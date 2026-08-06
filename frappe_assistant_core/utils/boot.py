import frappe


def add_assistant_access_to_boot(bootinfo):
    """Expose the user's assistant_enabled flag and hide AIKO surfaces when disabled.

    Runs on every boot (via the `boot_session` hook) for the logged-in user.

    When assistant access is off for the user we also strip the AIKO entry from
    the boot data so the frontend never renders the launcher icon, the AIKO
    sidebar group, or the floating widget — not just errors when clicked.

    This must NEVER break boot for anyone, so everything is wrapped and defaults
    fail OPEN (widget keeps showing) if the flag cannot be read. That mirrors the
    backend gate in utils/token_limits.is_assistant_enabled().
    """
    try:
        if frappe.session.user == "Guest":
            return

        enabled = _get_assistant_enabled(frappe.session.user)

        # Expose on boot.user so the widget (premium-ai-widget main.jsx) can
        # decide whether to mount without an extra round-trip.
        bootinfo.setdefault("user", {})["assistant_enabled"] = 1 if enabled else 0

        if enabled:
            return

        # Hide the AIKO workspace sidebar group (frontend renders this from boot).
        sidebar_items = bootinfo.get("workspace_sidebar_item") or {}
        sidebar_items.pop("aiko", None)

        # Hide the AIKO launcher icon (Desktop Icon). The frontend launcher is
        # driven by bootinfo.desktop_icons.
        desktop_icons = bootinfo.get("desktop_icons") or []
        bootinfo["desktop_icons"] = [
            icon
            for icon in desktop_icons
            if not _is_aiko_desktop_icon(icon)
        ]

    except Exception:
        # Never break the user's session boot because of a cosmetics flag.
        frappe.log_error(
            title="AIKO Boot Gating Error",
            message=frappe.get_traceback(),
        )


def _get_assistant_enabled(user: str) -> bool:
    from frappe_assistant_core.utils.token_limits import is_assistant_enabled

    return is_assistant_enabled(user)


def _is_aiko_desktop_icon(icon) -> bool:
    label = (icon.get("label") or "").lower()
    link_to = (icon.get("link_to") or "").lower()
    link_type = (icon.get("link_type") or "").lower()
    return label == "aiko" or (link_type == "workspace sidebar" and link_to == "aiko")
