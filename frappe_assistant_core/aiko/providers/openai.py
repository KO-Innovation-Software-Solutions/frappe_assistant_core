import json
import re
from typing import Optional, Dict, Any

class OpenAIProvider:
    def __init__(self, settings):
        from langchain_openai import ChatOpenAI
        import frappe

        self.settings = settings
        
        try:
            self.api_key = self.settings.get_password("openai_api_key")
        except Exception:
            self.api_key = getattr(self.settings, "openai_api_key", None)
        
        if not self.api_key:
            frappe.throw("OpenAI API key is missing. Please set it in Assistant Core Settings.")
        
        self.api_key = self.api_key.strip()
        
        frappe.logger().info(f"OpenAI key length: {len(self.api_key)}, prefix: {self.api_key[:8]}")
        
        # Pull model and base_url from settings instead of hardcoding
        self.model = getattr(self.settings, "openai_model", None)
        self.base_url = getattr(self.settings, "openai_url", None)
        
        self.llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.0,
            max_tokens=4096,
        )

    def _parse_next_action(self, response_text: str, tools: list) -> Optional[Dict[str, Any]]:
        """Parse the next action from the model's response"""
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
                        paramSection = firstTool[index + 1:]
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
                                    json_str = response_text[start_idx:i + 1]
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
        """Process a query using OpenAI and available MCP tools"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        import frappe

        response = await session.list_tools()
        tools = response.tools

        tools_info = "\n".join([
            f"- {tool.name}: {tool.description},'inputSchema':{tool.inputSchema}"
            for tool in tools
        ])
        system_message_content = (
            f"{system_prompt}\n\nAvailable tools:\n{tools_info}\n\n"
            "Format your response as a JSON object with 'tool' and 'parameters' fields when calling tools."
        )

        messages = [SystemMessage(content=system_message_content)]

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

        for _ in range(15):
            response_msg = await self.llm.ainvoke(messages)
            messages.append(AIMessage(content=response_msg.content))

            content_str = str(response_msg.content)

            clean_content = re.sub(r'```json.*?```', '', content_str, flags=re.DOTALL).strip()
            clean_content = re.sub(r'```python.*?```', '', clean_content, flags=re.DOTALL).strip()
            clean_content = re.sub(r'\[Calling tool.*?\]', '', clean_content, flags=re.DOTALL).strip()
            clean_content = re.sub(r'Task completed successfully!', '', clean_content, flags=re.IGNORECASE).strip()

            if clean_content.startswith('{') and clean_content.endswith('}'):
                clean_content = ""

            action = self._parse_next_action(content_str, tools)

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

            # ── FIX: if no tool call was detected, treat response as final and stop ──
            if not action:
                break

            tool_name = action.get("tool")
            parameters = action.get("parameters", {})

            if tool_name == "task_complete" or tool_name == "None" or not tool_name:
                break

            call_signature = f"{tool_name}::{json.dumps(parameters, sort_keys=True)}"
            if call_signature in tool_call_history:
                messages.append(HumanMessage(
                    content="System Warning: You have already executed this exact tool. DO NOT execute it again. Use the data you have."
                ))
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

            messages.append(HumanMessage(
                content=f"Action result: {result_text}\n\nWhat should be my next step? If you have all the information needed, summarize it for the user and say 'Task complete'."
            ))

        # Generate suggestions based on opened documents
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

        structured_response["suggestions"] = list(dict.fromkeys(suggestions))

        # Persist conversational context
        final_answer = "\n".join([m["content"] for m in structured_response["messages"]])
        if not final_answer.strip():
            final_answer = "Task complete."

        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": final_answer})

        frappe.cache().set_value(history_key, chat_history[-10:], expires_in_sec=86400)

        return structured_response