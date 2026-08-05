from datetime import datetime, timedelta
from typing import Dict, Optional

import frappe
from frappe.utils import now_datetime

FROZEN_CACHE_PREFIX = "token_frozen:"
USAGE_CACHE_PREFIX = "token_usage:"
CACHE_TTL = 300


def get_period_start(period: str, reset_day: int = 1) -> datetime:
    """Calculate the start datetime for the given period."""
    now = now_datetime()
    if period == "Daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "Weekly":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        if now.day >= reset_day:
            return now.replace(day=reset_day, hour=0, minute=0, second=0, microsecond=0)
        prev_month = now.replace(day=1) - timedelta(days=1)
        return prev_month.replace(day=min(reset_day, prev_month.day), hour=0, minute=0, second=0, microsecond=0)


def _resolve_pool(user: str, settings) -> tuple:
    """
    Single site = single organization, so there is one site-wide pool shared
    by every login on the site. The whole token budget for the organization
    is set on Assistant Core Settings (not on the Company doctype), and token
    usage is aggregated across all users of the site for the current period.

    Returns (pool_id, limit, is_client). pool_id is never None for a login
    once token limits are enabled — access is site-wide, there are no
    per-company or per-user pools anymore.
    """
    limit = int(settings.get("token_limit") or 0)
    return f"site:{frappe.local.site}", limit, True


# Fieldname on the User doctype for the "Enable Assistant Access" checkbox.
# Verified via Form Builder property panel on 2026-08-03 — do not guess again,
# just re-check the same way if this ever needs revisiting.
ASSISTANT_ACCESS_FIELD = "assistant_enabled"


def is_assistant_enabled(user: str) -> bool:
    """Access gate — separate from token limits. A login must have this checked to use AIKO at all."""
    if not frappe.db.has_column("User", ASSISTANT_ACCESS_FIELD):
        return True  # field not set up yet — don't block everyone by accident
    return bool(frappe.db.get_value("User", user, ASSISTANT_ACCESS_FIELD))


def get_pool_token_usage(pool_id: str, is_client: bool) -> int:
    """Aggregate tokens used by everyone sharing this pool in the current period.

    IMPORTANT: this counter is also mutated by raw Redis INCRBY/DECRBY in
    reserve_tokens()/true_up_tokens()/update_token_usage_cache(). Redis
    rejects INCRBY on a key written by Frappe's serialized set_value()
    ("value is not an integer or out of range"), and get_value() won't see
    what a raw INCRBY wrote either — the two wrappers use different key
    namespaces/formats. So every read/write of this specific key must go
    through raw GET/SET/INCRBY/DECRBY/EXISTS/EXPIRE, never get_value/set_value.
    """
    period_start = _get_current_period_start()
    raw_key = frappe.cache().make_key(f"{USAGE_CACHE_PREFIX}{pool_id}:{period_start.isoformat()}")
    cached = frappe.cache().get(raw_key)
    if cached is not None:
        return int(cached)

    if pool_id.startswith("site:"):
        # Site-wide (single-organization) pool — aggregate EVERY login's
        # usage on this site for the current period. No user/company filter:
        # the whole site shares one budget.
        chat_filter = "m.creation >= %s"
        dash_filter = "m.creation >= %s"
        param = period_start
        join_user = ""
    elif is_client:
        company = pool_id.split(":", 1)[1]
        # Bridge through Employee — only counts logins that are actually
        # enabled for the assistant, so a disabled employee's Employee
        # record (if any stray usage existed) never inflates the company total.
        chat_filter = f"e.organization = %s AND u.{ASSISTANT_ACCESS_FIELD} = 1"
        dash_filter = f"e.organization = %s AND u.{ASSISTANT_ACCESS_FIELD} = 1"
        param = company
        join_user = (
            "JOIN `tabUser` u ON u.name = s.user "
            "JOIN `tabEmployee` e ON e.user_id = s.user"
        )
    else:
        user = pool_id.split(":", 1)[1]
        chat_filter = "s.user = %s"
        dash_filter = "s.user = %s"
        param = user
        join_user = ""

    total = int(frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(m.total_tokens), 0)
        FROM `tabAiko Chat Message` m
        JOIN `tabAiko Chat Session` s ON s.name = m.session
        {join_user}
        WHERE {chat_filter} AND m.creation >= %s
        """,
        (param, period_start),
    )[0][0] or 0)

    dashboard_total = int(frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(m.total_tokens), 0)
        FROM `tabAiko Dashboard Message` m
        JOIN `tabAiko Dashboard Session` s ON s.name = m.session
        {join_user}
        WHERE {dash_filter} AND m.creation >= %s
        """,
        (param, period_start),
    )[0][0] or 0)

    total = total + dashboard_total

    # Seed with raw SET ... NX so we never clobber a concurrent reservation's
    # INCRBY that may have already landed on this key while we were querying
    # the DB. If someone beat us to it, re-read to return the live value.
    frappe.cache().set(raw_key, total, ex=CACHE_TTL, nx=True)
    current = frappe.cache().get(raw_key)
    return int(current) if current is not None else total



def _get_current_period_start() -> datetime:
    """Get the period start datetime from settings."""
    settings = frappe.get_cached_doc("Assistant Core Settings")
    period = settings.get("token_limit_period") or "Monthly"
    reset_day = int(settings.get("token_limit_reset_day") or 1)
    return get_period_start(period, reset_day)


def _usage_key(pool_id: str) -> str:
    period_start = _get_current_period_start()
    return frappe.cache().make_key(f"{USAGE_CACHE_PREFIX}{pool_id}:{period_start.isoformat()}")


def _ensure_seeded(raw_key: str, pool_id: str, is_client: bool):
    """The first time a period's counter is touched, seed it from the real DB total (not 0).

    Delegates the actual seeding to get_pool_token_usage(), which writes the
    seed with raw SET ... NX. Don't seed here too — a second, separately
    written SET/set_value call is exactly how this key's format drifted out
    of sync with the raw INCRBY/DECRBY calls before.
    """
    if not frappe.cache().exists(raw_key):
        get_pool_token_usage(pool_id, is_client)


def reserve_tokens(user: str, amount: int) -> Dict:
    """
    Atomically reserves `amount` tokens against this login's pool BEFORE the
    LLM call runs. Uses Redis's atomic INCRBY so two simultaneous requests
    from the same pool can never both slip through a stale read — only one
    can win the increment past the limit.

    Call this before starting the LLM request. If allowed, hang onto
    `pool_id` and `reserved` from the result and pass them to true_up_tokens()
    once the real usage is known.
    """
    settings = frappe.get_cached_doc("Assistant Core Settings")
    if not settings.get("enable_token_limits"):
        return {"allowed": True, "pool_id": None, "reserved": 0}

    pool_id, limit, is_client = _resolve_pool(user, settings)

    if limit <= 0:
        # Fail CLOSED: token limits are enabled but no budget is configured on
        # Assistant Core Settings. Blocked, not unlimited — an admin must
        # explicitly set the organization token limit before anyone gets access.
        return {
            "allowed": False,
            "pool_id": pool_id,
            "reserved": 0,
            "tokens_used": 0,
            "tokens_limit": 0,
            "reason": "No token limit configured for this account. Please contact your administrator.",
        }

    raw_key = _usage_key(pool_id)
    _ensure_seeded(raw_key, pool_id, is_client)

    new_total = frappe.cache().incrby(raw_key, amount)  # atomic — this is what closes the race
    frappe.cache().expire(raw_key, CACHE_TTL)

    if new_total > limit:
        frappe.cache().decrby(raw_key, amount)  # roll back — this reservation loses
        cache_key = f"{FROZEN_CACHE_PREFIX}{pool_id}"
        frappe.cache().set_value(
            cache_key,
            {"tokens_used": new_total - amount, "frozen_at": str(now_datetime())},
            expires_in_sec=CACHE_TTL,
        )
        return {
            "allowed": False,
            "pool_id": pool_id,
            "reserved": 0,
            "tokens_used": new_total - amount,
            "tokens_limit": limit,
            "reason": "Token limit exceeded. Please contact your administrator.",
        }

    return {
        "allowed": True,
        "pool_id": pool_id,
        "reserved": amount,
        "tokens_used": new_total,
        "tokens_limit": limit,
    }


def true_up_tokens(pool_id: Optional[str], reserved: int, actual: int):
    """
    After the real response completes, correct the reservation estimate down
    (or up, if it somehow ran over the cap) to the real token cost. Safe to
    call with actual=0 (e.g. on a hard failure before any tokens were spent)
    to simply release the reservation.
    """
    if not pool_id:
        return
    raw_key = _usage_key(pool_id)
    delta = actual - reserved
    if delta:
        frappe.cache().incrby(raw_key, delta)  # negative delta works like DECRBY
        frappe.cache().expire(raw_key, CACHE_TTL)
    clear_frozen_cache(pool_id)


def check_token_limit(user: str) -> Dict:
    """
    Check if a user has exceeded their token limit.

    Returns:
        Dict with keys: allowed (bool), tokens_used (int),
        tokens_limit (int), frozen (bool), reason (str)
    """
    try:
        settings = frappe.get_cached_doc("Assistant Core Settings")
        if not settings.get("enable_token_limits"):
            return {"allowed": True, "frozen": False}

        pool_id, limit, is_client = _resolve_pool(user, settings)

        if limit <= 0:
            # Fail CLOSED — see matching comment in reserve_tokens(). Token
            # limits are enabled but no budget is configured on Assistant
            # Core Settings, so the site is blocked, not unlimited.
            return {
                "allowed": False,
                "tokens_used": 0,
                "tokens_limit": 0,
                "frozen": True,
                "reason": "No token limit configured for this account. Please contact your administrator.",
            }

        # Known worst-case size of the request about to run — bounded by the
        # max_tokens cap set on the LLM call. This is what makes "preventive"
        # checking possible: without a cap, we'd have no way to know in
        # advance whether an incoming request risks pushing the pool over.
        safety_margin = int(settings.get("max_tokens_per_request") or 0)

        tokens_used = get_pool_token_usage(pool_id, is_client)
        if tokens_used + safety_margin >= limit:
            cache_key = f"{FROZEN_CACHE_PREFIX}{pool_id}"
            frappe.cache().set_value(
                cache_key,
                {"tokens_used": tokens_used, "frozen_at": str(now_datetime())},
                expires_in_sec=CACHE_TTL,
            )
            return {
                "allowed": False,
                "tokens_used": tokens_used,
                "tokens_limit": limit,
                "frozen": True,
                "reason": "Token limit exceeded. Please contact your administrator.",
            }

        cache_key = f"{FROZEN_CACHE_PREFIX}{pool_id}"
        frappe.cache().delete_value(cache_key)

        return {"allowed": True, "tokens_used": tokens_used, "tokens_limit": limit, "frozen": False}

    except Exception as e:
        frappe.logger("token_limits").error(f"Error checking token limit for {user}: {e}")
        return {"allowed": True, "frozen": False}


def update_token_usage_cache(user: str, additional_tokens: int):
    """Update the cached token usage after a new message is saved — the site-wide pool this login belongs to.

    Uses raw INCRBY (like reserve_tokens()/true_up_tokens()) rather than
    get_value/set_value, so this write lands on the same counter those
    functions maintain instead of a differently-formatted shadow key.
    """
    settings = frappe.get_cached_doc("Assistant Core Settings")
    pool_id, _limit, is_client = _resolve_pool(user, settings)
    raw_key = _usage_key(pool_id)
    _ensure_seeded(raw_key, pool_id, is_client)
    frappe.cache().incrby(raw_key, additional_tokens)
    frappe.cache().expire(raw_key, CACHE_TTL)
    clear_frozen_cache(pool_id)


def record_pool_usage(pool_id: Optional[str], tokens: int):
    """Record actual token usage against a pool after a response completes.

    Used by flows that don't pre-reserve tokens (e.g. the dashboard path),
    where there is no reservation to true-up — the real cost is simply added
    to the pool counter. Same raw INCRBY counter as reserve_tokens() /
    true_up_tokens() / update_token_usage_cache().
    """
    if not pool_id or tokens <= 0:
        return
    raw_key = _usage_key(pool_id)
    _ensure_seeded(raw_key, pool_id, True)
    frappe.cache().incrby(raw_key, tokens)
    frappe.cache().expire(raw_key, CACHE_TTL)
    clear_frozen_cache(pool_id)


def clear_frozen_cache(pool_id: str):
    """Clear the frozen cache flag (called on period reset or admin action). Accepts a pool_id like 'user:x' or 'client:y'."""
    cache_key = f"{FROZEN_CACHE_PREFIX}{pool_id}"
    frappe.cache().delete_value(cache_key)


def raise_if_frozen(user: str):
    """Raise a PermissionError if the user's token limit is exceeded."""
    result = check_token_limit(user)
    if result.get("frozen"):
        from frappe_assistant_core.utils.audit_trail import log_security_event
        log_security_event(
            "token_limit_exceeded",
            user,
            {
                "tokens_used": result.get("tokens_used", 0),
                "tokens_limit": result.get("tokens_limit", 0),
                "action": "blocked",
            },
            severity="Medium",
        )
        frappe.throw(result["reason"], frappe.PermissionError)