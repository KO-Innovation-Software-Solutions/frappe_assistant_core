import json
import asyncio
from frappe_assistant_core.aiko.openui.system_prompt import build_dashboard_system_prompt
def _humanize_tool_name(name: str) -> str:
    label = name.replace('_', ' ').strip()
    for prefix in ("get ", "list ", "fetch ", "search "):
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    return label or name

class OllamaProvider:
    def __init__(self, settings):
        from openai import OpenAI
        self.settings = settings
        api_key = "ollama"
        base_url = self.settings.get("ollama_chat_api_url") or "http://localhost:11434"
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        self.model = self.settings.get("ollama_chat_model") or "llama3.1"
        self.openai = OpenAI(api_key=api_key, base_url=base_url)

    async def _render_as_openui(self, final_answer: str, user_prompt: str) -> str | None:
        system_prompt = build_dashboard_system_prompt()
        render_instruction = (
            f"User asked: {user_prompt!r}\n\n"
            f"Response to format:\n{final_answer}\n\n"
            "Re-express this as OpenUI Lang using ONLY the approved components above.\n"
            "Output ONLY the component expression — no explanation, no markdown fences, no code blocks.\n"
            "CRITICAL: EVERY piece of text content must be wrapped in a component (TextContent, MarkDownRenderer, CardHeader, etc.). "
            "NEVER put bare text as a raw string child of Stack or Card. "
            "The children of Stack/Card must be only component elements, never free-form text.\n"
            "Start with: root = Stack([...]) or root = Card([...]) etc.\n"
            "Examples:\n"
            "  User: Show total vehicles\n"
            "  Response: 42\n"
            "  Output: root = Stack([Card([CardHeader(\"Total Vehicles\"), TextContent(\"42\", \"large-heavy\")])])\n"
            "  User: Fleet overview summary\n"
            "  Response: Total vehicles: 7. Available: 4. In maintenance: 2.\n"
            "  Output: root = Stack([Card([CardHeader(\"Fleet Overview\"), TextContent(\"Total vehicles: 7\"), TextContent(\"Available: 4\"), TextContent(\"In maintenance: 2\")])])\n"
        )
        try:
            response = await asyncio.to_thread(
                self.openai.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": render_instruction},
                ],
            )
            raw = response.choices[0].message.content or ""
            t = raw.strip()
            if t and ("root =" in t):
                return t
            import frappe
            frappe.logger().warning(f"_render_as_openui returned non-DSL output: {raw[:200]}")
            return None
        except Exception as e:
            import frappe
            frappe.logger().error(f"_render_as_openui failed: {e}", exc_info=True)
            return None

    async def process_query(self, query: str, session, messages: list, on_stage=None, is_cancelled=None, want_ui=False) -> tuple:
        def cancelled():
            return is_cancelled is not None and is_cancelled()

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
        any_tool_called = False
        while True:
            if cancelled():
                return "", messages, {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}, None
            if any_tool_called and on_stage:
                await on_stage("Putting together your answer…")
            response = await asyncio.to_thread(
                self.openai.chat.completions.create,
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
                ui = None
                if want_ui:
                    if on_stage:
                        await on_stage("Formatting dashboard…")
                    ui = await self._render_as_openui(final_answer, query)
                return final_answer, messages, usage, ui

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
                    return "", messages, {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}, None
                tool_name = tool_call.function.name
                if on_stage:
                    await on_stage(f"Checking {_humanize_tool_name(tool_name)}…")
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
                any_tool_called = True