from __future__ import annotations

from typing import Optional
import urllib.parse

import frappe
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from frappe.utils import get_url

from frappe_assistant_core.aiko.providers import OpenAIProvider, OllamaProvider
from frappe_assistant_core.aiko.file_chat.file_handler import FileHandler, truncate

MAX_HISTORY_MESSAGES = 20


class AikoFileAgent:
    """File-capable agent — handles vision, PDF/image/CSV extraction, and DocType writes."""

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
                    "1. Never describe yourself as a general AI or mention ERPNext, Frappe, or other platforms.\n"
                    "2. ONLY use provided tools to fetch real data. Never use internal knowledge or generate fake/assumed data.\n"
                    "3. If tools return no results, tell the user — never fabricate or fill in placeholder values.\n"
                    "4. For greetings or small talk, respond only with: 'I am AIKO, an AI assistant for Kofleetz. Please ask me about your fleet operations.'\n"
                    "5. If you lack a tool to fulfill a request, clearly inform the user.\n"
                    "6. Always summarize tool results clearly to the user.\n\n"
                    "For file uploads: present extracted content completely — all fields, rows, amounts. "
                    "Never say a parser is needed or suggest the user write code. "
                    "Before calling any tool, check if the answer is already in this conversation "
                    "(e.g. a previously extracted file). Only call a tool when the info is genuinely absent."
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
            filters={"session": session_name, "role": ["in", ["user", "assistant"]]},
            fields=["role", "content"],
            order_by="creation asc",
            limit=MAX_HISTORY_MESSAGES,
        )
        for msg in past_messages:
            self.messages.append({"role": msg["role"], "content": msg["content"]})

    def _trim_history(self):
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            system_prompt = self.messages[0]
            self.messages = [system_prompt] + self.messages[-MAX_HISTORY_MESSAGES:]

    async def connect_to_streamable_http_server(self):
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
    # Vision / multimodal
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
            final_answer, _updated_messages, usage = await self.provider.process_query_with_messages(
                self.session, messages_with_file
            )
            if not final_answer:
                final_answer = "I'm sorry, I couldn't analyse the file. Please try again."
            self.messages.append({"role": "user", "content": f"[File: {file_name}] {message}"})
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
    # File extraction (PDF / image / CSV)
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
                ),
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
                doctype_updated = result.get("doctype_updated", doctype)
                self.messages.append({
                    "role": "user",
                    "content": (
                        f"[File: {file_name}] {message}\n\n"
                        f"[DocType update result: {doctype_updated}]"
                    ),
                })
                self.messages.append({"role": "assistant", "content": final_answer})
                self._trim_history()
                return {
                    "content": final_answer,
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                }

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
            messages_for_llm = [self.messages[0], {"role": "user", "content": full_prompt}]
            final_answer, _updated_messages, usage = await self.provider.process_query_with_messages(
                self.session, messages_for_llm
            )

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
    # Public entry points
    # ------------------------------------------------------------------ #

    async def invoke_with_file(
        self, message: str, file_data: str, file_type: str, file_name: str
    ) -> dict:
        return await self._process_query_with_file(message, file_data, file_type, file_name)

    async def invoke_with_file_extraction(
        self, message: str, file_url: str, operation: str, file_name: str
    ) -> dict:
        return await self._process_file_extraction_query(message, file_url, operation, file_name)