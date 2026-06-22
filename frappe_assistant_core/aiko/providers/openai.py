import json
from openai import OpenAI

MAX_TOOL_ITERATIONS = 8
# Cap how much raw tool output we feed back into the model in one go, so a
# huge extracted document doesn't blow the context window by itself.
MAX_TOOL_RESULT_CHARS = 12000


def _stringify_tool_content(content) -> str:
    """Pull clean text out of an MCP CallToolResult.content list.

    `content` is normally a list of TextContent (and similar) Pydantic
    objects. Calling str() on those returns their repr
    (`type='text' text='...' annotations=None`), which roughly triples the
    token count and confuses smaller models with stray quotes/field names.
    We extract `.text` when present and only fall back to str() for content
    types that don't have it (e.g. embedded images/resources).
    """
    if isinstance(content, list):
        parts = []
        for item in content:
            text = getattr(item, "text", None)
            parts.append(text if text is not None else str(item))
        return "\n".join(parts)
    return str(content)


def _truncate_tool_result(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n\n[...truncated, {omitted} more characters omitted to fit the model's context window...]"


class OpenAIProvider:
    def __init__(self, settings):
        self.settings = settings
        api_key = self.settings.get_password("openai_api_key")
        base_url = self.settings.get("openai_url")
        self.model = self.settings.get("openai_model")
        self.openai = OpenAI(api_key=api_key, base_url=base_url)

    async def _get_tools(self, session) -> list:
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
        return tools

    async def _run_loop(self, session, messages: list, tools: list) -> tuple:
        """Core agentic loop shared by both entry points."""
        total_input_tokens = 0
        total_output_tokens = 0
        last_tool_result_text = None  # raw text from the most recent tool call

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=2048,
            )
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens or 0
                total_output_tokens += response.usage.completion_tokens or 0

            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                final_answer = assistant_message.content or ""

                if not final_answer and last_tool_result_text:
                    # The model produced nothing but we DO have the real
                    # extracted content from the last tool call. Surface
                    # that directly instead of a useless apology.
                    final_answer = (
                        "Here is the extracted file content (the model didn't "
                        "add commentary, so showing the raw extraction):\n\n"
                        f"{last_tool_result_text}"
                    )

                messages.append({"role": "assistant", "content": final_answer})
                usage = {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                }
                return final_answer, messages, usage

            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
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
                        tool_result = _stringify_tool_content(result.content)
                    else:
                        tool_result = "No session available."
                except Exception as e:
                    tool_result = f"Error calling tool: {e}"

                last_tool_result_text = tool_result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": _truncate_tool_result(tool_result),
                })

        # Hit the iteration cap without the model producing a final answer.
        # Surface the last extraction we have rather than going silent.
        final_answer = ""
        if last_tool_result_text:
            final_answer = (
                "Reached the tool-call limit before the model wrapped up, "
                "so here is the most recent extracted content:\n\n"
                f"{last_tool_result_text}"
            )
        messages.append({"role": "assistant", "content": final_answer})
        usage = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
        return final_answer, messages, usage

    async def process_query(self, query: str, session, messages: list) -> tuple:
        """Entry point for plain text queries."""
        tools = await self._get_tools(session)
        messages.append({"role": "user", "content": query})
        return await self._run_loop(session, messages, tools)

    async def process_query_with_messages(self, session, messages: list) -> tuple:
        """Entry point for pre-built message lists (e.g. multimodal/file queries).
        The caller is responsible for appending the user message before calling this."""
        tools = await self._get_tools(session)
        return await self._run_loop(session, messages, tools)