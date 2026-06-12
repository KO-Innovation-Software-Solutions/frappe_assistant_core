// Copyright (c) 2026, Paul Clinton and contributors
// For license information, please see license.txt

frappe.ui.form.on("Aiko Chat Session", {
    refresh(frm) {
        if (!frm.is_new()) {
            aiko_load_conversation(frm);
        }
    },
});

/**
 * Fetches all Aiko Chat Messages for this session,
 * renders styled HTML blocks, and populates the child table.
 */
function aiko_load_conversation(frm) {
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Aiko Chat Message",
            filters: { session: frm.doc.name },
            fields: [
                "name",
                "role",
                "content",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "creation",
            ],
            order_by: "creation asc",
            limit_page_length: 200,
        },
        callback(r) {
            const messages = (r && r.message) ? r.message : [];

            // ── 1. Render HTML conversation view ──────────────────────────
            const container = frm.fields_dict["conversation_html"].$wrapper;
            container.empty();

            if (messages.length === 0) {
                container.html(
                    `<div style="padding:16px;color:#888;font-style:italic;">
                        No messages in this session yet.
                    </div>`
                );
            } else {
                const blocks = messages.map((msg, i) => aiko_render_block(msg, i + 1)).join("");
                container.html(
                    `<div style="display:flex;flex-direction:column;gap:12px;padding:8px 0;">
                        ${blocks}
                    </div>`
                );
            }

            // ── 2. Populate child table ────────────────────────────────────
            // Clear existing rows silently
            frm.doc.messages = [];

            messages.forEach((msg, i) => {
                let row = frappe.model.add_child(frm.doc, "Aiko Chat Session Message", "messages");
                row.idx_display  = i + 1;
                row.role         = msg.role;
                row.content      = msg.content;
                row.input_tokens = msg.input_tokens || 0;
                row.output_tokens = msg.output_tokens || 0;
                row.total_tokens  = msg.total_tokens || 0;
                row.message_name  = msg.name;
            });

            frm.refresh_field("messages");
        },
    });
}

/**
 * Returns the HTML string for a single message block.
 * User messages are right-aligned (blue tint),
 * assistant messages are left-aligned (purple tint).
 */
function aiko_render_block(msg, index) {
    const isUser = msg.role === "user";

    const alignStyle   = isUser ? "align-self:flex-end;" : "align-self:flex-start;";
    const bgColor      = isUser ? "#e8f0fe" : "#f3e8fd";
    const borderColor  = isUser ? "#4a90d9" : "#9b59b6";
    const roleLabel    = isUser ? "🧑 User" : "🤖 Assistant";
    const roleBadgeBg  = isUser ? "#4a90d9" : "#9b59b6";

    const createdAt = msg.creation
        ? frappe.datetime.str_to_user(msg.creation)
        : "";

    // Token badge — only show for assistant (it's where costs live)
    const tokenBadge = !isUser
        ? `<span style="
                background:#fff3e0;
                border:1px solid #e0a020;
                border-radius:12px;
                padding:2px 10px;
                font-size:11px;
                color:#7a5200;
                white-space:nowrap;
            ">
            ↑ ${msg.input_tokens || 0} &nbsp;|&nbsp; ↓ ${msg.output_tokens || 0} &nbsp;|&nbsp; Σ ${msg.total_tokens || 0} tokens
           </span>`
        : "";

    // Escape content for safe HTML display, preserve newlines
    const safeContent = frappe.utils.escape_html(msg.content || "")
        .replace(/\n/g, "<br>");

    return `
    <div style="
        max-width:85%;
        ${alignStyle}
        background:${bgColor};
        border-left:4px solid ${borderColor};
        border-radius:8px;
        padding:12px 16px;
        box-shadow:0 1px 4px rgba(0,0,0,0.08);
        font-family:var(--font-stack);
    ">
        <!-- Header row -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:12px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="
                    background:${roleBadgeBg};
                    color:#fff;
                    border-radius:12px;
                    padding:2px 10px;
                    font-size:11px;
                    font-weight:600;
                    white-space:nowrap;
                ">${roleLabel}</span>
                <span style="font-size:11px;color:#888;">#${index}</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
                ${tokenBadge}
                <span style="font-size:11px;color:#aaa;">${createdAt}</span>
            </div>
        </div>

        <!-- Content -->
        <div style="
            font-size:13px;
            line-height:1.7;
            color:#333;
            word-break:break-word;
            white-space:pre-wrap;
        ">${safeContent}</div>

        <!-- Message ID (transparency) -->
        <div style="margin-top:8px;font-size:10px;color:#bbb;">
            ID: ${msg.name}
        </div>
    </div>`;
}