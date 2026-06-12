import json
from openai import OpenAI

class OllamaProvider:
    def __init__(self, settings):
        self.settings = settings
        api_key = "ollama"
        base_url = self.settings.get("ollama_chat_api_url") or "http://localhost:11434"
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
        self.model = self.settings.get("ollama_chat_model") or "llama3.1"
        self.openai = OpenAI(api_key=api_key, base_url=base_url)
    async def process_query(self, query: str, session, messages: list) -> tuple:
        tools = []
        if session:
            response = await session.list_tools()
            for tool in response.tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    },
                })
        messages.append({"role": "user", "content": query})
        total_input_tokens = 0
        total_output_tokens = 0
        while True:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
            )
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens or 0
                total_output_tokens += response.usage.completion_tokens or 0
            assistant_message = response.choices[0].message
            if not assistant_message.tool_calls:
                final_answer = assistant_message.content or ""
                messages.append({"role": "assistant", "content": final_answer})
                usage = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                }
                return final_answer, messages, usage
            messages.append({
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
            })
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except Exception:
                    tool_args = {}
                try:
                    if session:
                        result = await session.call_tool(tool_name, tool_args)
                        if isinstance(result.content, list):
                            tool_result = "\n".join(str(item) for item in result.content)
                        else:
                            tool_result = str(result.content)
                    else:
                        tool_result = "No session available."
                except Exception as e:
                    tool_result = f"Error calling tool: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })