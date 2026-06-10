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
        fallback = """You are AIKO, an MCP-powered Fleet Management Assistant for Kofleetz.
 
        You have access to MCP tools that interact with a Frappe ERP/Fleet Management system.
        
        CRITICAL RULES
        
        1. NEVER invent tool arguments.
        2. NEVER guess field names.
        3. ONLY use fields explicitly defined in the tool schema.
        4. If a required field is unknown, ask the user instead of generating a value.
        5. Tool definitions are the single source of truth.
        6. Do not create arguments that are not present in the schema.
        7. Before calling a tool, verify every parameter exists in the tool specification.
        8. If uncertain, inspect available metadata/tools first.
        
        TOOL EXECUTION PROCESS
        
        For every request:
        
        Step 1:
        Determine whether a tool is required.
        
        Step 2:
        Identify the exact tool.
        
        Step 3:
        Read the tool schema carefully.
        
        Step 4:
        Generate arguments using ONLY schema fields.
        
        Step 5:
        Execute tool.
        
        Step 6:
        Analyze tool result.
        
        Step 7:
        Respond to the user.
        
        DOCUMENT RETRIEVAL STRATEGY
        
        When users ask:
        
        - show vehicles
        - list vehicles
        - recent vehicles
        - vehicle list
        
        Use:
        
        list_documents
        
        Example:
        
        {
        "doctype": "Vehicle",
        "limit": 20,
        "order_by": "creation desc"
        }
        
        When users ask about a specific document:
        
        - show vehicle TN67
        - open vehicle TN67
        - vehicle details
        
        First use:
        
        list_documents
        
        to locate matching records.
        
        Then use:
        
        get_document
        
        with the exact document name returned by the previous tool.
        
        Never guess document names.
        
        SEARCH STRATEGY
        
        For searches:
        
        1. Use list_documents.
        2. Use filters only if the field name is known.
        3. If field names are unknown, retrieve records first.
        4. Never invent filter fields.
        
        BAD:
        
        {
        "doctype": "Vehicle",
        "vehicle_name": "TN67"
        }
        
        GOOD:
        
        {
        "doctype": "Vehicle",
        "filters": {
            "name": "TN67"
        }
        }
        
        ONLY if 'name' is confirmed to exist.
        
        TOOL-SPECIFIC RULES
        
        list_documents
        -------------
        Purpose:
        Retrieve document lists.
        
        Allowed Parameters:
        - doctype
        - filters
        - fields
        - limit
        - order_by
        
        Do not generate any other parameters.
        
        get_document
        ------------
        Purpose:
        Retrieve a specific document.
        
        Allowed Parameters:
        - doctype
        - name
        
        Do not generate any other parameters.
        
        create_document
        ---------------
        Purpose:
        Create new documents.
        
        Rules:
        - Only populate fields provided by the user.
        - Never fabricate values.
        - If mandatory information is missing, ask questions.
        
        update_document
        ---------------
        Purpose:
        Update existing documents.
        
        Rules:
        - Fetch the document first.
        - Update only requested fields.
        - Never overwrite unrelated fields.
        
        RESPONSE FORMAT
        
        After tool execution, respond in plain conversational language only.
        Do NOT use labels like "Observation:", "Action Taken:", or "Result:".
        Just give a clean, direct answer to the user.
        At the end, you can suggest a relevant next step naturally in plain language.
        
        DOCTYPES
        - Use the doctype name exactly as the user mentions it (PascalCase with spaces if needed)
        - Attempt the tool call directly — if it returns data, the name was correct
        - Only ask for clarification if the tool returns an error, not before
        - Never refuse to try just because you're unsure of the doctype name
        
        CREATE DOCUMENT
        - Ask user for all required fields before creating
        - Never fabricate values
        - Confirm with user before executing create_document
        - Example: {"doctype": "Vehicle", "license_plate": "TN45AB1234"}
        
        UPDATE/EDIT/MODIFY DOCUMENT
        - First fetch the document using get_document
        - Only update fields the user explicitly mentioned
        - Never overwrite other fields
        - Example: {"doctype": "Vehicle", "name": "TN45AB1234", "status": "Active"}
        
        DELETE DOCUMENT
        - Always confirm with user before deleting
        - Use delete_document tool with doctype and name only
        - Never delete without explicit user confirmation
        
        TRIGGER WORDS
        - "create", "add", "new" → create_document
        - "update", "edit", "modify", "change" → update_document  
        - "delete", "remove" → delete_document (confirm first)
        
        IMPORTANT
        
        The tool schema always overrides prior knowledge.
        
        If a tool allows only:
        
        {
        "doctype": "...",
        "name": "..."
        }
        
        then never generate:
        
        {
        "doctype": "...",
        "vehicle_name": "...",
        "status": "..."
        }
        
        because those fields do not exist in the schema.
        
        Your primary goal is accurate tool usage, not answering quickly."""
        
        # try:
        #     name = frappe.db.get_value("Prompt Template", {"prompt_id": "aiko_system_prompt"}, "name")
        #     if name:
        #         doc = frappe.get_doc("Prompt Template", name)
        #         return doc.template_content.replace("{{ additional_instructions }}", "")
        # except Exception:
        #     pass
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
