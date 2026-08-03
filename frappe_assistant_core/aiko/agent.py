from typing import Optional
import json
import urllib.parse

import frappe
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from frappe.utils import get_url

from .providers import OpenAIProvider, OllamaProvider

MAX_HISTORY_MESSAGES = 20
TOOLS_CACHE_TTL_SEC = 300  # 5 min — tool schemas rarely change turn to turn

class AikoAgent:
    """Unified MCP Agent for Frappe"""

    def __init__(self, thread_id: str, surface: str = "chat"):
        self.thread_id = thread_id
        self.surface = surface
        self.session_doctype = "Aiko Dashboard Session" if surface == "dashboard" else "Aiko Chat Session"
        self.message_doctype = "Aiko Dashboard Message" if surface == "dashboard" else "Aiko Chat Message"
        self.settings = frappe.get_single("Assistant Core Settings")
        provider_name = self.settings.get("llm_provider", "ollama").lower()
        if provider_name == "openai":
            self.provider = OpenAIProvider(self.settings)
        else:
            self.provider = OllamaProvider(self.settings)
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None
        self._connected = False
        self._tools_cache_key = f"aiko_mcp_tools:{frappe.session.user}"

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are AIKO, an AI assistant exclusively for Kofleetz. "
                    "CRITICAL INSTRUCTIONS:\n"
                    "1.Never describe yourself as a general AI or reveal/mention the underlying platform, framework, or database terms (ERPNext, Frappe, doctype, etc.) — the user only sees Kofleetz."                    
                    "2. ONLY use provided tools to fetch real data. Never use internal knowledge or generate fake/assumed data.\n"
                    "3. If tools return no results, tell the user — never fabricate or fill in placeholder values.\n"
                    "4. For greetings or small talk, respond only with: 'I am AIKO, an AI assistant for Kofleetz. Please ask me about your fleet operations.'\n"
                    "5. If you lack a tool to fulfill a request, clearly inform the user.\n"
                    "6. Always summarize tool results clearly to the user — never dump raw tool output.\n"
                    "7. When the user's request is well suited to a chart or graph (comparisons, trends, "
                        "distributions, rankings), include a fenced code block that starts with exactly ```chart "
                        "(not ```json or plain ```) containing valid JSON with this structure, built from the actual "
                        "data you retrieved:\n"
                        '```chart\n'
                        '{"type": "<bar|line|pie>", "title": "<short title>", "xKey": "<label field>", "yKey": "<value field>", "data": [{"<xKey>": "<label>", "<yKey>": <number>}, ...]}\n'
                        '```\n'
                        "For multiple angles, place several ```chart blocks back-to-back with nothing between them "
                        "(they become tabs automatically, titled from each chart's own \"title\") — don't add your "
                        "own 'Chart 1/2' headings or a caption per chart, just one short insight line for the group.\n"
                    "8. Answer like a fleet manager, not a field dump: skip IDs, empty sections, and internal "
                        "fields that don't add meaning; show an ID only to distinguish similar results. Don't pad "
                        "with what's missing unless it blocks a useful answer. Prefer comparisons where meaningful "
                        "(planned vs. actual, target vs. current, this period vs. last) using only retrieved data.\n"
                    "9. End with a ```followups block: a JSON array of exactly 3 short next questions, no "
                        "other text around it — e.g.\n"
                        '```followups\n'
                        '["Which of those are overdue?", "Break this down by branch", "How does this compare to last month?"]\n'
                        '```'
                ),
            }
        ]
        self._load_history()

    def _load_history(self):
        session_name = frappe.db.get_value(
            self.session_doctype, {"thread_id": self.thread_id}, "name"
        )
        if not session_name:
            return
        past_messages = frappe.db.get_list(
            self.message_doctype,
            filters={
                "session": session_name,
                "role": ["in", ["user", "assistant"]],
            },
            fields=["role", "content"],
            order_by="creation asc",
            limit=MAX_HISTORY_MESSAGES,
        )
        for msg in past_messages:
            self.messages.append({"role": msg["role"], "content": msg["content"]})

    def _trim_history(self):
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            system_prompt = self.messages[0]
            self.messages = [system_prompt] + self.messages[-(MAX_HISTORY_MESSAGES - 1):]

    async def connect_to_streamable_http_server(self):
        """Connect to the Frappe MCP server"""
        user = frappe.session.user
        user_doc = frappe.get_doc("User", user)
        api_key = user_doc.api_key
        if not api_key:
            raise RuntimeError(
                f"User '{user}' does not have an API Key set. "
                "Please generate one in your Frappe user settings to enable the AI assistant."
            )
        api_secret = user_doc.get_password("api_secret")

        mcp_url = get_url("/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp")
        parsed = urllib.parse.urlparse(mcp_url)
        internal_url = mcp_url.replace(parsed.hostname, "127.0.0.1")
        if not parsed.port:
            internal_url = internal_url.replace(
                "127.0.0.1", f"127.0.0.1:{frappe.conf.webserver_port or 8000}"
            )

        headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Host": parsed.hostname,
        }

        self._streams_context = streamablehttp_client(url=internal_url, headers=headers)
        read_stream, write_stream, _ = await self._streams_context.__aenter__()

        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()

        await self.session.initialize()
        self._connected = True

    async def cleanup(self):
        if not self._connected:
            return  # never connected this turn — nothing to tear down
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
        except Exception:
            pass
        try:
            if self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
        except Exception:
            pass
        self._connected = False

    async def _get_tools(self) -> list:
        """
        Returns the OpenAI-format tool schema. Serves from a per-user cache
        whenever possible so a plain message never has to touch MCP at all.
        """
        cached = frappe.cache().get_value(self._tools_cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # fall through and refetch on any cache corruption

        await self.connect_to_streamable_http_server()
        try:
            response = await self.session.list_tools()
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                }
                for t in response.tools
            ]
        finally:
            await self.cleanup()  # this one-off connect is done as soon as we have the schema

        frappe.cache().set_value(
            self._tools_cache_key, json.dumps(tools), expires_in_sec=TOOLS_CACHE_TTL_SEC
        )
        return tools

    async def _call_tool(self, name: str, args: dict) -> str:
        """
        Lazily opens the MCP connection the first time a tool is actually
        needed in this turn, and reuses it for any further tool calls in the
        same query loop. Never opens a connection at all if no tool is called.

        Self-healing: if the cached tool schema is stale (a tool was renamed/
        removed server-side since the last cache refresh), this invalidates
        the cache and retries once against the live tool list before giving up,
        so a stale cache degrades gracefully instead of silently failing.
        """
        if not self._connected:
            await self.connect_to_streamable_http_server()
        try:
            result = await self.session.call_tool(name, args)
        except Exception as e:
            err = str(e)
            looks_stale = any(s in err.lower() for s in ("not found", "unknown tool", "no such tool", "invalid tool"))
            if looks_stale:
                frappe.cache().delete_value(self._tools_cache_key)
                try:
                    result = await self.session.call_tool(name, args)
                except Exception as e2:
                    return f"Error calling tool: {e2}"
            else:
                return f"Error calling tool: {e}"
        if isinstance(result.content, list):
            return "\n".join(str(item) for item in result.content)
        return str(result.content)

    async def _process_query(self, query: str, on_stage=None, is_cancelled=None, want_ui=False, reasoning_effort=None) -> dict:
        tools = await self._get_tools()
        try:
            result = await self.provider.process_query(
                query, tools, self.messages,
                on_stage=on_stage, is_cancelled=is_cancelled, want_ui=want_ui,
                reasoning_effort=reasoning_effort, thread_id=self.thread_id,
                call_tool=self._call_tool,
            )
            final_answer, updated_messages, usage, ui, tool_call_log, manifest = result
            if not final_answer:
                final_answer = "I'm sorry, I couldn't generate a response. Please try again."
            self.messages = updated_messages
            self._trim_history()
            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "ui": ui,
                "tool_calls": tool_call_log,
                "manifest": manifest,
            }
        finally:
            await self.cleanup()  # no-op if no tool was ever called this turn

    async def invoke(self, message: str, on_stage=None, is_cancelled=None, want_ui=False, reasoning_effort=None) -> dict:
        return await self._process_query(message, on_stage=on_stage, is_cancelled=is_cancelled, want_ui=want_ui, reasoning_effort=reasoning_effort)