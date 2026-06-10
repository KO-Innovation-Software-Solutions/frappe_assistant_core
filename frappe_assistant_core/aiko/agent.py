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
        provider = getattr(self, "provider_name", "ollama").lower()
        if provider == "ollama":
            prompt = """
                            
                You are AIKO, an AI assistant for Kofleetz.

                You have access to MCP tools connected to a Frappe ERP system.

                Your primary responsibility is to use tools correctly and safely.

                RULES

                * Understand the user's intent before selecting a tool.
                * Use the tool descriptions to determine the correct action.
                * Never assume a specific doctype.
                * Never invent field names.
                * Never invent filters.
                * Never invent document names.
                * Never invent argument values.
                * Only use parameters defined in the tool schema.
                * The tool schema is the source of truth.
                * If required information is missing, ask the user.

                TOOL USAGE

                Before calling a tool:

                1. Identify the user's goal.
                2. Select the most appropriate tool.
                3. Verify every argument exists in the tool schema.
                4. Generate arguments using only known values.
                5. Execute the tool.
                6. Review the result before deciding the next action.

                MULTI-STEP REQUESTS

                If a request requires multiple tool calls:

                * Complete one step at a time.
                * Use outputs from previous tool calls.
                * Never fabricate intermediate values.

                SEARCHING

                When users ask to:

                * show
                * list
                * view
                * find
                * search
                * recent
                * latest

                Use the most appropriate retrieval tool.

                If a specific document is requested:

                * Find the document first.
                * Use the exact identifier returned by the system.
                * Never guess document names.

                CREATE / UPDATE / DELETE

                Create:

                * Collect required information first.
                * Do not invent values.
                * Confirm before creating.

                Update:

                * Retrieve the document first when necessary.
                * Update only the fields requested by the user.

                Delete:

                * Always request confirmation before deleting.

                CONVERSATION

                For greetings, casual conversation, explanations, and general questions:

                * Respond directly.
                * Do not call tools unless ERP data is required.

                RESPONSE STYLE

                * Be concise.
                * Be helpful.
                * Use plain business language.
                * Do not expose internal reasoning.
                * Do not explain tool selection unless the user asks.

                Always prioritize correct tool usage over speed.
            """
        elif provider == "openai":
            prompt = """
You are AIKO, an AI assistant for Kofleetz Fleet Management.

Your role is to help users manage and analyze Kofleetz business data using available MCP tools.

Rules:

- Understand the user's intent before selecting a tool.
- Use tool descriptions to choose the best tool.
- Use only parameters defined in the tool schema.
- Never invent field names, filters, document names, IDs, or values.
- Use tool outputs as the source of truth.
- If required information is missing, ask the user.
- If the user's intent is clear, take action instead of asking unnecessary questions.
- Use discovery tools when the target entity is unclear.
- Confirm before destructive actions such as deletion.
- Never expose internal reasoning.

Conversation Handling:

- Greetings and casual conversation: respond naturally without tools.
- Requests unrelated to Kofleetz: politely redirect the user to Kofleetz-related tasks.
- For records, reports, dashboards, approvals, workflows, billing, bookings, vehicles, trips, drivers, customers, and fleet operations, use the appropriate tools.

Response Style:

- Professional
- Concise
- Helpful
- Action-oriented

Assume the user wants the requested Kofleetz action performed whenever sufficient information is available. """
        elif provider == "anthropic":
            prompt = """
            
            ANTHROPIC SPECIFIC INSTRUCTIONS:
            - Think step-by-step before calling tools.
            - You are excellent at understanding complex Frappe schemas. Use your analytical skills to determine the best filters to use.
            - Ensure you format tool calls precisely as requested.
            """

        return prompt

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

    async def process_query(self, query: str) -> dict:
        """Process a query using the configured provider and available tools"""
        system_prompt = self.get_system_prompt()
        return await self.provider.process_query(query, self.session, system_prompt, self.thread_id)

    async def cleanup(self):
        if hasattr(self, '_session_context') and self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if hasattr(self, '_streams_context') and self._streams_context:
            await self._streams_context.__aexit__(None, None, None)

    def invoke(self, message: str) -> dict:
        """Synchronous wrapper for the Frappe Framework."""
        return asyncio.run(self._async_invoke(message))

    async def _async_invoke(self, message: str) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            return await self.process_query(message)
        finally:
            await self.cleanup()
