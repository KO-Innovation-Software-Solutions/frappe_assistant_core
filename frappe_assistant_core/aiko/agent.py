from typing import Optional
import urllib.parse

import frappe
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from frappe.utils import get_url

from .providers import OpenAIProvider, OllamaProvider
from .file_handler import FileHandler, truncate

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
                    "You are an AI assistant integrated with Frappe via MCP tools. "
                    "When you receive a file extraction result, you MUST present the "
                    "extracted content directly and completely in your reply — all fields, "
                    "all table rows, all amounts. Never say a custom parser or script is "
                    "needed. Never say you cannot process the content. Never suggest the "
                    "user install tools or write code. The extraction is already done — "
                    "your job is to read it and present it clearly.\n\n"
                    "BEFORE calling any tool, always check whether the question can already "
                    "be answered from THIS CONVERSATION's own history — for example, a "
                    "previously extracted file's text, a table you already presented, "
                    "amounts, names, or line items shown earlier. If the user asks a "
                    "follow-up about something already extracted or discussed (e.g. 'item "
                    "details', 'the prices', 'how many', 'total'), answer directly from the "
                    "earlier content in this conversation. Do NOT call a tool just because a "
                    "word in the question (like 'item') resembles the name of a Frappe "
                    "DocType or report — the user is almost always referring to data already "
                    "in this conversation, not asking you to look up Frappe's Item/Stock "
                    "module. Only call a tool when the requested information is genuinely "
                    "not available anywhere earlier in this conversation.\n\n"
                    "For all other tasks where the answer truly isn't already in this "
                    "conversation, use available MCP tools as needed and answer accurately."
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
            order_by="creation desc",
            limit=MAX_HISTORY_MESSAGES,
        )
        for msg in reversed(past_messages):
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

    # ------------------------------------------------------------------ #
    # Plain-text query
    # ------------------------------------------------------------------ #

    async def _process_query(self, query: str, on_stage=None) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            result = await self.provider.process_query(
                query, self.session, self.messages, on_stage=on_stage
            )
            final_answer, updated_messages, usage = result

            if not final_answer:
                final_answer = "I'm sorry, I couldn't generate a response. Please try again."
                frappe.log_error(
                    title="AIKO Empty LLM Response",
                    message=(
                        f"Provider returned an empty final answer with no tool result to "
                        f"fall back on. thread_id={self.thread_id}, "
                        f"provider={type(self.provider).__name__}, "
                        f"message_count={len(updated_messages)}"
                    ),
                )

            self.messages = updated_messages
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        finally:
            await self.cleanup()

    # ------------------------------------------------------------------ #
    # Vision / multimodal query
    # ------------------------------------------------------------------ #

    async def _process_query_with_file(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            fh = FileHandler(self.provider, self.session, self.messages, self.thread_id)
            multimodal_message = fh.build_multimodal_message(
                message, file_data, file_type, file_name
            )
            messages_with_file = self.messages + [multimodal_message]

            result = await self.provider.process_query_with_messages(
                self.session, messages_with_file
            )
            final_answer, updated_messages, usage = result

            if not final_answer:
                final_answer = "I'm sorry, I couldn't analyse the file. Please try again."

            self.messages.append({
                "role": "user",
                "content": f"[File: {file_name}] {message}",
            })
            self.messages.append({"role": "assistant", "content": final_answer})
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "doctype_updated": usage.get("doctype_updated", ""),
            }
        finally:
            await self.cleanup()

    # ------------------------------------------------------------------ #
    # File extraction query (PDF / image / CSV via extract_file_content)
    # ------------------------------------------------------------------ #

    async def _process_file_extraction_query(
        self, message: str, file_url: str, operation: str, file_name: str
    ) -> dict:
        await self.connect_to_streamable_http_server()
        try:
            fh = FileHandler(self.provider, self.session, self.messages, self.thread_id)

            display_content, note, plain_text = await fh.extract(file_url, operation)

            extraction_ok = not plain_text.startswith("[")

            frappe.log_error(
                title="AIKO file extraction fast-path check",
                message=(
                    f"file_name={file_name} operation={operation}\n"
                    f"extraction_ok={extraction_ok}\n"
                    f"plain_text[:300]={plain_text[:300]}"
                )
            )

            if not extraction_ok:
                final_answer = (
                    f"Sorry, I could not extract text from **{file_name}**.\n\n"
                    f"Reason: {plain_text}\n\n"
                    f"Please check the Frappe error log (titled 'AIKO extract_file_content') "
                    f"for the full details."
                )
                self.messages.append({"role": "user", "content": f"[File: {file_name}] {message}"})
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()
                return {"content": final_answer, "input_tokens": 0, "output_tokens": 0}

            # Fast path — display only
            if fh.is_display_only(message):
                display_header = f"Here is the extracted content of **{file_name}**:\n\n"
                if note:
                    display_header += f"_{note.strip()}_\n\n"
                final_answer = display_header + display_content

                self.messages.append({
                    "role": "user",
                    "content": (
                        f"[File: {file_name}] {message}\n\n"
                        f"[Extracted content was provided directly for this turn.]"
                    ),
                })
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()
                return {"content": final_answer, "input_tokens": 0, "output_tokens": 0}

            # DocType update path
            doctype_intent = fh.detect_doctype_intent(message)
            if doctype_intent is not None:
                doctype, field_map, record_name = doctype_intent
                result = await fh.update_doctype(
                    message=message,
                    extracted_text=plain_text,
                    doctype=doctype,
                    field_map=field_map,
                    record_name=record_name,
                    file_name=file_name,
                )
                final_answer = result.get("content", "")
                usage = {
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                }
                self.messages.append({
                    "role": "user",
                    "content": (
                        f"[File: {file_name}] {message}\n\n"
                        f"[DocType update attempted for: {doctype}]"
                    ),
                })
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()
                return {
                    "content": final_answer,
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                }

            # Slow path — LLM reasoning over extracted text
            truncated = truncate(plain_text)
            full_prompt = (
                f"A file named '{file_name}' was uploaded. The system has ALREADY "
                f"extracted its full content — do NOT call extract_file_content "
                f"yourself. Present every field, every line, every amount "
                f"completely. Never say the content can't be processed. If the "
                f"extracted content below already contains '**Label:** Value' "
                f"lines, reproduce them exactly as given, one per line — do NOT "
                f"rewrite them into prose or a table.\n\n"
                f"{note}"
                f"--- EXTRACTED FILE CONTENT START ---\n"
                f"{truncated}\n"
                f"--- EXTRACTED FILE CONTENT END ---\n\n"
                f"Only call a tool to create/update a Frappe record if the user's "
                f"request explicitly contains 'create', 'save', 'insert', or 'add to' "
                f"followed by a DocType name. Otherwise answer from the content above.\n\n"
                f"User request: {message}"
            )

            system_msg = self.messages[0]
            messages_for_llm = [system_msg, {"role": "user", "content": full_prompt}]

            result = await self.provider.process_query_with_messages(
                self.session, messages_for_llm
            )
            final_answer, _updated_messages, usage = result

            if not final_answer or final_answer.strip().startswith("I'm sorry"):
                if plain_text and not plain_text.startswith("[No content"):
                    final_answer = (
                        f"Here is the extracted content of **{file_name}**"
                        f"{' (' + note.strip() + ')' if note else ''}:\n\n"
                        f"{display_content}"
                    )
                else:
                    final_answer = display_content or (
                        "I'm sorry, I couldn't generate a response. Please try again."
                    )

            self.messages.append({
                "role": "user",
                "content": (
                    f"[File: {file_name}] {message}\n\n"
                    f"[Extracted content was provided to the assistant for this turn.]"
                ),
            })
            self.messages.append({"role": "assistant", "content": final_answer})
            self._trim_history()

            return {
                "content": final_answer,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        finally:
            await self.cleanup()

    # ------------------------------------------------------------------ #
    # Public sync wrappers
    # ------------------------------------------------------------------ #

    def invoke(self, message: str, on_stage=None) -> dict:
        """Synchronous wrapper for plain-text queries."""
        import asyncio
        return asyncio.run(self._process_query(message, on_stage=on_stage))

    def invoke_with_file(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        """Synchronous wrapper for vision / multimodal queries."""
        import asyncio
        return asyncio.run(
            self._process_query_with_file(message, file_data, file_type, file_name)
        )

    def invoke_with_file_extraction(
        self, message: str, file_url: str, operation: str, file_name: str
    ) -> dict:
        """Synchronous wrapper for document extraction queries.

        Calls extract_file_content deterministically before touching the LLM,
        removing the entire class of failures where a small local model ignores
        the extraction instruction and calls an unrelated tool instead.
        """
        import asyncio
        return asyncio.run(
            self._process_file_extraction_query(message, file_url, operation, file_name)
        )