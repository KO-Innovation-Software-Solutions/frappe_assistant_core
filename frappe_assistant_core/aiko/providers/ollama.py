import json
import re
from typing import Optional, Dict, Any

class OllamaProvider:
    def __init__(self, settings):
        from langchain_ollama import ChatOllama
        self.settings = settings
        self.ollama_url = getattr(self.settings, "ollama_chat_api_url", "http://localhost:11434").rstrip("/")
        self.model = getattr(self.settings, "ollama_chat_model", "llama3.1")
        
        # Configure Ollama with optimized parameters
        self.llm = ChatOllama(
            model=self.model,
            validate_model_on_init=True,
            temperature=0.0,
            num_ctx=32000,
            base_url=self.ollama_url,
        )

    def _parse_next_action(self, response_text: str, tools: list) -> Optional[Dict[str, Any]]:
        """Parse the next action from Ollama's response"""
        try:
            content = response_text.replace("\n", "")
            if "json" in content:
                json_matches = re.findall(r'(?<=```json).*?(?=```)', content)
                if json_matches:
                    action = json.loads(json_matches[0])
                    if isinstance(action, dict):
                        if "name" in action and "arguments" in action:
                            return {
                                "tool": action["name"],
                                "parameters": action["arguments"]
                            }
                        elif "tool" in action and "parameters" in action:
                            return action
                        elif "tool" in action and "inputSchema" in action:
                            return {
                                "tool": action["tool"],
                                "parameters": action["inputSchema"]
                            }
            elif "python" in content:
                json_matches = re.findall(r'(?<=python)(.+)\)', content)
                if json_matches:
                    firstTool = json_matches[0]
                    index = firstTool.find('(')
                    if index != -1:
                        action = {}
                        action["tool"] = firstTool[:index]
                        paramSection = firstTool[index+1:]
                        index = paramSection.find(')')
                        if index != -1:
                            paramSection = paramSection[:index]
                        paramMatches = re.findall(r'([^,]+)=([^,]+)', paramSection)
                        params = {}
                        for p in paramMatches:
                            params[p[0].strip()] = p[1].strip('\"\'')
                        action["parameters"] = params
                        return action
            elif "parameters" in content or "url" in content:
                try:
                    action = json.loads(content)
                    if isinstance(action, dict) and "tool" in action and "parameters" in action:
                        return action
                except Exception:
                    pass
        except Exception:
            pass

        try:
            tool_names = [tool.name for tool in tools]
            for tool_name in tool_names:
                if tool_name in response_text:
                    start_idx = response_text.find('{', response_text.find(tool_name))
                    if start_idx != -1:
                        brace_count = 0
                        for i in range(start_idx, len(response_text)):
                            if response_text[i] == '{':
                                brace_count += 1
                            elif response_text[i] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_str = response_text[start_idx:i+1]
                                    try:
                                        parsed = json.loads(json_str)
                                        if isinstance(parsed, dict):
                                            return {
                                                "tool": tool_name,
                                                "parameters": parsed.get("arguments", parsed.get("parameters", parsed))
                                            }
                                    except Exception:
                                        pass
                                    break
        except Exception:
            pass

        if "task complete" in response_text.lower() or "task is complete" in response_text.lower():
            return {"tool": "task_complete", "parameters": {}}

        return None

    async def process_query(self, query: str, session, system_prompt: str, thread_id: str) -> dict:
        """Process a query using the configured provider and available tools"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        import frappe
        
        response = await session.list_tools()
        tools = response.tools
        
        tools_info = "\n".join([f"- {tool.name}: {tool.description},'inputSchema':{tool.inputSchema}" for tool in tools])
        system_message_content = f"{system_prompt}\n\nAvailable tools:\n{tools_info}\n\nFormat your response as a JSON object with 'tool' and 'parameters' fields when calling tools."
        
        messages = [
            SystemMessage(content=system_message_content)
        ]
        
        # Load chat history for multi-turn context
        history_key = f"aiko_history_{thread_id}"
        chat_history = frappe.cache().get_value(history_key) or []
        for msg in chat_history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg.get("content", "")))
        
        messages.append(HumanMessage(content=f"Task: {query}\n\nWhat should be my first step?"))

        structured_response = {
            "messages": [],
            "activities": [],
            "documents": [],
            "suggestions": []
        }
        tool_call_history = []

        for _ in range(15): # Max iteration limit
            response_msg = await self.llm.ainvoke(messages)
            messages.append(AIMessage(content=response_msg.content))
            
            content_str = str(response_msg.content)
            
            # Remove any raw JSON or python blocks from the content so they don't show up in the chat UI
            clean_content = re.sub(r'```json.*?```', '', content_str, flags=re.DOTALL).strip()
            clean_content = re.sub(r'```python.*?```', '', clean_content, flags=re.DOTALL).strip()
            
            # Remove any [Calling tool ...] hallucinatory logs
            clean_content = re.sub(r'\[Calling tool.*?\]', '', clean_content, flags=re.DOTALL).strip()
            
            # Remove "Task completed successfully!" as the frontend handles completion
            clean_content = re.sub(r'Task completed successfully!', '', clean_content, flags=re.IGNORECASE).strip()
            
            # If the entire message was just a JSON object (e.g. for a tool call), hide it completely
            if clean_content.startswith('{') and clean_content.endswith('}'):
                clean_content = ""
            
            action = self._parse_next_action(content_str, tools)
            
            # Classify content as intermediate thought or final message
            if clean_content and clean_content.lower() not in ["task complete", "task is complete"]:
                if action and action.get("tool") not in ["task_complete", "None", None]:
                    structured_response["activities"].append({
                        "tool": "Reasoning",
                        "args": {"text": clean_content},
                        "status": "thought"
                    })
                else:
                    structured_response["messages"].append({
                        "type": "assistant",
                        "content": clean_content
                    })
            
            if not action:
                if "task complete" in content_str.lower() or "task is complete" in content_str.lower():
                    break
                
                messages.append(HumanMessage(content="If you are done, please provide a clear summary of your findings or the action you took to the user, and then just say 'Task complete'. Otherwise, provide a specific action to take using one of the available tools. Format your response as a JSON object with 'tool' and 'parameters' fields."))
                continue

            tool_name = action.get("tool")
            parameters = action.get("parameters", {})

            if tool_name == "task_complete" or tool_name == "None" or not tool_name:
                break

            call_signature = f"{tool_name}::{json.dumps(parameters, sort_keys=True)}"
            if call_signature in tool_call_history:
                messages.append(HumanMessage(content="System Warning: You have already executed this exact tool. DO NOT execute it again. Use the data you have."))
                continue
                
            tool_call_history.append(call_signature)

            try:
                result = await session.call_tool(tool_name, parameters)
                
                structured_response["activities"].append({
                    "tool": tool_name,
                    "args": parameters,
                    "status": "success"
                })
                
                if tool_name == "get_document" and "doctype" in parameters and "name" in parameters:
                    structured_response["documents"].append({
                        "doctype": parameters.get("doctype"),
                        "name": parameters.get("name")
                    })
                
                text_contents = []
                if hasattr(result, "content") and isinstance(result.content, list):
                    for block in result.content:
                        if hasattr(block, "text"):
                            text_contents.append(block.text)
                        else:
                            text_contents.append(str(block))
                    result_text = "\n".join(text_contents)
                else:
                    result_text = str(result.content if hasattr(result, "content") else result)
            except Exception as e:
                result_text = f"Error executing tool: {str(e)}"
                structured_response["activities"].append({
                    "tool": tool_name,
                    "args": parameters,
                    "status": "error"
                })

            messages.append(HumanMessage(content=f"Action result: {result_text}\n\nWhat should be my next step?"))

        # Generate suggestions based on documents
        suggestions = []
        for doc in structured_response["documents"]:
            dt = doc["doctype"]
            name = doc["name"]
            if dt == "Vehicle":
                suggestions.extend([
                    f"Show telematics history for {name}",
                    f"Show latest location of {name}",
                    f"Who is assigned to {name}?",
                    "List all vehicles"
                ])
            elif dt == "Customer":
                suggestions.extend([
                    "Show recent orders",
                    "Show outstanding balance",
                    "Show contact details",
                    "List related invoices"
                ])
            elif dt == "Sales Order":
                suggestions.extend([
                    "Show items in this order",
                    "Show payment status",
                    "Show customer details",
                    "List related invoices"
                ])
        
        # Remove duplicates while preserving order
        structured_response["suggestions"] = list(dict.fromkeys(suggestions))

        # Save the conversational multi-turn context
        final_answer = "\n".join([m["content"] for m in structured_response["messages"]])
        if not final_answer.strip():
            final_answer = "Task complete."
            
        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": final_answer})
        
        # Keep only the last 10 messages (5 user/assistant turns)
        frappe.cache().set_value(history_key, chat_history[-10:], expires_in_sec=86400)

        return structured_response
