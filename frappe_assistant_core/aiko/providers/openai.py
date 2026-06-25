import json

import asyncio

from openai import OpenAI
 
MAX_TOOL_ITERATIONS = 8

MAX_TOOL_RESULT_CHARS = 12000
 
 
def _humanize_tool_name(name: str) -> str:

    label = name.replace("_", " ").strip()

    for prefix in ("get ", "list ", "fetch ", "search "):

        if label.startswith(prefix):

            label = label[len(prefix):]

            break

    return label or name
 
 
def _stringify_tool_content(content) -> str:

    """Extract clean text from an MCP CallToolResult.content list."""

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

    return (

        f"{text[:limit]}\n\n"

        f"[...truncated, {omitted} more characters omitted to fit the model's context window...]"

    )
 
 
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
 
    async def _run_loop(

        self, session, messages: list, tools: list,

        on_stage=None, is_cancelled=None,

    ) -> tuple:

        """Core agentic loop with cancellation, stage events, and tool-result safety."""

        def cancelled():

            return is_cancelled is not None and is_cancelled()
 
        total_input_tokens = 0

        total_output_tokens = 0

        last_tool_result_text = None

        any_tool_called = False
 
        for _ in range(MAX_TOOL_ITERATIONS):

            if cancelled():

                return "", messages, {

                    "input_tokens": total_input_tokens,

                    "output_tokens": total_output_tokens,

                }
 
            if any_tool_called and on_stage:

                await on_stage("Putting together your answer...")
 
            response = await asyncio.to_thread(

                self.openai.chat.completions.create,

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
 
                # Fallback: if model produced nothing, surface last tool result

                if not final_answer and last_tool_result_text:

                    final_answer = (

                        "Here is the extracted file content (the model didn't "

                        "add commentary, so showing the raw extraction):\n\n"

                        f"{last_tool_result_text}"

                    )
 
                messages.append({"role": "assistant", "content": final_answer})

                return final_answer, messages, {

                    "input_tokens": total_input_tokens,

                    "output_tokens": total_output_tokens,

                }
 
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

                if cancelled():

                    return "", messages, {

                        "input_tokens": total_input_tokens,

                        "output_tokens": total_output_tokens,

                    }
 
                tool_name = tool_call.function.name

                if on_stage:

                    await on_stage(f"Checking {_humanize_tool_name(tool_name)}...")
 
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

                any_tool_called = True
 
        # Hit iteration cap -- surface whatever we have

        final_answer = ""

        if last_tool_result_text:

            final_answer = (

                "Reached the tool-call limit before the model wrapped up, "

                "so here is the most recent extracted content:\n\n"

                f"{last_tool_result_text}"

            )

        messages.append({"role": "assistant", "content": final_answer})

        return final_answer, messages, {

            "input_tokens": total_input_tokens,

            "output_tokens": total_output_tokens,

        }
 
    async def process_query(

        self, query: str, session, messages: list,

        on_stage=None, is_cancelled=None,

    ) -> tuple:

        """Entry point for plain-text queries."""

        tools = await self._get_tools(session)

        messages.append({"role": "user", "content": query})

        return await self._run_loop(

            session, messages, tools,

            on_stage=on_stage, is_cancelled=is_cancelled,

        )
 
    async def process_query_with_messages(self, session, messages: list) -> tuple:

        """Entry point for pre-built message lists (multimodal / file extraction).

        The caller is responsible for appending the user message before calling this."""

        tools = await self._get_tools(session)

        return await self._run_loop(session, messages, tools)