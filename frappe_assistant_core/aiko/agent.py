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
        
        # Determine provider based on settings
        provider_name = self.settings.get("llm_provider", "ollama").lower()
        if provider_name == "openai":
            self.provider = OpenAIProvider(self.settings)
        else:
            # Fallback to Ollama for anything else (anthropic can be added later)
            self.provider = OllamaProvider(self.settings)
        
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None
        
        self.cache_key = f"aiko_history_{self.thread_id}"
        self.messages = frappe.cache().get_value(self.cache_key) or [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant connected to MCP tools. "
                    "Use available tools whenever needed. "
                    "Maintain conversational context and answer accurately."
                ),
            }
        ]

    def _save_history(self):
        frappe.cache().set_value(self.cache_key, self.messages, expires_in_sec=86400) # 24 hours

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
            internal_url = internal_url.replace("127.0.0.1", f"127.0.0.1:{frappe.conf.webserver_port or 8000}")
            
        headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Host": parsed.hostname
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

    async def _process_query(self, query: str) -> str:
        await self.connect_to_streamable_http_server()
        try:
            final_answer, updated_messages = await self.provider.process_query(query, self.session, self.messages)
            self.messages = updated_messages
            self._trim_history()
            self._save_history()
            return final_answer
        finally:
            await self.cleanup()

    def invoke(self, message: str) -> str:
        """
        Synchronous wrapper for Frappe to call the async agent flow.
        """
        return asyncio.run(self._process_query(message))
