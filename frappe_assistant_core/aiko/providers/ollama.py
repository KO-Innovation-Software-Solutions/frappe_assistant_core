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

    async def _render_as_openui(self, final_answer: str, user_prompt: str, tool_call_log: list | None = None) -> str | None:
        system_prompt = build_dashboard_system_prompt()

        # Ground the render step in the tool calls that were ACTUALLY made
        # during this conversation, so it can only build Query(tool_name,
        # args, []) bindings that reference a real, already-proven-working
        # (tool_name, args) pair — never invent one from prose, and never
        # fall back to baking literals "because it doesn't know the source."
        tool_call_log = tool_call_log or []
        if tool_call_log:
            lines = []
            for c in tool_call_log:
                try:
                    result_preview = json.dumps(c.get("result"))
                except Exception:
                    result_preview = str(c.get("result"))
                if len(result_preview) > 500:
                    result_preview = result_preview[:500] + "…"
                lines.append(f"- {c.get('name')}({json.dumps(c.get('args', {}))}) -> {result_preview}")
            tool_calls_block = (
                "Tool calls that were ACTUALLY made to produce this answer, with their real "
                "arguments and a preview of what they returned:\n" + "\n".join(lines) + "\n\n"
                "Every Query(tool_name, args, []) binding you write MUST reuse one of these exact "
                "(tool_name, args) pairs verbatim — same tool name, same argument keys/values. "
                "Do NOT invent a tool call, a doctype, a filter, or an argument that is not listed "
                "above, even if it seems like a reasonable guess. If a number in the response text "
                "cannot be traced to any tool call above, do NOT bake it as a literal either — "
                "instead add a Callout(\"warning\", ...) noting that figure is unavailable as live "
                "data, or omit that specific KPI/section rather than fabricate its binding.\n\n"
            )
        else:
            tool_calls_block = (
                "No tool calls were made for this response. Do not invent Query(...) bindings that "
                "reference tools/args that were never actually called — if there is no real data "
                "source, keep the dashboard to static/explanatory content (e.g. Callout components) "
                "rather than fabricating numbers.\n\n"
            )

        render_instruction = (
            f"User asked: {user_prompt!r}\n\n"
            f"Response to format:\n{final_answer}\n\n"
            f"{tool_calls_block}"
            "Re-express this as OpenUI Lang using ONLY the approved components above.\n"
            "Output ONLY the component expression — no explanation, no markdown fences, no code blocks.\n"
            "CRITICAL: EVERY piece of text content must be wrapped in a component (TextContent, MarkDownRenderer, CardHeader, etc.). "
            "NEVER put bare text as a raw string child of Stack or Card. "
            "The children of Stack/Card must be only component elements, never free-form text.\n"
            "Start with: root = Stack([...]) or root = Card([...]) etc.\n"
            "CRITICAL — DATA MUST STAY LIVE, NEVER BAKE NUMBERS AS PLAIN LITERALS: every count, sum, "
            "average, or breakdown MUST come from a Query(tool_name, args, []) binding backed by a real "
            "tool call from the list above (list_documents, aggregate_documents, etc.), the same way the "
            "system prompt's own worked examples do it — e.g. `assets = Query(\"list_documents\", "
            "{\"doctype\": \"Asset\"}, [])` then `TextContent(\"\" + @Count(assets), \"large-heavy\")`, or "
            "for a category/status breakdown, `byCategory = Query(\"aggregate_documents\", {\"doctype\": "
            "\"Asset\", \"group_by\": \"asset_category\"}, [])` then `BarChart(byCategory.label, "
            "[Series(\"Count\", byCategory.value)], ...)`. Writing a plain number literal like "
            "TextContent(\"42\", ...) or a hardcoded array like Col(\"Asset ID\", [\"AST-001\", \"AST-002\"]) "
            "for data that came from a tool call is WRONG — it freezes that data forever and breaks the "
            "dashboard's Refresh button. Follow the system prompt's worked examples exactly; do not invent "
            "a simpler literal-only shortcut, and do not invent a Query() call that isn't in the tool-call "
            "list above.\n"
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

    async def process_query(self, query: str, tools: list, messages: list, on_stage=None, is_cancelled=None, want_ui=False, reasoning_effort=None, thread_id=None, call_tool=None) -> tuple:
        def cancelled():
            return is_cancelled is not None and is_cancelled()

        messages.append({"role": "user", "content": query})
        total_input_tokens = 0
        total_output_tokens = 0
        any_tool_called = False
        tool_call_log = []
        while True:
            if cancelled():
                return (
                    "",
                    messages,
                    {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
                    None,
                    tool_call_log,
                    None,
                )
            if any_tool_called and on_stage:
                await on_stage("Putting together your answer…")
            response = await asyncio.to_thread(
                self.openai.chat.completions.create,
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
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
                manifest = None
                if want_ui and not cancelled():
                    if on_stage:
                        await on_stage("Formatting dashboard…")
                    ui = await self._render_as_openui(final_answer, query, tool_call_log)
                    if ui:
                        from frappe_assistant_core.aiko.openui.dsl_manifest import build_manifest
                        try:
                            manifest = build_manifest(ui, [c["result"] for c in tool_call_log])
                        except Exception:
                            import frappe
                            frappe.logger().warning("build_manifest failed", exc_info=True)
                            manifest = None
                return final_answer, messages, usage, ui, tool_call_log, manifest

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
                    return (
                        "",
                        messages,
                        {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
                        None,
                        tool_call_log,
                        None,
                    )
                tool_name = tool_call.function.name
                if on_stage:
                    await on_stage(f"Checking {_humanize_tool_name(tool_name)}…")
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except Exception:
                    tool_args = {}
                try:
                    if call_tool:
                        tool_result = await call_tool(tool_name, tool_args)
                    else:
                        tool_result = "No tool executor available."
                except Exception as e:
                    tool_result = f"Error calling tool: {e}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

                try:
                    parsed_result = json.loads(tool_result)
                except Exception:
                    parsed_result = tool_result
                tool_call_log.append({"name": tool_name, "args": tool_args, "result": parsed_result})

                any_tool_called = True