import asyncio
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

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
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
                    "1. IDENTITY: You are AIKO, built specifically for Kofleetz fleet management. "
                    "Never describe yourself as a general AI or mention ERPNext, Frappe, or other platforms.\n"
                    "2. TOOLS ONLY: You MUST ONLY use the provided tools to fetch real data. "
                    "NEVER use internal knowledge to answer questions, explain concepts, or write code snippets.\n"
                    "3. NO GREETINGS: If the user sends a greeting (e.g., 'hi', 'hello', 'how are you', 'good morning'), "
                    "respond ONLY with: 'I am AIKO, an AI assistant for Kofleetz. I am not designed for greetings or small talk. "
                    "Please ask me about your Kofleetz operations, such as vehicles, trips, or fleet information.'\n"
                    "4. DATA REQUESTS: Always use the available tool to fetch real data from the Kofleetz database.\n"
                    "5. NO CAPABILITY: If you lack a tool to fulfill a request, clearly inform the user.\n"
                    "6. SUMMARIZE: Always summarize actual data received from tools clearly to the user."
                ),
            }
        ]
        self._load_history()

    def _load_history(self):
        session_name = frappe.db.get_value(
            "Aiko Chat Session", {"thread_id": self.thread_id}, "name"
        )
        if not session_name:
            return
        past_messages = frappe.db.get_list(
            "Aiko Chat Message",
            filters={
                "session": session_name,
                "role": ["in", ["user", "assistant"]],
            },
            fields=["role", "content"],
            order_by="creation asc",
            limit=MAX_HISTORY_MESSAGES,
        )

        for msg in past_messages:
            self.messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
            
    def _trim_history(self):
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            system_prompt = self.messages[0]
            self.messages = [system_prompt] + self.messages[-MAX_HISTORY_MESSAGES:]

    async def connect_to_streamable_http_server(self):
        """Connect to the Frappe MCP server"""
        user = frappe.session.user
        user_doc = frappe.get_doc("User", user)
        api_key = user_doc.api_key
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

    async def _process_query(self, query: str) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            result = await self.provider.process_query(query, self.session, self.messages)

            # Always expect 3-tuple: (text, messages, usage)
            final_answer, updated_messages, usage = result

            # Guard against empty response
            if not final_answer:
                final_answer = "I'm sorry, I couldn't generate a response. Please try again."

            self.messages = updated_messages
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        finally:
            await self.cleanup()

    def invoke(self, message: str) -> dict:
        """
        Synchronous wrapper for Frappe.
        Returns a dict: {content, input_tokens, output_tokens}
        """
        return asyncio.run(self._process_query(message))