window.AikoChatPage = {
    init: function (wrapper) {

        // ── THINKING PHRASES ──────────────────────────────────────────────
        const THINK_PHRASES = [
            "Revving up the response…",
            "Cruising through your fleet data…",
            "Navigating your records…",
            "Pulling into the data lot…",
            "Checking the dashboard…",
            "Taking the express lane…",
            "Fueling up the answer…",
            "Shifting into gear…",
            "Reading the mileage…",
            "Mapping out the details…",
            "On the home stretch…",
            "Almost at the destination…"
        ];
        let _thinkInterval = null;

        function shuffledPhrases() {
            const arr = THINK_PHRASES.slice();
            for (let i = arr.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [arr[i], arr[j]] = [arr[j], arr[i]];
            }
            return arr;
        }

        function startThinkCycle(el) {
            const phrases = shuffledPhrases();
            let idx = 0;
            const $el = $(el);
            $el.text(phrases[idx]).addClass('aiko-think-visible');
            _thinkInterval = setInterval(function () {
                $el.removeClass('aiko-think-visible');
                setTimeout(function () {
                    idx = (idx + 1) % phrases.length;
                    $el.text(phrases[idx]);
                    $el.addClass('aiko-think-visible');
                }, 220);
            }, 2200);
        }

        function stopThinkCycle() {
            if (_thinkInterval) { clearInterval(_thinkInterval); _thinkInterval = null; }
        }

        function updateThinkingStage(text) {
            // A real backend stage update arrived — stop the generic cycling
            // phrases and show what's actually happening.
            stopThinkCycle();
            const $el = $('#aiko-page-thinking .aiko-think-text');
            if (!$el.length || !text) return;
            $el.removeClass('aiko-think-visible');
            setTimeout(function () {
                $el.text(text);
                $el.addClass('aiko-think-visible');
            }, 220);
        }

        // ── STATE ─────────────────────────────────────────────────────────
        let thread_id             = frappe.utils.get_random(10);
        let currentSessionName    = null;
        let isThinking            = false;
        let isScrolledUp          = false;
        let messageCount          = 0;
        let pendingXhr            = null;
        let currentRequestId      = null;
        let allSessions           = [];
        let sidebarVisible        = window.innerWidth > 900;
        let abortedRequests       = new Set();
        let responseStopped       = false;

        // ── HELPERS ───────────────────────────────────────────────────────
        function formatTimestamp(dateStr) {
            const date = dateStr ? new Date(dateStr.replace(' ', 'T')) : new Date();
            return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        }

        function formatRelativeTime(datetimeStr) {
            if (!datetimeStr) return '';
            const date      = new Date(datetimeStr.replace(' ', 'T'));
            const now       = new Date();
            const diffMins  = Math.floor((now - date) / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays  = Math.floor(diffHours / 24);
            if (diffMins  < 1)  return 'Just now';
            if (diffMins  < 60) return diffMins  + 'm ago';
            if (diffHours < 24) return diffHours + 'h ago';
            if (diffDays  < 7)  return diffDays  + 'd ago';
            return date.toLocaleDateString();
        }

        function escapeHtml(str) {
            return String(str)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function sessionDisplayTitle(s) {
            if (s.name) return s.name;
            if (s.title && s.title.trim()) return s.title.trim();
            return 'New Chat';
        }

        // ── ROOT HTML ─────────────────────────────────────────────────────
        // NOTE: We target the wrapper div directly (no .page-content lookup)
        $(wrapper).html(`
            <div id="aiko-page-root">

                <!-- SIDEBAR -->
                <aside class="aiko-sidebar">
                    <div class="aiko-sidebar-header">
                        <span class="aiko-sidebar-title">AIKO</span>
                        <button id="aiko-page-new-chat" title="New chat">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        </button>
                    </div>
                    <div class="aiko-sidebar-search-wrap">
                        <svg class="aiko-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                        <input id="aiko-sidebar-search" type="text" placeholder="Search chats…" autocomplete="off" />
                    </div>
                    <div class="aiko-sidebar-sessions" id="aiko-sidebar-sessions">
                        <div class="aiko-sessions-loading">Loading…</div>
                    </div>
                </aside>

                <!-- MAIN -->
                <div class="aiko-page-main">

                    <!-- TOPBAR -->
                    <div class="aiko-page-topbar">
                        <button class="aiko-icon-btn aiko-topbar-btn" id="aiko-toggle-sidebar" title="Toggle sidebar">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                        </button>

                        <div class="aiko-status-dot"></div>
                        <span class="aiko-page-session-label" id="aiko-page-session-label">New Chat</span>

                        <div class="aiko-topbar-actions">
                            <!-- Go back to Frappe desk -->
                            <button class="aiko-icon-btn aiko-topbar-btn" id="aiko-shrink-btn" title="Back to desk">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>
                            </button>
                        </div>
                    </div>

                    <!-- MESSAGES -->
                    <div class="aiko-page-messages" id="aiko-page-messages"></div>

                    <div id="aiko-page-scroll-btn" class="aiko-scroll-btn hidden">
                        <span id="aiko-page-scroll-label">↓</span>
                    </div>

                    <!-- INPUT -->
                    <div class="aiko-page-input-area">
                        <div class="aiko-input-wrapper">
                            <textarea class="aiko-page-textarea" id="aiko-page-input" placeholder="Ask AIKO anything…" rows="1"></textarea>
                            <button class="aiko-page-stop-btn" id="aiko-page-stop-btn" title="Stop generating" style="display: none;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <rect x="5" y="5" width="14" height="14" rx="2"/>
                                </svg>
                            </button>
                            <button class="aiko-page-send-btn" id="aiko-page-send-btn">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                            </button>
                        </div>
                        <p class="aiko-input-hint">AIKO can make mistakes — verify important information.</p>
                    </div>
                </div>
            </div>
        `);

        const $root     = $('#aiko-page-root');
        const $messages = $('#aiko-page-messages');

        // ── SIDEBAR COLLAPSE ──────────────────────────────────────────────
        function applySidebarState() {
            if (sidebarVisible) {
                $root.addClass('sidebar-expanded').removeClass('sidebar-collapsed');
            } else {
                $root.addClass('sidebar-collapsed').removeClass('sidebar-expanded');
            }
        }
        applySidebarState();

        if (window.innerWidth <= 900) { sidebarVisible = false; applySidebarState(); }

        $('#aiko-toggle-sidebar').on('click', function () {
            sidebarVisible = !sidebarVisible;
            applySidebarState();
        });

        // ── SHRINK / BACK TO DESK ─────────────────────────────────────────
        $('#aiko-shrink-btn').on('click', function () {
            sessionStorage.setItem('aiko_open_widget', '1');
            sessionStorage.setItem('aiko_widget_session', currentSessionName || '');
            sessionStorage.setItem('aiko_widget_thread', thread_id || '');
            if (isThinking) {
                sessionStorage.setItem('aiko_widget_thinking', '1');
                const lastUserMsg = $('#aiko-page-messages .aiko-message.user').last().find('.aiko-bubble').text().trim();
                if (lastUserMsg) sessionStorage.setItem('aiko_widget_pending', lastUserMsg);
            } else {
                sessionStorage.removeItem('aiko_widget_thinking');
                sessionStorage.removeItem('aiko_widget_pending');
            }
            if (document.referrer && document.referrer !== window.location.href) {
                window.location.href = document.referrer;
            } else {
                window.location.href = '/desk';
            }
        });

        // FIX #3: Limit is consistently 20 in both the condition and the banner text
        function checkMessageLimit() {
            if (messageCount >= 20) {
                $('#aiko-page-send-btn').prop('disabled', true);
                $('#aiko-page-input').prop('disabled', true).attr('placeholder', 'Message limit reached.');
                $('.aiko-page-input-area').addClass('aiko-input-disabled');

                if (!$('#aiko-limit-banner').length) {
                    $('.aiko-page-input-area').before(`
                        <div id="aiko-limit-banner" class="aiko-limit-banner">
                            <p>This chat has reached 20 messages.<br>Start a new session to continue.</p>
                            <button class="aiko-limit-new-chat-btn" id="aiko-page-limit-new-chat">+ New Chat</button>
                        </div>`);
                    $('#aiko-page-limit-new-chat').on('click', function () { startNewChat(); });
                }
            }
        }

        // ── SESSION LABEL ─────────────────────────────────────────────────
        function updateSessionLabel(name) {
            $('#aiko-page-session-label').text(name || 'New Chat');
        }

        // ── SIDEBAR SESSIONS ──────────────────────────────────────────────
        function loadSidebarSessions(onDone) {
            $('#aiko-sidebar-sessions').html('<div class="aiko-sessions-loading">Loading…</div>');
            frappe.call({
                method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
                callback: function (r) {
                    if (r.message && r.message.success) {
                        allSessions = r.message.sessions || [];
                        renderSidebarSessions(allSessions);
                        if (onDone) onDone();
                    } else {
                        $('#aiko-sidebar-sessions').html('<div class="aiko-sessions-loading">Could not load chats.</div>');
                    }
                },
                error: function () {
                    $('#aiko-sidebar-sessions').html('<div class="aiko-sessions-loading">Network error.</div>');
                }
            });
        }

        function renderSidebarSessions(sessions) {
            if (!sessions || sessions.length === 0) {
                $('#aiko-sidebar-sessions').html('<div class="aiko-sessions-loading">No previous chats.</div>');
                return;
            }

            const now   = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const yday  = new Date(today - 86400000);
            const week  = new Date(today - 6 * 86400000);

            const groups = { Today: [], Yesterday: [], 'This week': [], Older: [] };
            sessions.forEach(function (s) {
                const d = new Date((s.preview_time || s.last_active || '').replace(' ', 'T'));
                if (d >= today)      groups['Today'].push(s);
                else if (d >= yday)  groups['Yesterday'].push(s);
                else if (d >= week)  groups['This week'].push(s);
                else                 groups['Older'].push(s);
            });

            let html = '';
            Object.keys(groups).forEach(function (label) {
                if (!groups[label].length) return;
                html += `<div class="aiko-sessions-group"><div class="aiko-sessions-group-label">${label}</div>`;
                groups[label].forEach(function (s) {
                    const title    = sessionDisplayTitle(s);
                    const isActive = s.name === currentSessionName ? 'active' : '';
                    html += `
                        <div class="aiko-session-item ${isActive}" data-session-name="${s.name}" data-thread-id="${s.thread_id}">
                            <div class="aiko-session-title">${escapeHtml(title)}</div>
                            <div class="aiko-session-time">${formatRelativeTime(s.preview_time || s.last_active)}</div>
                        </div>`;
                });
                html += '</div>';
            });

            $('#aiko-sidebar-sessions').html(html);
            $('#aiko-sidebar-sessions').off('click', '.aiko-session-item').on('click', '.aiko-session-item', function () {
                loadSession($(this).data('session-name'), $(this).data('thread-id'));
            });
        }

        // Sidebar search filter
        $('#aiko-sidebar-search').on('input', function () {
            const q = $(this).val().trim().toLowerCase();
            if (!q) { renderSidebarSessions(allSessions); return; }
            renderSidebarSessions(allSessions.filter(function (s) {
                return (sessionDisplayTitle(s) + ' ' + (s.preview || '')).toLowerCase().includes(q);
            }));
        });

        // ── LOAD SESSION ──────────────────────────────────────────────────
        function loadSession(sessionName, sessionThreadId) {
            currentSessionName    = sessionName;
            thread_id             = sessionThreadId;
            isScrolledUp          = false;
            updateSessionLabel(sessionName);
            const params = new URLSearchParams({ session: sessionName, thread: sessionThreadId });
            history.replaceState(null, '', '?' + params.toString());
            $('#aiko-sidebar-sessions .aiko-session-item').removeClass('active');
            $(`[data-session-name="${sessionName}"]`).addClass('active');

            $messages.html('<div class="aiko-sessions-loading">Loading messages…</div>');

            frappe.call({
                method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
                args: { session_name: sessionName, limit: 20 },
                callback: function (r) {
                    $messages.html('');
                    if (r.message && r.message.success) {
                        const msgs = r.message.messages;
                        if (msgs.length === 0) {
                            showEmptyState();
                        } else {
                            msgs.forEach(function (m) { appendPageMessage(m.role, m.content, false, m.creation); });
                            messageCount = msgs.length;
                            checkMessageLimit();
                            pageScrollToBottom();
                        }
                    } else {
                        showEmptyState();
                    }
                },
                error: function () {
                    $messages.html('');
                    showEmptyState();
                }
            });
        }

        // ── NEW CHAT ──────────────────────────────────────────────────────
        function startNewChat() {
            thread_id          = frappe.utils.get_random(10);
            currentSessionName = null;
            messageCount       = 0;
            isScrolledUp       = false;
            history.replaceState(null, '', window.location.pathname);
            abortedRequests.clear();
            currentRequestId   = null;
            updateSessionLabel('New Chat');

            // Remove limit banner and re-enable input
            $('#aiko-limit-banner').remove();
            $('#aiko-limit-warning').remove();
            $('#aiko-page-send-btn').prop('disabled', false);
            $('#aiko-page-input').prop('disabled', false).attr('placeholder', 'Ask AIKO anything…');
            $('.aiko-page-input-area').removeClass('aiko-input-disabled');

            $messages.html('');
            showEmptyState();
            $('#aiko-page-input').focus();
            $('#aiko-sidebar-sessions .aiko-session-item').removeClass('active');
        }

        // FIX #1: removed the dead '#aiko-page-new-chat-topbar' selector — that element doesn't exist in the HTML
        $('#aiko-page-new-chat').on('click', function () { startNewChat(); });

        // ── EMPTY STATE ───────────────────────────────────────────────────
        function showEmptyState() {
            const allSuggestions = [
                { label: "Fleet overview", prompt: "How many vehicles are in the fleet?" },
                { label: "Active vehicles", prompt: "List active vehicles." },
                { label: "Compliance alerts", prompt: "Which vehicles have expired compliance documents?" },
                { label: "Expiring soon", prompt: "Which compliances are expiring soon?" },
                { label: "Open inspections", prompt: "Show all open inspections." },
                { label: "Overdue inspections", prompt: "Which inspections are overdue?" },
                { label: "Open issues", prompt: "Show all issues." },
                { label: "High priority issues", prompt: "Show all high priority issues." },
                { label: "Critical faults", prompt: "Show all critical faults." },
                { label: "Work orders", prompt: "Show all submitted work orders." },
                { label: "Overdue work orders", prompt: "Which work orders are overdue?" },
                { label: "Fuel entries today", prompt: "Show fuel entries for today." },
                { label: "Service reminders", prompt: "Show all upcoming service reminders." },
                { label: "Overdue reminders", prompt: "Which service reminders are overdue?" },
                { label: "Active assets", prompt: "List all active assets." },
                { label: "Asset summary", prompt: "Give me an asset summary." },
                { label: "Today's bookings", prompt: "Show today's bookings." },
                { label: "Pending bookings", prompt: "Show pending bookings." },
                { label: "E-Way Bill expiry", prompt: "Which E-Way Bills expire today?" },
                { label: "Active trips", prompt: "What trips are active right now?" },
                { label: "Overdue trips", prompt: "Are there any overdue trips?" },
                { label: "Trip summary", prompt: "Give me an overall trip operations summary." },
            ];

            // Pick 4 random suggestions
            const shuffled = allSuggestions.sort(() => Math.random() - 0.5);
            const picked = shuffled.slice(0, 4);

            const chipsHtml = picked.map(s =>
                `<button class="aiko-suggestion-chip" data-prompt="${s.prompt}">${s.label}</button>`
            ).join('');

            $messages.html(`
                <div class="aiko-empty-state">
                    <div class="aiko-empty-icon">
                        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <h3>How can I help you today?</h3>
                    <p>Ask me anything — I'm here for Kofleetz.</p>
                    <div class="aiko-suggestions">
                        ${chipsHtml}
                    </div>
                </div>
            `);

            $messages.off('click', '.aiko-suggestion-chip').on('click', '.aiko-suggestion-chip', function () {
                const prompt = $(this).data('prompt');
                $('#aiko-page-input').val(prompt);
                sendPageMessage();
            });
        }

        function renderMarkdown(text) {
            text = text.replace(/\r\n/g, '\n').replace(/[ \t]+$/gm, '');

            // ── Step 1: Extract and protect code blocks ───────────────────
            const codeBlocks = [];
            text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, function(_, lang, code) {
                const idx = codeBlocks.length;
                codeBlocks.push({ lang: lang || 'text', code: code.trimEnd() });
                return `\x00CODE${idx}\x00`;
            });

            // ── Step 2: Extract and protect tables ────────────────────────
            const tables = [];
            text = text.replace(/^(\|.+\|\n)([ \t]*\|[-| :]+\|\n)((?:[ \t]*\|.+\|\n?)+)/gm,
                function(_, header, _sep, body) {
                    const idx = tables.length;

                    function parseRow(row) {
                        return row.trim()
                            .replace(/^\||\|$/g, '')
                            .split('|')
                            .map(c => c.trim());
                    }

                    function inlineMarkdown(s) {
                        return s
                            .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
                            .replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>')
                            .replace(/\*(.+?)\*/g,         '<em>$1</em>')
                            .replace(/_([^_]+)_/g,         '<em>$1</em>')
                            .replace(/`([^`]+)`/g,         '<code>$1</code>');
                    }

                    const headers = parseRow(header);
                    const rows    = body.trim().split('\n').map(parseRow);

                    const th = headers.map(h =>
                        `<th>${inlineMarkdown(h)}</th>`).join('');
                    const tr = rows.map(r =>
                        '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>'
                    ).join('');

                    tables.push(
                        `<div class="aiko-table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`
                    );
                    return `\x00TABLE${idx}\x00`;
                }
            );

            // ── Step 3: Escape HTML in remaining text ─────────────────────
            let html = text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

                // Headers
                .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
                .replace(/^### (.+)$/gm,  '<h3>$1</h3>')
                .replace(/^## (.+)$/gm,   '<h2>$1</h2>')
                .replace(/^# (.+)$/gm,    '<h1>$1</h1>')

                // Bold + Italic
                .replace(/\*\*\*(.+?)\*\*\*/gs, '<strong><em>$1</em></strong>')
                .replace(/\*\*(.+?)\*\*/gs,     '<strong>$1</strong>')
                .replace(/\*(.+?)\*/gs,         '<em>$1</em>')
                .replace(/_([^_]+)_/g,          '<em>$1</em>')

                // Inline code
                .replace(/`([^`]+)`/g, '<code>$1</code>')

                // Horizontal rule
                .replace(/^---$/gm, '<hr>')

                // Blockquote
                .replace(/^&gt; (.+)$/gm, '<blockquote><p>$1</p></blockquote>')

                // Unordered list items
                .replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>')

                // Ordered list items
                .replace(/^\s*\d+\. (.+)$/gm, '<oli>$1</oli>')

                // Links
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

            // Wrap consecutive <li> in <ul>
            html = html.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, m => '<ul>' + m + '</ul>');

            // Wrap consecutive <oli> in <ol>
            html = html.replace(/(<oli>[\s\S]*?<\/oli>\n?)+/g, m =>
                '<ol>' + m.replace(/<oli>/g, '<li>').replace(/<\/oli>/g, '</li>') + '</ol>');

            // Paragraphs — skip blocks that are already block-level HTML or table placeholders
            html = html.split(/\n{2,}/).map(function(block) {
                block = block.trim();
                if (!block) return '';
                if (/^<(h[1-6]|ul|ol|hr|blockquote|pre|div)/.test(block)) return block;
                if (/^\x00TABLE\d+\x00$/.test(block)) return block;
                return '<p>' + block.replace(/\n/g, '<br>') + '</p>';
            }).join('\n');

            // ── Step 4: Restore tables ────────────────────────────────────
            html = html.replace(/\x00TABLE(\d+)\x00/g, (_, idx) => tables[parseInt(idx)]);

            // ── Step 5: Restore code blocks ───────────────────────────────
            html = html.replace(/\x00CODE(\d+)\x00/g, function(_, idx) {
                const { lang, code } = codeBlocks[parseInt(idx)];
                const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                const label = lang && lang !== 'text' ? lang : '';
                return `<div class="aiko-code-block">
                    <div class="aiko-code-header">
                        <span class="aiko-code-lang">${label}</span>
                        <button class="aiko-code-copy" data-code="${escaped.replace(/"/g, '&quot;')}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                            Copy
                        </button>
                    </div>
                    <pre><code class="language-${lang}">${escaped}</code></pre>
                </div>`;
            });

            return html;
        }

        function buildPageMessageHtml(role, text, creation) {
            let content = (role === 'assistant') ? renderMarkdown(text) : escapeHtml(text);
            const time = formatTimestamp(creation);

            const copyBtn = (role === 'assistant')
                ? `<button class="aiko-copy-btn" data-text="${escapeHtml(text)}">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    Copy
                </button>`
                : '';

            return `
                <div class="aiko-message ${role}">
                    <div class="aiko-message-inner">
                        <div class="aiko-bubble">
                            ${content}
                        </div>
                        <div class="aiko-message-footer">
                            <span class="aiko-timestamp">${time}</span>
                            ${copyBtn}
                        </div>
                    </div>
                </div>`;
        }

        function appendPageMessage(role, text, doScroll, creation) {
            if (doScroll === undefined) doScroll = true;
            $messages.find('.aiko-empty-state').remove();
            $messages.append(buildPageMessageHtml(role, text, creation));
            if (doScroll) {
                if (isScrolledUp) {
                    $('#aiko-page-scroll-label').text('New message ↓');
                    $('#aiko-page-scroll-btn').removeClass('hidden').addClass('aiko-scroll-btn-new');
                } else {
                    pageScrollToBottom();
                }
            }
        }

        function pageScrollToBottom() {
            const el = $messages[0];
            el.scrollTop = el.scrollHeight;
            isScrolledUp = false;
            $('#aiko-page-scroll-btn').addClass('hidden');
            $('#aiko-page-scroll-label').text('↓');
            $('#aiko-page-scroll-btn').removeClass('aiko-scroll-btn-new');
        }

        // Code block copy button
        $messages.on('click', '.aiko-code-copy', function () {
            const code = $(this).data('code');
            navigator.clipboard && navigator.clipboard.writeText(code).then(() => {
                const $btn = $(this);
                $btn.addClass('copied').html(`
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    Copied!`);
                setTimeout(() => {
                    $btn.removeClass('copied').html(`
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        Copy`);
                }, 2000);
            });
        });

        // Scroll tracking
        $messages.on('scroll', function () {
            const el   = this;
            const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
            isScrolledUp = dist > 80;
            if (!isScrolledUp) {
                $('#aiko-page-scroll-btn').addClass('hidden');
                $('#aiko-page-scroll-label').text('↓');
                $('#aiko-page-scroll-btn').removeClass('aiko-scroll-btn-new');
            } else {
                $('#aiko-page-scroll-btn').removeClass('hidden');
            }
        });

        $('#aiko-page-scroll-btn').on('click', function () { pageScrollToBottom(); });

        // ── THINKING ──────────────────────────────────────────────────────
        function showPageThinking() {
            isThinking = true;

            $('#aiko-page-send-btn').hide();
            $('#aiko-page-stop-btn').css('display', 'flex');

            const $bubble = $(`
                <div class="aiko-message assistant" id="aiko-page-thinking">
                    <div class="aiko-think-plain">

                        <div class="aiko-truck-scene">
                            <div class="aiko-puff p1"></div>
                            <div class="aiko-puff p2"></div>
                            <div class="aiko-puff p3"></div>
                            <div class="aiko-speed-line sl1"></div>
                            <div class="aiko-speed-line sl2"></div>
                            <div class="aiko-speed-line sl3"></div>
                            <svg class="aiko-truck-svg" width="54" height="32" viewBox="0 0 54 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <rect x="1" y="6" width="30" height="20" rx="2" stroke="#7c3aed" stroke-width="1.5" fill="none"/>
                                <path d="M31 14 L31 26 L52 26 L52 14 L46 6 L31 6 Z" stroke="#7c3aed" stroke-width="1.5" fill="none" stroke-linejoin="round"/>
                                <path d="M33 13 L33 8 L45 8 L50 13 Z" stroke="#7c3aed" stroke-width="1.2" fill="none" stroke-linejoin="round"/>
                                <line x1="39" y1="14" x2="39" y2="25" stroke="#7c3aed" stroke-width="1" stroke-dasharray="1 2"/>
                                <line x1="40" y1="20" x2="43" y2="20" stroke="#7c3aed" stroke-width="1.2" stroke-linecap="round"/>
                                <rect x="50" y="13" width="3" height="2" rx="0.5" stroke="#7c3aed" stroke-width="1" fill="none"/>
                                <line x1="4" y1="6" x2="4" y2="2" stroke="#7c3aed" stroke-width="1.5" stroke-linecap="round"/>
                                <path d="M38 26 Q41 28 44 26" stroke="#7c3aed" stroke-width="1.2" fill="none"/>
                                <path d="M8 26 Q11 28 14 26" stroke="#7c3aed" stroke-width="1.2" fill="none"/>
                                <circle cx="11" cy="27" r="4.5" stroke="#7c3aed" stroke-width="1.5" fill="none" class="aiko-wheel"/>
                                <circle cx="11" cy="27" r="1.5" stroke="#7c3aed" stroke-width="1" fill="none"/>
                                <line x1="11" y1="22.5" x2="11" y2="31.5" stroke="#7c3aed" stroke-width="0.8" class="aiko-wheel"/>
                                <line x1="6.5" y1="27" x2="15.5" y2="27" stroke="#7c3aed" stroke-width="0.8" class="aiko-wheel"/>
                                <circle cx="41" cy="27" r="4.5" stroke="#7c3aed" stroke-width="1.5" fill="none" class="aiko-wheel"/>
                                <circle cx="41" cy="27" r="1.5" stroke="#7c3aed" stroke-width="1" fill="none"/>
                                <line x1="41" y1="22.5" x2="41" y2="31.5" stroke="#7c3aed" stroke-width="0.8" class="aiko-wheel"/>
                                <line x1="36.5" y1="27" x2="45.5" y2="27" stroke="#7c3aed" stroke-width="0.8" class="aiko-wheel"/>
                            </svg>
                            <div class="aiko-road">
                                <div class="aiko-road-dash d1"></div>
                                <div class="aiko-road-dash d2"></div>
                                <div class="aiko-road-dash d3"></div>
                            </div>
                        </div>

                        <div class="aiko-think-dots-wrap">
                            <span class="aiko-tdot d1"></span>
                            <span class="aiko-tdot d2"></span>
                            <span class="aiko-tdot d3"></span>
                        </div>

                        <span class="aiko-think-text"></span>
                    </div>
                </div>`);

            $messages.find('.aiko-empty-state').remove();
            $messages.append($bubble);
            startThinkCycle($bubble.find('.aiko-think-text')[0]);
            pageScrollToBottom();
        }

        function removePageThinking() {
            stopThinkCycle();
            isThinking = false;
            $('#aiko-page-thinking').remove();
            $('#aiko-page-stop-btn').hide();
            $('#aiko-page-send-btn').show();
        }

        // ── STOP BUTTON ───────────────────────────────────────────────────
        $('#aiko-page-stop-btn').on('click', function () {
            if (!isThinking) return;
            responseStopped = true;
            const stoppedRequestId = currentRequestId;
            if (stoppedRequestId) {
                abortedRequests.add(stoppedRequestId);
                // Tell the backend to skip saving when the job finishes
                frappe.call({
                    method: 'frappe_assistant_core.aiko.api.cancel_chat',
                    args: { request_id: stoppedRequestId },
                    // fire-and-forget — ignore success/error
                });
            } else {
                abortedRequests.add('thread:' + thread_id);
            }
            if (pendingXhr && typeof pendingXhr.abort === 'function') {
                pendingXhr.abort();
            }
            removePageThinking();
        appendPageMessage('assistant', '_Response stopped._');
        pageScrollToBottom();
        frappe.call({
            method: 'frappe_assistant_core.aiko.api.save_stopped_message',
            args: { thread_id: thread_id },
        });
        messageCount += 2;
        checkMessageLimit();
        });

        // ── AUTO-RESIZE TEXTAREA ──────────────────────────────────────────
        $('#aiko-page-input').on('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 160) + 'px';
        });

        // ── SEND ──────────────────────────────────────────────────────────
        function sendPageMessage() {
            if (isThinking) return;
            const $input = $('#aiko-page-input');
            const text   = $input.val().trim();
            if (!text) return;

            $input.val('').css('height', 'auto');
            appendPageMessage('user', text);
            // FIX #5: reset currentRequestId before each new send so stale
            // abort state from a prior request cannot bleed into this one
            currentRequestId = frappe.utils.get_random(10);
            responseStopped = false;
            showPageThinking();

            pendingXhr = frappe.call({
                method: 'frappe_assistant_core.aiko.api.chat',
                args: { message: text, thread_id: thread_id, request_id: currentRequestId },
                callback: function (r) {
                    // This only confirms the job was queued — the real answer
                    // arrives via the 'aiko_done' realtime event.
                    if (!r.message || !r.message.success) {
                        if (abortedRequests.has(currentRequestId)) return;
                        removePageThinking();
                        appendPageMessage('error', 'Could not start the request. Please try again.');
                    }
                },
                error: function () {
                    if (abortedRequests.has(currentRequestId)) return;
                    removePageThinking();
                    appendPageMessage('error', 'Network error or server unavailable.');
                }
            });
        }

        $('#aiko-page-send-btn').on('click', sendPageMessage);
        $('#aiko-page-input').on('keydown', function (e) {
            if (e.which === 13 && !e.shiftKey) { e.preventDefault(); sendPageMessage(); }
        });

        // ── REALTIME LISTENERS ────────────────────────────────────────────
        frappe.realtime.on('aiko_stage', function (data) {
            if (!isThinking) return;
            if (data.thread_id !== thread_id) return;
            if (data.request_id !== currentRequestId) return;
            updateThinkingStage(data.stage);
        });

        frappe.realtime.on('aiko_done', function (data) {
            if (data.thread_id  !== thread_id)                            return;
            if (responseStopped) {
                responseStopped = false;
                return;
            }
            if (abortedRequests.has(data.request_id)) {
                abortedRequests.delete(data.request_id);
                return;
            }
            if (abortedRequests.has('thread:' + data.thread_id)) {
                abortedRequests.delete('thread:' + data.thread_id);
                return;
            }
            if (currentRequestId && data.request_id !== currentRequestId) return;
            removePageThinking();
            if (data.success) {
                appendPageMessage('assistant', data.data);
                if (data.session_name && !currentSessionName) {
                    currentSessionName = data.session_name;
                    updateSessionLabel(data.session_name);
                    loadSidebarSessions(function () {
                        $(`[data-session-name="${data.session_name}"]`).addClass('active');
                    });
                }
                messageCount += 2;
                checkMessageLimit();
            } else {
                appendPageMessage('error', data.error || 'An error occurred.');
            }
        });

        // ── BOOT ──────────────────────────────────────────────────────────
        loadSidebarSessions();
        const urlParams         = new URLSearchParams(window.location.search);
        const sessionFromWidget = urlParams.get('session');
        const threadFromWidget  = urlParams.get('thread');
        const wasThinking       = urlParams.get('thinking') === '1';

        if (sessionFromWidget) {
            loadSession(sessionFromWidget, threadFromWidget);
            if (wasThinking) {
                const pendingMsg = urlParams.get('pending');
                setTimeout(function () {
                    if (pendingMsg) appendPageMessage('user', pendingMsg, false);
                    showPageThinking();
                }, 800);
            }
        } else if (threadFromWidget && wasThinking) {
            thread_id = threadFromWidget;
            const pendingMsg = urlParams.get('pending');
            if (pendingMsg) appendPageMessage('user', pendingMsg, false);
            showPageThinking();
        } else {
            showEmptyState();
        }

        $('#aiko-page-input').focus();

    } 
};