import asyncio
from typing import Optional
from contextlib import AsyncExitStack

import frappe
from frappe.utils import get_url
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import urllib.parse

from .providers.anthropic import AnthropicProvider
from .providers.openai import OpenAIProvider
from .providers.ollama import OllamaProvider

class AikoAgent:
    """Unified MCP Agent for Frappe"""

    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.settings = frappe.get_single("Assistant Core Settings")
        self.provider_name = self.settings.get("llm_provider", "Ollama").lower()
        
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # Initialize providers based on settings
        if self.provider_name == "anthropic":
            self.provider = AnthropicProvider(self.settings)
        elif self.provider_name == "openai":
            self.provider = OpenAIProvider(self.settings)
        else:
            self.provider = OllamaProvider(self.settings)

    def get_system_prompt(self) -> str:
        fallback = "You are AIKO, an AI assistant for Kofleetz. Use the provided tools to extract relevant information, and execute tasks. Every step needs to be well thought out."
        try:
            name = frappe.db.get_value("Prompt Template", {"prompt_id": "aiko_system_prompt"}, "name")
            if name:
                doc = frappe.get_doc("Prompt Template", name)
                return doc.template_content.replace("{{ additional_instructions }}", "")
        except Exception:
            pass
        return fallback

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

    async def process_query(self, query: str) -> str:
        """Process a query using the configured provider and available tools"""
        system_prompt = self.get_system_prompt()
        return await self.provider.process_query(query, self.session, system_prompt)

    async def cleanup(self):
        if hasattr(self, '_session_context') and self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if hasattr(self, '_streams_context') and self._streams_context:
            await self._streams_context.__aexit__(None, None, None)

    def invoke(self, message: str) -> str:
        """Synchronous wrapper for the Frappe Framework."""
        return asyncio.run(self._async_invoke(message))

    async def _async_invoke(self, message: str) -> str:
        await self.connect_to_streamable_http_server()
        try:
            return await self.process_query(message)
        finally:
            await self.cleanup()
