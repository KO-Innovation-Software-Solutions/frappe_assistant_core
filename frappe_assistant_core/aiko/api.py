import asyncio
import hashlib
import json
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe_assistant_core.aiko.agent import AikoAgent
from frappe_assistant_core.aiko.openui.dsl_manifest import rebuild_dsl, resolve_path, format_value
from frappe_assistant_core.core.tool_registry import get_tool_registry

def _cancel_key(request_id: str) -> str:
    return f"aiko_cancel_{request_id}"

def _mark_cancelled(request_id: str):
    """Set a short-lived cache flag so the background worker knows to stop."""
    frappe.cache().set_value(_cancel_key(request_id), 1, expires_in_sec=300)

def _is_cancelled(request_id: str) -> bool:
    """Check if the given request has been cancelled."""
    return bool(frappe.cache().get_value(_cancel_key(request_id)))

def _clear_cancel(request_id: str):
    frappe.cache().delete_value(_cancel_key(request_id))

@frappe.whitelist(methods=["POST"])
def cancel_chat(request_id: str):
    """Called by the frontend stop button. Sets a cache flag the worker polls."""
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    if not request_id:
        frappe.throw(_("request_id is required"))
    _mark_cancelled(request_id)
    return {"success": True}

def _get_active_llm_info(settings=None):
    """Return (provider, model) currently configured in Assistant Core Settings -> AIKO LLM tab."""
    settings = settings or frappe.get_single("Assistant Core Settings")
    provider = (settings.get("llm_provider") or "ollama").lower()

    if provider == "openai":
        model = settings.get("openai_model")
    elif provider == "ollama":
        model = settings.get("ollama_chat_model")
    else:
        model = settings.get("anthropic_model")

    return provider, model


def _get_or_create_session(thread_id: str, user: str):
    existing_name = frappe.db.get_value("Aiko Chat Session", {"thread_id": thread_id}, "name")
    if existing_name:
        return frappe.get_doc("Aiko Chat Session", existing_name)

    session = frappe.get_doc({
        "doctype": "Aiko Chat Session",
        "thread_id": thread_id,
        "user": user,
        "title": f"Chat {thread_id[:8]}",
        "message_count": 0,
    })
    try:
        session.insert(ignore_permissions=True)
    except frappe.db.IntegrityError:
        frappe.db.rollback()
        existing_name = frappe.db.get_value("Aiko Chat Session", {"thread_id": thread_id}, "name")
        if existing_name:
            return frappe.get_doc("Aiko Chat Session", existing_name)
        raise
    return session


def _save_message(session_id: str, role: str, content: str, input_tokens: int = 0, output_tokens: int = 0, llm_provider: str = None, llm_model: str = None):
    total = input_tokens + output_tokens
    msg = frappe.get_doc({
        "doctype": "Aiko Chat Message",
        "session": session_id,
        "role": role,
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    })
    msg.insert(ignore_permissions=True)
    return msg


def _update_session_meta(session, delta_messages: int = 1):
    """Bump message_count and refresh last_active."""
    frappe.db.set_value(
        "Aiko Chat Session",
        session.name,
        {
            "last_active": now_datetime(),
            "message_count": (session.message_count or 0) + delta_messages,
        },
        update_modified=False,
    )

@frappe.whitelist(methods=["POST"])
def save_stopped_message(thread_id: str, request_id: str = None):
    """Save a 'Response stopped' placeholder so it persists after refresh."""
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    user = frappe.session.user
    session = _get_or_create_session(thread_id, user)
    _save_message(session.name, role="assistant", content="_Response stopped._")
    _update_session_meta(session, delta_messages=1)
    frappe.db.commit()
    return {"success": True}

@frappe.whitelist()
def chat(message: str, thread_id: str, request_id: str = None):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    user = frappe.session.user
    request_id = request_id or frappe.generate_hash(length=10)

    try:
        frappe.enqueue(
            "frappe_assistant_core.aiko.api.run_chat_job_sync",
            queue="default",
            timeout=300,
            message=message,
            thread_id=thread_id,
            user=user,
            request_id=request_id,
        )
    except Exception:
        frappe.log_error(title="AIKO Chat Enqueue Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not start the request. Please try again."}

    return {
        "success": True,
        "queued": True,
        "thread_id": thread_id,
        "request_id": request_id,
    }
async def run_chat_job(message: str, thread_id: str, user: str, request_id: str):
    """
    Runs on the background worker. Executes the AIKO agent, publishing
    stage updates as it goes, then publishes the final answer.
    """
    frappe.set_user(user)

    async def on_stage(text):
        await asyncio.to_thread(
            frappe.publish_realtime,
            event="aiko_stage",
            message={"thread_id": thread_id, "request_id": request_id, "stage": text},
            user=user,
        )

    try:
        await on_stage("Reading your message…")
        settings = frappe.get_single("Assistant Core Settings")
        provider, model = _get_active_llm_info(settings)
        session = _get_or_create_session(thread_id, user)

        _save_message(
            session.name,
            role="user",
            content=message,
            llm_provider=provider,
            llm_model=model,
        )
        _update_session_meta(session, delta_messages=1)
        frappe.db.commit()
        # ─────────────────────────────────────────────────────────────────

        agent = AikoAgent(thread_id=thread_id)
        result = await agent.invoke(message, on_stage=on_stage, is_cancelled=lambda: _is_cancelled(request_id))
        if _is_cancelled(request_id):
            _clear_cancel(request_id)
            frappe.logger().info(f"AIKO request {request_id} was cancelled — skipping assistant save.")
            return

        response_text = result.get("content", "")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        tool_calls_snapshot = result.get("tool_calls", [])
        data_manifest = result.get("manifest", [])

        _save_message(
            session.name,
            role="assistant",
            content=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_provider=provider,
            llm_model=model,
        )
        _update_session_meta(session, delta_messages=1)
        frappe.db.commit()

        frappe.publish_realtime(
            event="aiko_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": True,
                "data": response_text,
                "session_name": session.name,
            },
            user=user,
        )

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="AIKO Chat Error", message=frappe.get_traceback())
        frappe.publish_realtime(
            event="aiko_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": False,
                "error": "Something went wrong while processing your message.",
            },
            user=user,
        )

def _get_or_create_dashboard_session(thread_id: str, user: str):
    existing_name = frappe.db.get_value("Aiko Dashboard Session", {"thread_id": thread_id}, "name")
    if existing_name:
        return frappe.get_doc("Aiko Dashboard Session", existing_name)

    session = frappe.get_doc({
        "doctype": "Aiko Dashboard Session",
        "thread_id": thread_id,
        "user": user,
        "title": f"Dashboard {thread_id[:8]}",
        "message_count": 0,
    })
    try:
        session.insert(ignore_permissions=True)
    except frappe.exceptions.DuplicateEntryError:
        frappe.db.rollback()
        existing_name = frappe.db.get_value("Aiko Dashboard Session", {"thread_id": thread_id}, "name")
        if existing_name:
            return frappe.get_doc("Aiko Dashboard Session", existing_name)
        raise
    return session


def _save_dashboard_message(session_id, role, content, ui=None, tool_calls_snapshot=None, data_manifest=None,
                             input_tokens=0, output_tokens=0, llm_provider=None, llm_model=None):
    total = input_tokens + output_tokens
    msg = frappe.get_doc({
        "doctype": "Aiko Dashboard Message",
        "session": session_id,
        "role": role,
        "content": content,
        "ui": ui,
        "tool_calls_snapshot": tool_calls_snapshot,
        "data_manifest": data_manifest,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    })
    msg.insert(ignore_permissions=True)
    return msg


def _update_dashboard_session_meta(session, delta_messages: int = 1):
    frappe.db.set_value(
        "Aiko Dashboard Session",
        session.name,
        {
            "last_active": now_datetime(),
            "message_count": (session.message_count or 0) + delta_messages,
        },
        update_modified=False,
    )


async def run_dashboard_job(message: str, thread_id: str, user: str, request_id: str):
    frappe.set_user(user)

    async def on_stage(text):
        await asyncio.to_thread(
            frappe.publish_realtime,
            event="aiko_dashboard_stage",
            message={"thread_id": thread_id, "request_id": request_id, "stage": text},
            user=user,
        )

    try:
        await on_stage("Reading your message…")
        settings = frappe.get_single("Assistant Core Settings")
        provider, model = _get_active_llm_info(settings)
        session = _get_or_create_dashboard_session(thread_id, user)

        _save_dashboard_message(
            session.name, role="user", content=message,
            llm_provider=provider, llm_model=model,
        )
        _update_dashboard_session_meta(session, delta_messages=1)
        frappe.db.commit()

        agent = AikoAgent(thread_id=thread_id, surface="dashboard")
        result = await agent.invoke(
            message, on_stage=on_stage,
            is_cancelled=lambda: _is_cancelled(request_id),
            want_ui=True,
        )
        if _is_cancelled(request_id):
            _clear_cancel(request_id)
            frappe.logger().info(f"AIKO dashboard request {request_id} was cancelled — skipping save.")
            return

        response_text = result.get("content", "")
        ui = result.get("ui")
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        tool_calls_snapshot = result.get("tool_calls", [])
        data_manifest = result.get("manifest", [])

        _save_dashboard_message(
            session.name, role="assistant", content=response_text, ui=ui,
            tool_calls_snapshot=json.dumps(tool_calls_snapshot),
            data_manifest=json.dumps(data_manifest),
            input_tokens=input_tokens, output_tokens=output_tokens,
            llm_provider=provider, llm_model=model,
        )
        _update_dashboard_session_meta(session, delta_messages=1)
        frappe.db.commit()

        frappe.publish_realtime(
            event="aiko_dashboard_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": True,
                "data": response_text,
                "ui": ui,
                "session_name": session.name,
            },
            user=user,
        )

    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="AIKO Dashboard Error", message=frappe.get_traceback())
        frappe.publish_realtime(
            event="aiko_dashboard_done",
            message={
                "thread_id": thread_id,
                "request_id": request_id,
                "success": False,
                "error": "Something went wrong while processing your message.",
            },
            user=user,
        )


def run_dashboard_job_sync(message: str, thread_id: str, user: str, request_id: str):
    asyncio.run(run_dashboard_job(message, thread_id, user, request_id))

@frappe.whitelist()
def list_dashboard_sessions(limit: int = 50):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    sessions = frappe.db.sql(
        """
        SELECT
            s.name, s.thread_id, s.title, s.last_active, s.message_count, s.creation,
            (SELECT m.content FROM `tabAiko Dashboard Message` m
             WHERE m.session = s.name AND m.role = 'user' ORDER BY m.creation DESC LIMIT 1) AS last_message,
            (SELECT m2.content FROM `tabAiko Dashboard Message` m2
             WHERE m2.session = s.name AND m2.role = 'user' ORDER BY m2.creation ASC LIMIT 1) AS first_message
        FROM `tabAiko Dashboard Session` s
        WHERE s.user = %s
        ORDER BY COALESCE(s.last_active, s.creation) DESC
        LIMIT %s
        """,
        (frappe.session.user, limit),
        as_dict=True,
    )
    for s in sessions:
        last_msg = (s.pop("last_message", None) or "").strip()
        first_msg = (s.pop("first_message", None) or "").strip()
        s["preview"] = last_msg or first_msg or ""
    return sessions


@frappe.whitelist()
def get_dashboard_session_messages(thread_id: str):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    session_name = frappe.db.get_value(
        "Aiko Dashboard Session",
        {"thread_id": thread_id, "user": frappe.session.user},
        "name",
    )
    if not session_name:
        return {"thread_id": thread_id, "messages": []}

    messages = frappe.db.get_list(
        "Aiko Dashboard Message",
        filters={"session": session_name},
        fields=["role", "content", "ui", "creation"],
        order_by="creation asc",
    )
    return {"thread_id": thread_id, "messages": messages}

@frappe.whitelist()
def dashboard_chat(message: str, thread_id: str, request_id: str = None):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))
    request_id = request_id or frappe.generate_hash(length=10)
    try:
        frappe.enqueue(
            "frappe_assistant_core.aiko.api.run_dashboard_job_sync",
            queue="default",
            timeout=300,
            message=message,
            thread_id=thread_id,
            user=frappe.session.user,
            request_id=request_id,
        )
    except Exception:
        frappe.log_error(title="AIKO Dashboard Enqueue Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not start the request. Please try again."}
    return {"success": True, "queued": True, "thread_id": thread_id, "request_id": request_id}

@frappe.whitelist()
def refresh_dashboard(thread_id: str):
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    session_name = frappe.db.get_value(
        "Aiko Dashboard Session", {"thread_id": thread_id, "user": frappe.session.user}, "name"
    )
    if not session_name:
        frappe.throw(_("No dashboard session found"))

    last_msg = frappe.db.get_list(
        "Aiko Dashboard Message",
        filters={"session": session_name, "role": "assistant"},
        fields=["name", "ui", "tool_calls_snapshot", "data_manifest"],
        order_by="creation desc",
        limit=1,
    )
    if not last_msg or not last_msg[0].get("ui"):
        frappe.throw(_("Nothing to refresh yet"))

    row = last_msg[0]
    ui = row["ui"]
    tool_calls = json.loads(row["tool_calls_snapshot"] or "[]")
    manifest = json.loads(row["data_manifest"] or "[]")

    if not tool_calls or not manifest:
        return {"success": False, "error": "No refreshable data recorded for this dashboard."}

    async def _run():
        agent = AikoAgent(thread_id=thread_id, surface="dashboard")
        await agent.connect_to_streamable_http_server()
        try:
            results = []
            for call in tool_calls:
                result = await agent.session.call_tool(call["name"], call["args"])
                if isinstance(result.content, list):
                    raw = "\n".join(str(item) for item in result.content)
                else:
                    raw = str(result.content)
                try:
                    results.append(json.loads(raw))
                except Exception:
                    results.append(raw)
            return results
        finally:
            await agent.cleanup()

    fresh_results = asyncio.run(_run())

    updates = {}
    for entry in manifest:
        t_idx = entry["tool_index"]
        if t_idx >= len(fresh_results):
            continue
        new_val = resolve_path(fresh_results[t_idx], entry["field_path"])
        if new_val is None:
            continue
        # Re-apply whatever formatting (currency symbol / thousands separator /
        # decimal rounding) the original literal had, so refresh doesn't just
        # dump a raw float where a formatted string used to be.
        formatted = format_value(new_val, entry.get("format"))
        updates[tuple(entry["path"])] = formatted

    try:
        new_ui = rebuild_dsl(ui, updates)
    except Exception:
        frappe.log_error(title="Dashboard Refresh Rebuild Error", message=frappe.get_traceback())
        return {"success": False, "error": "Could not rebuild dashboard from fresh data."}

    _save_dashboard_message(session_name, role="assistant", content="_Refreshed with latest data._", ui=new_ui)
    _update_dashboard_session_meta(frappe.get_doc("Aiko Dashboard Session", session_name))
    frappe.db.commit()

    return {"success": True, "ui": new_ui}


def _extract_ast_node_kind(node):
    """Return the (kind, payload) for any AST node, tolerating all plausible shapes.

    parse_program output varies across @openuidev/react-lang versions.  A node
    could be: a class instance with .k attribute + named attrs, a dict with a
    'k' key + other keys, a 2-tuple of (k, payload_dict), or a plain Python
    primitive.  This helper normalises all of them so we never lose args.
    """
    if node is None:
        return None, None, node
    # Plain Python primitive: already a value
    if isinstance(node, (str, int, float, bool)):
        return type(node).__name__, node, node
    # Dict shape: {"k": "Str", "v": "foo"}
    if isinstance(node, dict):
        k = node.get("k") or node.get("kind") or node.get("type")
        if isinstance(k, str):
            # Payload dict = whole node minus k/kind/type
            payload = dict(node)
            payload.pop("k", None)
            payload.pop("kind", None)
            payload.pop("type", None)
            return k, payload, node
        return None, None, node
    # Named-tuple / dataclass-ish instance: has .k attribute, other attrs
    k = getattr(node, "k", None) or getattr(node, "kind", None) or getattr(node, "type", None)
    if isinstance(k, str):
        payload = {}
        try:
            # dataclass / attrs
            from dataclasses import fields as _dc_fields
            for f in _dc_fields(node):
                payload[f.name] = getattr(node, f.name, None)
        except Exception:
            try:
                for attr in ("name", "args", "els", "entries", "left", "right",
                             "cond", "then", "else", "obj", "index", "operand",
                             "value", "v", "n", "id", "refType", "ref_type",
                             "statementId", "statement_id", "key"):
                    if hasattr(node, attr):
                        payload[attr] = getattr(node, attr)
            except Exception:
                pass
        try:
            # Final fallback: __dict__
            payload.update(vars(node))
        except Exception:
            pass
        return k, payload, node
    # 2-tuple AST representation: (kind_string, payload_dict)
    if isinstance(node, tuple) and len(node) == 2 and isinstance(node[0], str):
        return node[0], node[1] if isinstance(node[1], dict) else {"value": node[1]}, node
    return None, None, node


def _eval_as_str_literal(node) -> str | None:
    """If node is a Str/String AST node, return its plain Python string value.

    Known payload keys across parser versions: .v, .value, .text, .string, .s
    """
    k, payload, raw = _extract_ast_node_kind(node)
    if k in ("Str", "String", "StringLiteral", "string", "str", "Literal"):
        for key in ("v", "value", "text", "string", "s", "raw", "literal"):
            if key in payload and isinstance(payload[key], str):
                return payload[key]
        if isinstance(raw, str):
            return raw
    if isinstance(raw, str):
        return raw
    return None


def _evaluate_query_args_ast(ast_args, bindings=None):
    """Evaluate a simple AST (produced by parse_program's args object literal) to a
    plain Python dict/list.  Supports Str/Num/Bool/Null/Arr/Obj/StateRef/Ref and
    tolerates every plausible parser representation of those nodes.
    """
    bindings = bindings or {}
    k, payload, raw = _extract_ast_node_kind(ast_args)
    # ---- Literals
    s = _eval_as_str_literal(ast_args)
    if s is not None:
        return s
    if k in ("Num", "Number", "number", "NumericLiteral", "Int", "Float"):
        for key in ("v", "value", "n", "num", "number", "raw"):
            if key in payload and isinstance(payload[key], (int, float)):
                return payload[key]
        if isinstance(raw, (int, float)):
            return raw
    if k in ("Bool", "Boolean", "boolean", "BooleanLiteral"):
        for key in ("v", "value", "bool", "b"):
            if key in payload and isinstance(payload[key], bool):
                return payload[key]
        if isinstance(raw, bool):
            return raw
    if k in ("Null", "null", "Nil", "None", "undefined"):
        return None
    # ---- Array
    if k in ("Arr", "Array", "array", "list", "Tuple"):
        els = None
        for key in ("els", "elements", "items", "children", "values"):
            if key in payload:
                els = payload[key]
                break
        if els is None and isinstance(raw, (list, tuple)):
            els = list(raw)
        return [_evaluate_query_args_ast(el, bindings) for el in (els or [])]
    # ---- Object (dictionary) — THIS IS THE BLOCK THAT WAS BROKEN BEFORE.
    if k in ("Obj", "Object", "object", "Dict", "Record"):
        out = {}
        entries = None
        for key in ("entries", "properties", "props", "fields", "pairs", "members"):
            if key in payload:
                entries = payload[key]
                break
        if entries is None:
            # Last ditch: payload itself might BE the {key: val_ast} map already
            skip = {"k", "kind", "type", "name", "args", "els", "entries"}
            maybe = {k: v for k, v in payload.items() if k not in skip}
            if maybe:
                return {str(k): _evaluate_query_args_ast(v, bindings) for k, v in maybe.items()}
        for entry in (entries or []):
            # Every parser encodes (key, value) object entries differently:
            #   - Python tuple/list: (Str(key), value_ast)
            #   - Dict: {"key": Str, "value": val_ast}
            #   - Named node ObjProp: .key / .value attributes
            #   - Class with .k == "ObjProp" or .kind == "Property"
            entry_k, entry_payload, _ = _extract_ast_node_kind(entry)
            key_node = None
            val_node = None
            if entry_k in ("ObjProp", "Property", "prop", "KeyValue"):
                for kn in ("key", "name", "k", "id"):
                    if kn in entry_payload:
                        key_node = entry_payload[kn]
                        break
                for vn in ("value", "val", "v", "expr", "expression"):
                    if vn in entry_payload:
                        val_node = entry_payload[vn]
                        break
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                key_node, val_node = entry[0], entry[1]
            elif isinstance(entry, dict) and ("key" in entry or "name" in entry):
                key_node = entry.get("key") or entry.get("name")
                val_node = entry.get("value") or entry.get("val") or entry.get("expr")
            if key_node is None or val_node is None:
                continue
            # Turn key_node into a plain Python string.
            key_str = _eval_as_str_literal(key_node)
            if key_str is None:
                # Last ditch: .n attribute (for tokens that expose the key via .n)
                key_str = (getattr(key_node, "n", None)
                           or (isinstance(key_node, dict) and (key_node.get("n") or key_node.get("name")))
                           or None)
            if key_str is None:
                continue
            out[str(key_str)] = _evaluate_query_args_ast(val_node, bindings)
        return out
    if k in ("StateRef", "StateBinding", "$binding", "BindingRef"):
        # $binding reference — return the known value if any, else None marker
        n = payload.get("n") or payload.get("name") or payload.get("id")
        return bindings.get(n) if isinstance(n, str) else None
    if k in ("Ref", "Identifier", "identifier", "id", "ident"):
        return None
    # Unknown node — try one last fallback (already-a-plain-dict without k)
    if isinstance(raw, dict):
        return {str(k): _evaluate_query_args_ast(v, bindings) for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        return [_evaluate_query_args_ast(x, bindings) for x in raw]
    return None


def extract_unique_queries(dsl_src: str):
    """Walk the DSL and return a list of unique Query() calls.

    Two-pass, order-independent, dedup by stable SHA-1 over (tool_name, sorted args).

    Pass 1 (regex, always runs): Python literal eval / JSON normalisation of each
    `Query("tool_name", {...})` call from source text.  This reliably captures
    huge string args (SQL, descriptions) even when parse_program AST nodes have
    shapes our evaluator hasn't learned yet.

    Pass 2 (parse_program AST, optional, best-effort): Walks parse_program tree
    for more exact extraction, records `statement_id` for top-level declared
    Query bindings (enables targeted @Run(statementId) button clicks).  Results
    from both passes are merged — if a call is in regex pass already, the AST
    pass only enriches it with statement_id, never duplicates.
    """
    if not dsl_src or not isinstance(dsl_src, str):
        return []

    seen = {}
    ordered = []

    def _merge_in(tool_val, args_val, statement_id=None):
        if not tool_val:
            return None
        if not isinstance(args_val, dict):
            args_val = {}
        uses_bindings = _has_none_deep(args_val)
        try:
            raw_key = f"{tool_val}::{json.dumps(args_val, sort_keys=True, default=str)}"
        except Exception:
            raw_key = f"{tool_val}::{repr(args_val)}"
        key = hashlib.sha1(raw_key.encode()).hexdigest()
        if key not in seen:
            seen[key] = len(ordered)
            ordered.append({
                "key": key,
                "statement_id": statement_id,
                "tool": str(tool_val),
                "args": args_val,
                "uses_bindings": bool(uses_bindings),
                "occurrences": 0,
            })
        entry = ordered[seen[key]]
        entry["occurrences"] += 1
        if statement_id and not entry["statement_id"]:
            entry["statement_id"] = statement_id
        return entry

    # ---------------- PASS 1: regex (seeded, reliable for big literals) -----
    import re as _re
    import ast as _py_ast
    pattern = _re.compile(
        r'Query\(\s*[\"\']([A-Za-z_][A-Za-z0-9_]*)[\"\']\s*,\s*(\{.*?\})\s*\)',
        _re.DOTALL,
    )
    for m in pattern.finditer(dsl_src):
        tool_val = m.group(1)
        args_src = m.group(2)
        parsed_args = {}
        try:
            parsed_args = _py_ast.literal_eval(args_src)
            if not isinstance(parsed_args, dict):
                parsed_args = {}
        except Exception:
            try:
                import json as _json_native
                normalised = _re.sub(
                    r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:", r'"\1":', args_src)
                parsed_args = _json_native.loads(normalised)
                if not isinstance(parsed_args, dict):
                    parsed_args = {}
            except Exception:
                parsed_args = {}
        _merge_in(tool_val, parsed_args)

    # ---------------- PASS 2: parse_program AST (enrichment only) ----------
    try:
        from frappe_assistant_core.aiko.openui.dsl_manifest import parse_program
    except Exception:
        parse_program = None

    if parse_program is not None:
        try:
            parsed = parse_program(dsl_src)
            top_level = getattr(parsed, "statements", None) or []
            if not isinstance(top_level, (list, tuple)):
                top_level = list(top_level) if hasattr(top_level, "__iter__") else []

            def walk(node, statement_id=None):
                if node is None:
                    return
                k = getattr(node, "k", None) or (
                    node.get("k") if isinstance(node, dict) else None
                )
                name = getattr(node, "name", None) or (
                    node.get("name") if isinstance(node, dict) else None
                )
                # Comp node with name="Query"
                if k == "Comp" and name == "Query":
                    args = getattr(node, "args", None) or (
                        node.get("args") if isinstance(node, dict) else None
                    ) or []
                    if len(args) >= 2:
                        tool_val = _evaluate_query_args_ast(args[0]) or ""
                        args_val = _evaluate_query_args_ast(args[1]) or {}
                        if isinstance(args_val, dict) and args_val:
                            # Only merge in if the evaluator found REAL keys.
                            # If it returned {} for a call that regex pass
                            # already found with real keys, we'd clobber the
                            # cache key; _merge_in correctly dedupes if args
                            # match, or adds a new entry if they differ.
                            _merge_in(tool_val, args_val, statement_id)
                            return
                # Recurse — works with both attribute nodes and dict nodes.
                containers = []
                if hasattr(node, "args") and getattr(node, "args"):
                    containers.append(node.args)
                if hasattr(node, "els") and getattr(node, "els"):
                    containers.append(node.els)
                if hasattr(node, "entries") and getattr(node, "entries"):
                    entries = node.entries
                    containers.append(
                        [v for pair in entries for v in (
                            pair if isinstance(pair, (list, tuple)) and len(pair) > 1
                            else (getattr(pair, "value", None),
                                  getattr(pair, "key", None))
                        )]
                    )
                for fname in ("left", "right", "cond", "then", "else", "obj",
                              "index", "operand", "value", "expr", "test"):
                    if hasattr(node, fname):
                        containers.append([getattr(node, fname)])
                if isinstance(node, dict):
                    containers.append(list(node.values()))
                if isinstance(node, (list, tuple)):
                    containers.append(list(node))
                for container in containers:
                    if isinstance(container, (list, tuple)):
                        for child in container:
                            walk(child, statement_id)

            for stmt in top_level:
                # stmt can be dict or class; extract id + expr generically.
                stmt_id = (getattr(stmt, "id", None)
                           or (isinstance(stmt, dict) and stmt.get("id") or None))
                stmt_expr = (getattr(stmt, "expr", None) if getattr(stmt, "expr", None) is not None
                             else stmt)
                walk(stmt_expr, stmt_id)
        except Exception:
            # Parser walk is best-effort enrichment. If it fails, regex
            # extraction already populated ordered with every call we need.
            pass

    return ordered


def _has_none_deep(obj):
    if obj is None:
        return True
    if isinstance(obj, list):
        return any(_has_none_deep(x) for x in obj)
    if isinstance(obj, dict):
        return any(_has_none_deep(v) for v in obj.values())
    return False


class _DecoratedResultList(list):
    """A plain Python list subclass that also exposes read-only dict attrs.

    The AIKO DSL accesses Query() results in TWO incompatible ways, depending
    on the tool:

      * Row-list tools (list_documents / run_database_query): the whole
        Query() call must be ITERABLE so @Each / @Filter / @Count work. Each
        item in the list is a row with .name / .status / .vehicle etc.

      * Aggregation / chart tools (aggregate_documents / create_dashboard_chart):
        Query() is NOT iterated — instead it's accessed with dot-property:
        Query().label / Query().value / Query().groups.

    Frappe returns row-list tools as {"success": True, "data": [...], ...}.
    This class exposes:
      - `for x in obj:` / len(obj) / obj[0]  →  the list of rows (list semantics)
      - obj.label / obj["label"] / obj.data  →  the dict fields (dict semantics)
    """
    __slots__ = ("_attrs",)

    def __init__(self, iterable, attrs):
        super().__init__(iterable)
        object.__setattr__(self, "_attrs", attrs or {})

    def __getattr__(self, name):
        try:
            attrs = object.__getattribute__(self, "_attrs")
        except AttributeError:
            raise AttributeError(name)
        if name in attrs:
            return attrs[name]
        # Plural fallback: obj["labels"] -> obj.label list aliases etc.
        if name == "labels" and "label" in attrs:
            return attrs["label"]
        if name == "values" and "value" in attrs:
            return attrs["value"]
        raise AttributeError(
            f"'DecoratedResultList' object has no attribute {name!r}"
        )

    def __getitem__(self, idx_or_key):
        if isinstance(idx_or_key, str):
            return object.__getattribute__(self, "_attrs")[idx_or_key]
        return super().__getitem__(idx_or_key)

    def __contains__(self, x):
        try:
            if x in object.__getattribute__(self, "_attrs"):
                return True
        except Exception:
            pass
        return super().__contains__(x)

    def __len__(self):
        return super().__len__()

    def __iter__(self):
        return super().__iter__()

    # JSON serialisation: always emit the list form for wire transport.
    # Decorated keys are transparently re-added by the frontend decoder
    # because the transport envelope carries them as sibling keys per Query.
    def __json__(self):
        return list(self)


def _normalise_tool_result_for_querymap(tool_name: str, raw_result):
    """Normalise raw tool return values into the shape the DSL expects.

    Returns (result_for_querymap, decorated_info_for_frontend).  The first
    value is what we cache in query_map[key] (and thus becomes the "resolved"
    value of Query(...)).  The second is a dict of extra attributes the DSL
    accesses via .label / .value etc. on the result.
    """
    if not isinstance(raw_result, dict):
        return raw_result, {}

    info = dict(raw_result)
    # --- Row-list tools: unwrap to list of rows, keep attr aliases --------
    if tool_name in ("list_documents", "run_database_query", "search_documents",
                     "search_doctype", "get_pending_approvals"):
        rows = info.get("data")
        if isinstance(rows, list):
            decorated = _DecoratedResultList(rows, info)
            return decorated, info
        return raw_result, info

    # --- Aggregate + chart tools: keep as dict, but wrap with list-like length
    # (for @Count over Query(...) if the DSL ever uses that form, plus allow
    # .label / .value to work on dict form.)
    return raw_result, info


@frappe.whitelist()
def refresh_dashboard_queries(thread_id: str, legacy_fallback: bool = True):
    """Strategy-A refresh: run every unique Query() via ToolRegistry directly.

    * NO LLM call
    * NO MCP server round trip
    * Same permission checks as always (ToolRegistry enforces role + FAC config)
    * Dedups identical Query() references automatically (one SQL per signature)

    Response shape:
        { success: bool,
          ui?: string,        # legacy literal-refreshed UI (if any literal-refreshable values found)
          queryMap: { [sha1_key]: any },   # raw JSON per unique Query result
          queries: [...extracted metadata],
          refreshed_at: ISO timestamp,
          callouts_timestamped: bool }
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"))

    session_name = frappe.db.get_value(
        "Aiko Dashboard Session",
        {"thread_id": thread_id, "user": frappe.session.user},
        "name",
    )
    if not session_name:
        frappe.throw(_("No dashboard session found"))

    last_msg = frappe.db.get_list(
        "Aiko Dashboard Message",
        filters={"session": session_name, "role": "assistant"},
        fields=["name", "ui", "tool_calls_snapshot", "data_manifest", "creation"],
        order_by="creation desc",
        limit=1,
    )
    if not last_msg or not last_msg[0].get("ui"):
        return {"success": False, "error": "Nothing to refresh yet"}

    row = last_msg[0]
    ui = row["ui"]
    refreshed_at = now_datetime().isoformat()

    # --- Phase 1: Extract + run unique queries (Strategy A) --------------
    queries = extract_unique_queries(ui)
    registry = get_tool_registry()
    query_map = {}
    failed = []

    for q in queries:
        if not q["tool"] or q["uses_bindings"]:
            continue
        try:
            raw = registry.execute_tool(q["tool"], q["args"] or {})
            # ToolRegistry has already peeled off a .result wrapper if the
            # tool used the success+result convention.  Now normalise further.
            result_for_map, _info = _normalise_tool_result_for_querymap(q["tool"], raw)
            query_map[q["key"]] = result_for_map
            # Probe JSON-safety; any bad types coerce via default=str.  (The
            # DecoratedResultList subclass is _not_ serialised directly; it's
            # converted to plain list automatically via default handler below.)
            try:
                json.dumps(query_map[q["key"]], default=str)
            except Exception:
                query_map[q["key"]] = json.loads(json.dumps(query_map[q["key"]], default=str))
        except Exception as e:
            failed.append({"key": q["key"], "tool": q["tool"], "error": str(e)})

    # --- Phase 2 (optional legacy pipeline): Run old rebuild_dsl for literals.
    # This ONLY updates dashboards where the LLM previously baked literal
    # numbers (Fuel Entry / Asset Movements style).  It does NOT touch Query
    # nodes — build_manifest explicitly skips them today, so the two paths
    # don't fight each other.
    new_ui = None
    if legacy_fallback:
        try:
            tool_calls = json.loads(row["tool_calls_snapshot"] or "[]")
            manifest = json.loads(row["data_manifest"] or "[]")
            if tool_calls and manifest:
                async def _legacy_run():
                    agent = AikoAgent(thread_id=thread_id, surface="dashboard")
                    await agent.connect_to_streamable_http_server()
                    try:
                        results = []
                        for call in tool_calls:
                            res = await agent.session.call_tool(call["name"], call["args"])
                            raw = ("\n".join(str(i) for i in res.content)
                                   if isinstance(res.content, list) else str(res.content))
                            try:
                                results.append(json.loads(raw))
                            except Exception:
                                results.append(raw)
                        return results
                    finally:
                        await agent.cleanup()

                fresh_results = asyncio.run(_legacy_run())
                updates = {}
                for entry in manifest:
                    t_idx = entry["tool_index"]
                    if t_idx >= len(fresh_results):
                        continue
                    new_val = resolve_path(fresh_results[t_idx], entry["field_path"])
                    if new_val is None:
                        continue
                    updates[tuple(entry["path"])] = format_value(new_val, entry.get("format"))
                if updates:
                    new_ui = rebuild_dsl(ui, updates)
        except Exception:
            new_ui = None  # Don't fail the whole endpoint on legacy errors.

    return {
        "success": True,
        "ui": new_ui,                   # legacy literal-refreshed UI (or None)
        "queryMap": query_map,          # strategy-A fresh data per unique Query
        "queries": queries,             # metadata per Query (debug / frontend cache)
        "refreshed_at": refreshed_at,   # for the "based on data from [time]" label on callouts
        "callouts_timestamped": True,
        "failed": failed,
    }


def run_chat_job_sync(message: str, thread_id: str, user: str, request_id: str):
    """Sync entry point for Frappe's background worker."""
    asyncio.run(run_chat_job(message, thread_id, user, request_id))