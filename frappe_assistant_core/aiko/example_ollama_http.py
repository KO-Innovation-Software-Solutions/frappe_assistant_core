import argparse
import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import timedelta
from io import BytesIO
import json
import logging
import os
from typing import Any, Dict, Optional

from mcp import ClientSession
from mcp.types import ImageContent
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from mcp.client.streamable_http import streamablehttp_client
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ollama-browser-session")

class MCPClient:
    def __init__(self,server_url: str, transport_type: str, initial_task: str):
        self.server_url = server_url
        self.transport_type = transport_type
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.task = initial_task
        
        # Get Ollama model from environment variable or use default
        ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
        logger.info(f"Using Ollama model: {ollama_model}")
        
        # Configure Ollama with optimized parameters
        self.llm = ChatOllama(
            model=ollama_model,
            validate_model_on_init=True,
            temperature=0.8,
            num_ctx=32000,  # Large context window for complex tasks
            base_url="http://localhost:11434",
        )
        
        # Initialize conversation history for continuous context
        self.messages:list[SystemMessage|HumanMessage|AIMessage] = [
            SystemMessage(content="""Use the browser automation tools and open required websites for extracting relevant information, and execute tasks.
            Every step need to be well thought out and decide on the next procedure to be taken to execute the task.
            """)
        ]
        
        # Cache for storing frequently accessed data
        self.cache = {}
    
    async def connect(self):
        """Connect to the MCP server."""
        print(f"🔗 Attempting to connect to {self.server_url}...") 

        print("📡 Opening StreamableHTTP transport connection with auth...")
        async with streamablehttp_client(
            url=self.server_url,
            timeout=timedelta(seconds=60),
        ) as (read_stream, write_stream, get_session_id):
            await self._run_session(read_stream, write_stream, get_session_id)

    async def _run_session(self, read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            self.session = session
            await session.initialize()
            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    print(f"Session ID: {session_id}")

            try:
                response = await self.session.list_tools()
                self.tools = response.tools
                print("\nConnected to server with tools:", [tool.name for tool in self.tools])
                
                tools_info = "\n".join([f"- {tool.name}: {tool.description},'inputSchema':{tool.inputSchema}" for tool in self.tools])
                self.messages[0] = SystemMessage(content=f"{self.messages[0].content}\n\nAvailable tools:\n{tools_info}")
            
            except Exception as e:
                logger.error(f"Error listing tools: {str(e)}", exc_info=True)
                raise
            await self.interactive_loop()
           
    async def cleanup(self):
        """Clean up resources"""
        logger.debug("Cleaning up resources")
        await self.exit_stack.aclose()

    async def interactive_loop(self):

        # Add the initial task to the conversation
        self.messages.append(HumanMessage(content=f"Task: {self.task}\n\nWhat should be my first step?"))

        session_id = None
        task_complete = False
            
        while not task_complete:
            try:
                # Get Ollama's next recommendation
                print("\nSending current state to Ollama for analysis...")
                response = await self.llm.ainvoke(self.messages)
                print(f"\nOllama's analysis:\n{response.content}")

              
                # Add Ollama's response to the conversation history
                self.messages.append(AIMessage(content=response.content))
                
                # Parse the recommended action
                action = self._parse_next_action(str(response.content), session_id)
                if not action:
                    # Ask for a more specific action
                    self.messages.append(HumanMessage(content="Please provide a specific action to take using one of the available tools. Format your response as a JSON object with 'tool' and 'parameters' fields."))
                    continue
                
                # Check if the task is complete
                if action.get("tool") == "task_complete":
                    print("\nTask completed successfully!")
                    task_complete = True
                    break
                
                # Execute the recommended action
                tool_name = action["tool"]
                parameters = action["parameters"]
                
                # Handle session ID for browser actions
                if tool_name == "launch_browser" and self.session:
                    print(f"\nExecuting: {tool_name}")
                    print(f"Parameters: {json.dumps(parameters, indent=2)}")
                    
                    result = await self.session.call_tool(tool_name, parameters)
                    result_text = f"session_id: {result.content[0].text}" # type: ignore
                    print(f"Result: {result_text}")
                    
                    # Store the session ID
                    session_id = result.content[0].text # type: ignore
                elif tool_name == "take_screenshot" and self.session:
                    print(f"\nExecuting: {tool_name}")
                    print(f"Parameters: {json.dumps(parameters, indent=2)}")
                    
                    result = await self.session.call_tool(tool_name, parameters)
                    resultImage:list[ImageContent] = result.content[0] # type: ignore
                    result_text = f"Screenshot captured ({len(resultImage.data)} bytes). File processed and cleaned up for security." # type: ignore
                    encoded_data = resultImage.data # type: ignore
                    decoded_image_data = base64.b64decode(encoded_data)
                    image_stream = BytesIO(decoded_image_data)
                    image = Image.open(image_stream)
                    image.show()          
                    result_text = f"Screenshot saved. The browser window shows the current state of the page."
                elif session_id and self.session:
                    # Update the session ID in the parameters
                    parameters["session_id"] = session_id
                    
                    print(f"\nExecuting: {tool_name}")
                    print(f"Parameters: {json.dumps(parameters, indent=2)}")
                    
                    result = await self.session.call_tool(tool_name, parameters)
                    result_text = result.content[0].text # type: ignore
                    print(f"Result: {result_text}")

                elif self.session:
                    print(f"\nExecuting: {tool_name}")
                    print(f"Parameters: {json.dumps(parameters, indent=2)}")
                    
                    result = await self.session.call_tool(tool_name, parameters)
                    result_text = result.content[0].text # type: ignore
                    print(f"Result: {result_text}")
                
                # Add the result to the conversation
                self.messages.append(HumanMessage(content=f"Action result: {result_text}\n\nWhat should be my next step?"))
            except KeyboardInterrupt:
                logger.info("\nTask execution interrupted by user.")
                print("\n\n👋 Goodbye!")
                break
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Error during execution: {str(e)}", exc_info=True)
                break
            finally:
                await self.cleanup()

    def _parse_next_action(self, response_text: str, session_id:str | None) -> Dict[str, Any] | None:
        """Parse the next action from Ollama's response
        
        Args:
            response_text: Ollama's response text
            
        Returns:
            Dictionary with tool name and parameters, or None if no valid action found
        """

        try:
            import re
            content = response_text.replace("\n", "")
            if "json" in content:
                json_matches = re.findall(r'(?<=```json).*?(?=```)', content)
                action = json.loads(json_matches[0])
                if isinstance(action, dict):
                    if "name" in action and "arguments" in action:
                        return {
                            "tool":action["name"],
                            "parameters":action["arguments"]
                        }
                    elif "tool" in action and "parameters" in action:
                        return action
                    elif "tool" in action and "inputSchema" in action:
                        return {
                            "tool":action["tool"],
                            "parameters": action["inputSchema"]
                        }
            elif "python" in content:
                json_matches = re.findall(r'(?<=python)(.+)\)', content)
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
                action = json.loads(content)
                if isinstance(action, dict) and "tool" in action and "parameters" in action:
                    return action
        except json.JSONDecodeError:
            print()

        try:
            if hasattr(self, 'tools'):
                tool_names = [tool.name for tool in self.tools]
                for tool_name in tool_names:
                    if tool_name in response_text:
                        # Try to extract parameters from the text
                        params_start = response_text.find(tool_name) + len(tool_name)
                        params_text = response_text[params_start:].strip()

                        if tool_name != "launch_browser" and not session_id:
                            return None
                        
                        # Simple heuristic to extract parameters
                        parameters = {}
                        if "url" in params_text.lower() and tool_name == "launch_browser":
                            url_match = re.search(r'https?://[^\s"\']+', params_text)
                            if url_match:
                                parameters["url"] = url_match.group(0)
                                return {"tool": tool_name, "parameters": parameters}
                        elif tool_name == "click_element":
                            if "x" in params_text.lower() and "y" in params_text.lower():
                                pattern_match = re.search(r'x":\s*([^,]*),.*\s*?"y":\s*([^,]*)', params_text)                          
                                if pattern_match:
                                    parameters["x"] = pattern_match.group(1)
                                    parameters["y"] = pattern_match.group(2)
                                    return {"tool": tool_name, "parameters": parameters}
                            elif "coordinates" in params_text.lower():
                                pattern_match = re.findall(r'\d+', params_text)                                  
                                if pattern_match:
                                    parameters["x"] = pattern_match[0]
                                    parameters["y"] = pattern_match[1]
                                    return {"tool": tool_name, "parameters": parameters}
                        elif tool_name == "click_selector" and  "selector" in params_text.lower():
                            pattern_match = re.search(r'(?<="selector": )\".+\"', params_text)                          
                            if pattern_match:
                                parameters["selector"] = pattern_match.group(0).strip('"')
                                return {"tool": tool_name, "parameters": parameters}
                        elif tool_name == "type_text" and '"text"' in params_text.lower():
                            content = response_text.replace("\n", "")
                            json_pattern = r'(?<=```json).*?(?=})'
                            json_matches = re.findall(json_pattern, content)
                            action = json.loads(json_matches[0]+'}}')
                            print(action)
                            if "arguments" in action:
                                return {
                                    "tool":tool_name,
                                    "parameters":action["arguments"]
                                }
                            elif "parameters" in action:
                                return action
                            elif "inputSchema" in action:
                                return {
                                    "tool":tool_name,
                                    "parameters": action["inputSchema"]
                                }
                        elif tool_name == "scroll_page" and "direction" in params_text.lower():
                            pattern_match = re.search(r'(?<="direction": )\".+\"', params_text)                          
                            if pattern_match:
                                parameters["direction"] = pattern_match.group(0).strip('"')
                                return {"tool": tool_name, "parameters": parameters}
                        elif tool_name == "get_dom_structure":
                            parameters["max_depth"] = 3
                            parameters["session_id"] = session_id
                            return {"tool": tool_name, "parameters": parameters}
                        elif tool_name == "extract_data":
                            pattern_match = re.search(r'(?:)\[[\S\s]*\]', params_text)
                            if pattern_match:
                                parameters["pattern"] = pattern_match.group(0)
                                return {"tool": tool_name, "parameters": parameters}                       
                        elif tool_name == "take_screenshot" \
                            or tool_name == "get_page_content" :
                            parameters["session_id"] = session_id
                            return {"tool": tool_name, "parameters": parameters}

            
            # If task completion is mentioned
            if "task complete" in response_text.lower() or "task is complete" in response_text.lower():
                return {"tool": "task_complete", "parameters": {}}
                
            return None
            
        except Exception as e:
            logger.warning(f"Failed to parse next action: {e}")
            return None


async def main(): 
#     import re
#     response_text = '` tool to enter the search query and then simulate a click on the resulting link.\n   \n2. **Search and Click "HTML DOM API"**:\n   - Similarly, search for and click on the "HTML DOM API" section.\n\nLet\'s proceed with these steps:\n\n1. **Type Search Query for "Web APIs"**:\n   ```json\n   {\n     "tool": "type_text",\n     "inputSchema": {\n       "session_id": "cf4cf744576b53b20b0db4658915e3ff",\n       "text": "Web APIs"\n     }\n   }\n   ```\n\n2. **Click on the Resulting Link**:\n   - Assuming the search results are displayed and the first link is for "Web APIs", you can click it using its text content.\n   \n3. **Type Search Query for "HTML DOM API"**:\n   ```json\n   {\n     "tool": "type_text",\n     "inputSchema": {\n       "session_id": "cf4cf744576b53b20b0db4658915e3ff",\n       "text": "HTML DOM API"\n     }\n   }\n   ```\n\n4. **Click on the Resulting Link**:\n   - Similarly, click on the resulting link for "HTML DOM API".\n\nAfter these clicks, you should be on the HTML DOM API page. Now, you can extract its content using the `get_page_content` tool.\n\nHere is the command to get the page content:\n```json\n{\n  "tool": "get_page_content",\n  "inputSchema": {\n    "session_id": "cf4cf744576b53b20b0db4658915e3ff"\n  }\n}\n```\n\nProceed with these steps to navigate and extract the content from the MDN HTML DOM API page.'
#     content = response_text.replace("\n", "")
#  #   toolnameAndParamsMatch = re.search(r'(?<=python\\n).+\)', response_text)
#     json_pattern = r'(?<=```json).*?(?=})'
#     json_matches = re.findall(json_pattern, content)
#     for t in json_matches:
#         action = json.loads(t+'}}')
#         print(action)
#     toolnameAndParamsMatch = re.search(r'(?<=python\\n)(.+)\)', response_text)
#     print(f"toolnameAndParamsMatch: {toolnameAndParamsMatch}")
  
    server_url = 5600
    transport_type = "streamable-http"
    server_url = f"http://localhost:{server_url}/mcp"

    print("MCP Client using Ollama")
    print(f"Connecting to: {server_url}")
    print(f"Transport type: {transport_type}")

    parser = argparse.ArgumentParser(description="Interactive browser automation with Ollama")
    parser.add_argument("task", nargs='?', help="Task description")
    args = parser.parse_args()
    print(f"executing Task: {args.task}")
    if not args.task:
         args.task = "Navigate to Ollama's model library, analyze the page content, and extract information about the available models."

    # Start connection flow - OAuth will be handled automatically
    client = MCPClient(server_url, transport_type, args.task)
    await client.connect()

if __name__ == "__main__":
    asyncio.run(main())
