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
                    "You are an AI assistant connected to MCP tools. "
                    "Use available tools whenever needed. "
                    "Maintain conversational context and answer accurately."
                ),
            }
        ]

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

            # Providers may return (text, messages) or (text, messages, usage_dict)
            if len(result) == 3:
                final_answer, updated_messages, usage = result
            else:
                final_answer, updated_messages = result
                usage = {}

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