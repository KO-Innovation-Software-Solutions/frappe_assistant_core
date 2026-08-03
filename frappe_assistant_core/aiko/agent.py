from typing import Optional
import urllib.parse

import frappe
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from frappe.utils import get_url

from .providers import OpenAIProvider, OllamaProvider

MAX_HISTORY_MESSAGES = 20

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
                    "6. Always summarize tool results clearly to the user.\n"
                    "7. For chart-worthy data (comparisons, trends, distributions, rankings), add a fenced "
                        "```chart block (not ```json) with JSON built from real data:\n"
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

    async def cleanup(self):
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

    async def _process_query(self, query: str, on_stage=None, is_cancelled=None, want_ui=False) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            result = await self.provider.process_query(
                query, self.session, self.messages,
                on_stage=on_stage, is_cancelled=is_cancelled, want_ui=want_ui,
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
            await self.cleanup()

    async def invoke(self, message: str, on_stage=None, is_cancelled=None, want_ui=False) -> dict:
        return await self._process_query(message, on_stage=on_stage, is_cancelled=is_cancelled, want_ui=want_ui)