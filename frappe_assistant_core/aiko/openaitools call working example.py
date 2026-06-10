import argparse
import asyncio
import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

MAX_HISTORY_MESSAGES = 20


class MCPClient:
    """OpenAI + MCP Streamable HTTP Client"""

    def __init__(
        self,
        model: str = "deepseek-ai/DeepSeek-V4-Flash"
    ):
        self.model = model
        self.session: Optional[ClientSession] = None

        self.openai = OpenAI(
            api_key=os.getenv(
                "DEEPINFRA_API_KEY",
                "JyrEuDM0UKCf8nRNlEhBI6E2AHpcV1Lo"
            ),
            base_url="http://ollama.kofleetz.in:3900"
        )
        self._streams_context = None
        self._session_context = None

        # Persistent conversation history
        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant connected to MCP tools. "
                    "Use available tools whenever needed. "
                    "Maintain conversational context and answer accurately."
                ),
            }
        ]

    async def connect_to_streamable_http_server(
        self,
        server_url: str,
        headers: Optional[dict] = None,
    ):
        """Connect to MCP Streamable HTTP server"""

        self._streams_context = streamablehttp_client(
            url=server_url,
            headers=headers or {},
        )

        read_stream, write_stream, _ = (
            await self._streams_context.__aenter__()
        )

        self._session_context = ClientSession(
            read_stream,
            write_stream,
        )

        self.session = await self._session_context.__aenter__()

        await self.session.initialize()

        print(f"✅ Connected to MCP Server: {server_url}")

    async def get_tools(self):
        """Get MCP tools in OpenAI format"""

        response = await self.session.list_tools()

        tools = []

        for tool in response.tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                }
            )

        return tools

    def trim_history(self):
        """Prevent context window from growing forever"""

        if len(self.messages) > MAX_HISTORY_MESSAGES:
            system_prompt = self.messages[0]

            self.messages = (
                [system_prompt]
                + self.messages[-MAX_HISTORY_MESSAGES:]
            )

    async def process_query(self, query: str) -> str:
        """Process user query"""

        tools = await self.get_tools()

        self.messages.append(
            {
                "role": "user",
                "content": query,
            }
        )

        while True:

            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=tools,
                tool_choice="auto",
            )

            assistant_message = response.choices[0].message
            print("\n========== DEBUG ==========")
            print("CONTENT:")
            print(assistant_message.content)

            print("\nTOOL CALLS:")
            print(assistant_message.tool_calls)

            print("===========================\n")
            # No tool calls -> final answer
            if not assistant_message.tool_calls:

                final_answer = assistant_message.content or ""

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final_answer,
                    }
                )

                self.trim_history()

                return final_answer

            # Add assistant tool request
            self.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_message.tool_calls
                    ],
                }
            )

            # Execute tool calls
            for tool_call in assistant_message.tool_calls:

                tool_name = tool_call.function.name

                try:
                    tool_args = json.loads(
                        tool_call.function.arguments
                    )
                except Exception:
                    tool_args = {}

                print(
                    f"\n🔧 Calling Tool: {tool_name}"
                )

                result = await self.session.call_tool(
                    tool_name,
                    tool_args,
                )

                if isinstance(result.content, list):
                    tool_result = "\n".join(
                        str(item)
                        for item in result.content
                    )
                else:
                    tool_result = str(result.content)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

    async def chat_loop(self):
        """Interactive CLI"""

        print("\n🚀 MCP OpenAI Client Started")
        print("Type 'quit' or 'exit' to stop\n")

        while True:

            try:
                query = input("You: ").strip()

                if query.lower() in ("quit", "exit"):
                    break

                answer = await self.process_query(query)

                print("\nAssistant:")
                print(answer)
                print()

            except KeyboardInterrupt:
                break

            except Exception as e:
                print(f"\n❌ Error: {e}")

    async def cleanup(self):
        """Cleanup MCP resources"""

        try:
            if self._session_context:
                await self._session_context.__aexit__(
                    None,
                    None,
                    None,
                )
        except Exception:
            pass

        try:
            if self._streams_context:
                await self._streams_context.__aexit__(
                    None,
                    None,
                    None,
                )
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser(
        description="OpenAI MCP Streamable HTTP Client"
    )

    parser.add_argument(
        "--mcp-localhost-port",
        type=int,
        default=8123,
    )

    parser.add_argument(
        "--model",
        default="deepseek-ai/DeepSeek-V4-Flash",
    )
    args = parser.parse_args()

    client = MCPClient(model=args.model)

    try:

        await client.connect_to_streamable_http_server(
            f"http://127.0.0.1:8000/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp",
            headers={
                "Authorization": "token 1d7ad5e256bdb04:db8a2805e4820ac"
            }
        )

        await client.chat_loop()

    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())