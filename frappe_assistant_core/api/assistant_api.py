# Frappe Assistant Core - AI Assistant integration for Frappe Framework
# Copyright (C) 2025 Paul Clinton
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Clean refactored Assistant API with modular handlers and proper logging
"""

from typing import Any, Dict, Optional

import frappe
from frappe import _

from frappe_assistant_core.utils.logger import api_logger


@frappe.whitelist(methods=["GET", "POST"])
def get_usage_statistics() -> Dict[str, Any]:
    """Get usage statistics for the assistant"""
    try:
        # SECURITY: Handle both session-based and token-based authentication
        authenticated_user = _authenticate_request()
        if not authenticated_user:
            api_logger.warning("Usage statistics requested without valid authentication")
            frappe.throw(_("Authentication required"))

        # SECURITY: Restrict global usage statistics to assistant admins
        from frappe_assistant_core.utils.permissions import check_assistant_admin_permission

        user_roles = frappe.get_roles(authenticated_user)
        api_logger.debug(f"User {authenticated_user} has roles: {user_roles}")

        if not check_assistant_admin_permission(authenticated_user):
            api_logger.warning(
                f"Usage statistics denied for non-admin user: {authenticated_user} with roles: {user_roles}"
            )
            frappe.throw(_("Access denied - administrator permissions required"))

        api_logger.info(f"Usage statistics requested by user: {authenticated_user}")
        api_logger.info(f"Current site: {frappe.local.site}")

        # Get actual usage statistics
        today = frappe.utils.today()
        week_start = frappe.utils.add_days(today, -7)

        # Connection statistics are no longer tracked (Assistant Connection Log removed)
        # Using audit log activity as a proxy for connection activity
        try:
            total_connections = frappe.db.count("Assistant Audit Log") or 0
            today_connections = frappe.db.count("Assistant Audit Log", {"creation": (">=", today)}) or 0
            week_connections = frappe.db.count("Assistant Audit Log", {"creation": (">=", week_start)}) or 0
        except Exception as e:
            api_logger.warning(f"Connection stats error: {e}")
            total_connections = today_connections = week_connections = 0

        # Audit log statistics with error handling
        try:
            total_audit = frappe.db.count("Assistant Audit Log") or 0
            today_audit = frappe.db.count("Assistant Audit Log", {"creation": (">=", today)}) or 0
            week_audit = frappe.db.count("Assistant Audit Log", {"creation": (">=", week_start)}) or 0
        except Exception as e:
            api_logger.warning(f"Audit stats error: {e}")
            total_audit = today_audit = week_audit = 0

        # Tool statistics from plugin manager
        try:
            from frappe_assistant_core.utils.plugin_manager import get_plugin_manager

            plugin_manager = get_plugin_manager()
            all_tools = plugin_manager.get_all_tools()
            total_tools = len(all_tools)
            enabled_tools = len(all_tools)  # All loaded tools are enabled
            api_logger.debug(f"Tool stats: total={total_tools}, enabled={enabled_tools}")
        except Exception as e:
            api_logger.warning(f"Tool stats error: {e}")
            total_tools = enabled_tools = 0

        # Recent activity with error handling
        try:
            recent_activity = (
                frappe.db.get_list(
                    "Assistant Audit Log",
                    fields=["action", "tool_name", "user", "status", "timestamp"],
                    order_by="timestamp desc",
                    limit=10,
                )
                or []
            )
        except Exception as e:
            api_logger.warning(f"Recent activity error: {e}")
            recent_activity = []

        # Return statistics in the format expected by frontend
        result = {
            "success": True,
            "data": {
                "connections": {
                    "total": total_connections,
                    "today": today_connections,
                    "this_week": week_connections,
                },
                "audit_logs": {"total": total_audit, "today": today_audit, "this_week": week_audit},
                "tools": {"total": total_tools, "enabled": enabled_tools},
                "recent_activity": recent_activity,
            },
        }

        api_logger.debug(f"Usage statistics result: {result}")
        return result

    except Exception as e:
        api_logger.error(f"Error getting usage statistics: {e}")
        return {"success": False, "error": str(e)}


@frappe.whitelist(methods=["GET", "POST"])
def ping() -> Dict[str, Any]:
    """Ping endpoint for testing connectivity"""
    try:
        # SECURITY: Handle both session-based and token-based authentication
        authenticated_user = _authenticate_request()
        if not authenticated_user:
            frappe.throw(_("Authentication required"))

        # SECURITY: Check if user has assistant access
        from frappe_assistant_core.utils.permissions import check_assistant_permission

        if not check_assistant_permission(authenticated_user):
            frappe.throw(_("Access denied"))

        return {
            "success": True,
            "message": "pong",
            "timestamp": frappe.utils.now(),
            "user": authenticated_user,
        }

    except Exception as e:
        api_logger.error(f"Error in ping: {e}")
        return {"success": False, "message": f"Ping failed: {str(e)}"}


def _authenticate_request() -> Optional[str]:
    """
    Handle session-based, OAuth2.0 Bearer token, and API key authentication
    Returns the authenticated user or None if authentication fails

    Note: OAuth2.0 Bearer tokens are automatically validated by Frappe's auth system
    and frappe.session.user is set before this function is called
    """

    # Check if user is already authenticated (covers session and OAuth2.0 Bearer tokens)
    if frappe.session.user and frappe.session.user != "Guest":
        # Check if user has assistant access enabled
        if not _check_assistant_enabled(frappe.session.user):
            api_logger.warning(f"User {frappe.session.user} has assistant access disabled")
            return None

        auth_header = frappe.get_request_header("Authorization", "") or ""
        if auth_header.startswith("Bearer "):
            api_logger.debug(f"OAuth2.0 Bearer token authentication successful: {frappe.session.user}")
        else:
            api_logger.debug(f"Session authentication successful: {frappe.session.user}")
        return frappe.session.user

    # Fallback to API key authentication for legacy clients
    auth_header = frappe.get_request_header("Authorization")
    api_logger.debug(f"Authorization header present: {bool(auth_header)}")

    if auth_header and auth_header.startswith("token "):
        try:
            # Extract token from "token api_key:api_secret" format
            token_part = auth_header[6:]  # Remove "token " prefix
            if ":" in token_part:
                api_key, api_secret = token_part.split(":", 1)
                api_logger.debug("API key extracted from token header")

                # Custom validation using database lookup and password verification
                user_data = frappe.db.get_value(
                    "User", {"api_key": api_key, "enabled": 1}, ["name", "api_secret"]
                )

                api_logger.debug(f"User data found: {bool(user_data)}")

                if user_data:
                    user, _ = user_data
                    # Compare the provided secret with stored secret
                    from frappe.utils.password import get_decrypted_password

                    decrypted_secret = get_decrypted_password("User", user, "api_secret")

                    if api_secret == decrypted_secret:
                        # Check if user has assistant access enabled
                        if not _check_assistant_enabled(str(user)):
                            api_logger.warning(f"User {user} has assistant access disabled")
                            return None

                        # Set user context for this request
                        # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser — user authenticated via API key:secret comparison above
                        frappe.set_user(str(user))
                        api_logger.debug(f"API key authentication successful: {user}")
                        return str(user)
                    else:
                        api_logger.debug("API secret mismatch")
                else:
                    api_logger.debug("No user found with provided API key")

        except Exception as e:
            api_logger.error(f"API key authentication failed: {e}")
    else:
        api_logger.debug("No valid authorization header found")

    api_logger.debug("Authentication failed")
    return None


@frappe.whitelist(methods=["GET", "POST"])
def get_chat_sessions() -> Dict[str, Any]:
    """Get all chat sessions for the current user, with last message preview (WhatsApp style)"""
    try:
        authenticated_user = _authenticate_request()
        if not authenticated_user:
            frappe.throw(_("Authentication required"))

        # Fetch sessions for this user, newest first
        sessions = frappe.db.get_list(
            "Aiko Chat Session",
            filters={"user": authenticated_user},
            fields=["name", "thread_id", "title", "last_active", "message_count"],
            order_by="last_active desc",
            limit=50,
        )

        # For each session, get the last message as preview
        for session in sessions:
            last_msg = frappe.db.get_list(
                "Aiko Chat Message",
                filters={"session": session["name"]},
                fields=["role", "content", "creation"],
                order_by="creation desc",
                limit=1,
            )
            if last_msg:
                session["preview"] = last_msg[0]["content"][:80]
                session["preview_role"] = last_msg[0]["role"]
                session["preview_time"] = last_msg[0]["creation"]
            else:
                session["preview"] = "No messages yet"
                session["preview_role"] = ""
                session["preview_time"] = session["last_active"]

        return {"success": True, "sessions": sessions}

    except Exception as e:
        api_logger.error(f"Error getting chat sessions: {e}")
        return {"success": False, "error": str(e)}


@frappe.whitelist(methods=["GET", "POST"])
def get_session_messages(session_name: str, limit: int = 20, before_creation: str = None) -> Dict[str, Any]:
    """
    Get messages for a session with pagination.
    Returns last `limit` messages, or messages older than `before_creation` for scroll-up loading.
    """
    try:
        authenticated_user = _authenticate_request()
        if not authenticated_user:
            frappe.throw(_("Authentication required"))

        # Verify session belongs to this user
        session_user = frappe.db.get_value("Aiko Chat Session", session_name, "user")
        if session_user != authenticated_user:
            frappe.throw(_("Access denied"))

        filters = {"session": session_name}
        if before_creation:
            filters["creation"] = ("<", before_creation)

        messages = frappe.db.get_list(
            "Aiko Chat Message",
            filters=filters,
            fields=["name", "role", "content", "creation"],
            order_by="creation desc",
            limit=int(limit) + 1,  # fetch one extra to know if there are more
        )

        has_more = len(messages) > int(limit)
        if has_more:
            messages = messages[:int(limit)]

        # Reverse so oldest is first (chronological order for display)
        messages.reverse()

        return {
            "success": True,
            "messages": messages,
            "has_more": has_more,
        }

    except Exception as e:
        api_logger.error(f"Error getting session messages: {e}")
        return {"success": False, "error": str(e)}


def _check_assistant_enabled(user: str) -> bool:
    """
    Check if the assistant_enabled field is enabled for the user.

    Single source of truth is utils.token_limits.is_assistant_enabled().
    Agreed default: column missing -> open; value NULL/0 -> disabled.
    """
    from frappe_assistant_core.utils.token_limits import is_assistant_enabled

    is_enabled = is_assistant_enabled(user)
    api_logger.debug(f"User {user} assistant_enabled: {is_enabled}")
    return is_enabled
@frappe.whitelist()
def execute_tool(tool_name: str, arguments=None) -> Dict[str, Any]:
    """Execute a single tool via the ToolRegistry and return its result.

    Used by the Strategy-A dashboard Query resolver for per-Query targeted
    re-fetches (on cache miss or on @Run button click). Not a bulk endpoint —
    the backend's refresh_dashboard_queries handles batch refresh.

    Permissions:
      - caller must have assistant_enabled = 1 on their User row
      - ToolRegistry enforces plugin enable, FAC tool config,
        FAC Tool Role Access rules, and Frappe doctype permissions
      - identical to MCP /tools/call handler
    """
    from frappe_assistant_core.constants.definitions import (
        ErrorCodes, ErrorMessages,
    )
    from frappe_assistant_core.core.tool_registry import get_tool_registry

    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Authentication required"))

    if not _check_assistant_enabled(user):
        frappe.throw(_("Assistant is not enabled for this user"))

    if not tool_name or not isinstance(tool_name, str):
        return {"success": False, "error": ErrorMessages.MISSING_TOOL_NAME}
    import json as _json
    if tool_name.startswith("{") and tool_name.endswith("}"):
        try:
            parsed = _json.loads(tool_name)
            if isinstance(parsed, dict) and "name" in parsed:
                inner_name = parsed.get("name")
                inner_args = parsed.get("arguments") or parsed.get("args") or {}
                if isinstance(inner_name, str) and inner_name:
                    tool_name = inner_name
                    arguments = inner_args
        except Exception:
            pass  

    if arguments is None:
        arguments = {}
    elif isinstance(arguments, str):
        try:
            arguments = _json.loads(arguments)
        except Exception:
            return {"success": False, "error": "arguments must be a JSON object"}
    if not isinstance(arguments, dict):
        return {"success": False, "error": "arguments must be an object"}

    registry = get_tool_registry()
    try:
        result = registry.execute_tool(tool_name, arguments)
    except ValueError as e:
        api_logger.warning(f"execute_tool: {tool_name} not available for {user}: {e}")
        return {"success": False, "error": f"Unknown tool: {tool_name}", "error_code": ErrorCodes.INVALID_PARAMS}
    except PermissionError as e:
        api_logger.warning(f"execute_tool: {tool_name} permission denied for {user}: {e}")
        return {
            "success": False,
            "error": "Access denied",
            "error_code": ErrorCodes.AUTHENTICATION_REQUIRED,
        }
    except frappe.ValidationError as e:
        api_logger.error(f"execute_tool: {tool_name} validation error: {e}")
        return {"success": False, "error": str(e), "error_code": ErrorCodes.VALIDATION_ERROR}
    except Exception as e:
        api_logger.error(f"execute_tool: {tool_name} failed for {user}: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_code": ErrorCodes.INTERNAL_ERROR,
        }
    try:
        import json as _json
        _json.dumps(result, default=str)
    except Exception:
        pass

    return {"success": True, "tool": tool_name, "result": result}