$(document).ready(function () {
    if (frappe.session.user === "Guest") return;

    // ── THINKING PHRASES ──────────────────────────────────────────────────
    const THINK_PHRASES = [
        "Searching through your data…",
        "Looking into this…",
        "Checking records…",
        "Digging through documents…",
        "Pulling that up…",
        "Scanning through everything…",
        "Let me check on this…",
        "Going through the details…",
        "Fetching the latest info…",
        "Almost there…"
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
        stopThinkCycle();
        const $el = $('#aiko-thinking .aiko-think-text');
        if (!$el.length || !text) return;
        $el.removeClass('aiko-think-visible');
        setTimeout(function () {
            $el.text(text);
            $el.addClass('aiko-think-visible');
        }, 220);
    }

    // ── HTML TEMPLATE ─────────────────────────────────────────────────────
    const chatHtml = `
        <div id="aiko-chat-widget">
            <div id="aiko-chat-button" title="Chat with AIKO">
                <span class="aiko-notif-badge" id="aiko-notif-badge"></span>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            </div>
            <div id="aiko-chat-window" style="display: none;">
                <div class="aiko-chat-header">
                    <h4>AIKO Assistant</h4>
                    <div class="aiko-chat-header-actions">
                        <button id="aiko-history-btn" title="Chat History">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                        </button>
                        <button id="aiko-new-chat-btn" title="New Chat">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                        </button>
                        <button id="aiko-chat-fullscreen" title="Open fullscreen">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
                        </button>
                        <button id="aiko-chat-close">&times;</button>
                    </div>
                </div>

                <div id="aiko-sessions-panel" class="aiko-sessions-panel hidden">
                    <div class="aiko-sessions-header">
                        <span>Recent Chats</span>
                        <button id="aiko-sessions-close" title="Close">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                        </button>
                    </div>
                    <div id="aiko-sessions-list" class="aiko-sessions-list">
                        <div class="aiko-sessions-loading">Loading chats...</div>
                    </div>
                </div>

                <div class="aiko-chat-messages" id="aiko-chat-messages"></div>

                <div id="aiko-scroll-btn" class="aiko-scroll-btn hidden">
                    <span id="aiko-scroll-label">↓</span>
                </div>

                <div class="aiko-chat-input-area">
                    <textarea id="aiko-chat-input" placeholder="Ask something…" autocomplete="off" rows="1"></textarea>
                    <button id="aiko-chat-send">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                    </button>
                    <button id="aiko-stop-btn" title="Stop generating" style="display: none;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="7" y="7" width="10" height="10" fill="currentColor" stroke="none"></rect>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;

    $('body').append(chatHtml);
    $('body').append('<div id="aiko-toast"></div>');
    $('#aiko-toast').on('click', function () {
        $('#aiko-chat-window').show();
        clearResponseNotification();
        $('#aiko-chat-input').focus();
    });

    // ── STATE ─────────────────────────────────────────────────────────────
    let thread_id          = frappe.utils.get_random(10);
    let isThinking         = false;
    let currentSessionName = null;
    let currentRequestId   = null;
    let hasAutoLoaded      = false;
    let messageCount       = 0;
    let abortedRequests    = new Set();
    let responseStopped       = false;
    let pendingXhr         = null;

    // ── WIDGET VISIBILITY ─────────────────────────────────────────────────
    function syncWidgetVisibility() {
        let onFullPage = false;
        if (typeof frappe.get_route === 'function') {
            const route = frappe.get_route();
            onFullPage = route && route[0] === 'aiko-chat';
        } else {
            onFullPage = window.location.pathname.includes('/aiko_chat');
        }

        if (sessionStorage.getItem('aiko_open_widget') === '1') {
            const savedSession = sessionStorage.getItem('aiko_widget_session');
            const savedThread  = sessionStorage.getItem('aiko_widget_thread');
            const wasThinking  = sessionStorage.getItem('aiko_widget_thinking') === '1';
            const pendingMsg   = sessionStorage.getItem('aiko_widget_pending') || '';
            sessionStorage.removeItem('aiko_open_widget');
            sessionStorage.removeItem('aiko_widget_session');
            sessionStorage.removeItem('aiko_widget_thread');
            sessionStorage.removeItem('aiko_widget_thinking');
            sessionStorage.removeItem('aiko_widget_pending');

            $('#aiko-chat-window').show();
            hasAutoLoaded = true;

            if (savedSession) {
                loadSession(savedSession, savedThread);
                if (wasThinking) {
                    setTimeout(function () {
                        if (pendingMsg) appendMessage('user', pendingMsg, false);
                        showThinking();
                    }, 800);
                }
            } else if (savedThread && wasThinking) {
                thread_id = savedThread;
                if (pendingMsg) appendMessage('user', pendingMsg, false);
                showThinking();
            } else {
                autoLoadLastSession();
            }
        }

        if (onFullPage) {
            $('#aiko-chat-widget').addClass('aiko-widget-hidden');
        } else {
            $('#aiko-chat-widget').removeClass('aiko-widget-hidden');
        }
    }

    if (frappe.router) {
        frappe.router.on('change', function () { syncWidgetVisibility(); });
    }
    syncWidgetVisibility();

    // ── SCROLL TRACKING ───────────────────────────────────────────────────
    let isScrolledUp = false;

    $('#aiko-chat-messages').on('scroll', function () {
        const el = this;
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        isScrolledUp = distFromBottom > 80;
        if (isScrolledUp) {
            $('#aiko-scroll-btn').removeClass('hidden');
        } else {
            $('#aiko-scroll-btn').addClass('hidden');
            $('#aiko-scroll-label').text('↓');
            $('#aiko-scroll-btn').removeClass('aiko-scroll-btn-new');
        }
    });

    $('#aiko-scroll-btn').on('click', function () { scrollToBottom(); });

    // ── HELPERS ───────────────────────────────────────────────────────────
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

    // ── EMPTY STATE ───────────────────────────────────────────────────────
    function showEmptyState() {
        const allSuggestions = [
            { label: "Fleet overview",       prompt: "How many vehicles are in the fleet?" },
            { label: "Active vehicles",      prompt: "List active vehicles." },
            { label: "Compliance alerts",    prompt: "Which vehicles have expired compliance documents?" },
            { label: "Expiring soon",        prompt: "Which compliances are expiring soon?" },
            { label: "Open inspections",     prompt: "Show all open inspections." },
            { label: "Overdue inspections",  prompt: "Which inspections are overdue?" },
            { label: "Open issues",          prompt: "Show all issues." },
            { label: "High priority issues", prompt: "Show all high priority issues." },
            { label: "Critical faults",      prompt: "Show all critical faults." },
            { label: "Work orders",          prompt: "Show all submitted work orders." },
            { label: "Overdue work orders",  prompt: "Which work orders are overdue?" },
            { label: "Fuel entries today",   prompt: "Show fuel entries for today." },
            { label: "Service reminders",    prompt: "Show all upcoming service reminders." },
            { label: "Active trips",         prompt: "What trips are active right now?" },
            { label: "Today's bookings",     prompt: "Show today's bookings." },
            { label: "Pending bookings",     prompt: "Show pending bookings." },
        ];
        const picked    = allSuggestions.sort(() => Math.random() - 0.5).slice(0, 4);
        const chipsHtml = picked.map(s =>
            `<button class="aiko-suggestion-chip" data-prompt="${s.prompt}">${s.label}</button>`
        ).join('');

        $('#aiko-chat-messages').html(`
            <div class="aiko-empty-state">
                <div class="aiko-empty-icon">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                </div>
                <h3>How can I help?</h3>
                <p>Ask me anything about your fleet.</p>
                <div class="aiko-suggestions">
                    ${chipsHtml}
                </div>
            </div>
        `);

        $('#aiko-chat-messages').off('click', '.aiko-suggestion-chip').on('click', '.aiko-suggestion-chip', function () {
            $('#aiko-chat-input').val($(this).data('prompt'));
            sendMessage();
        });
    }

    // ── AUTO-LOAD LAST SESSION ────────────────────────────────────────────
    function autoLoadLastSession() {
        $('#aiko-chat-messages').html('<div class="aiko-sessions-loading" id="aiko-msg-loading">Loading…</div>');
        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
            callback: function (r) {
                if (r.message && r.message.success && r.message.sessions && r.message.sessions.length > 0) {
                    loadSession(r.message.sessions[0].name, r.message.sessions[0].thread_id);
                } else {
                    $('#aiko-chat-messages').html('');
                    showEmptyState();
                }
            },
            error: function () {
                $('#aiko-chat-messages').html('');
                showEmptyState();
            }
        });
    }

    // ── OPEN / CLOSE ──────────────────────────────────────────────────────
    $('#aiko-chat-button').on('click', function () {
        const $win = $('#aiko-chat-window');
        if ($win.is(':visible')) {
            $win.css({ animation: 'aiko-scale-out 0.28s cubic-bezier(0.4, 0, 1, 1) forwards' });
            setTimeout(function () {
                $win.hide().css({ animation: '' });
            }, 260);
        } else {
            $win.show().css({ animation: 'aiko-scale-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards' });
            clearResponseNotification();
            if (!hasAutoLoaded) {
                hasAutoLoaded = true;
                autoLoadLastSession();
            }
            $('#aiko-chat-input').focus();
        }
    });

    $('#aiko-chat-close').on('click', function () {
        const $win = $('#aiko-chat-window');
        $win.css({ animation: 'aiko-scale-out 0.28s cubic-bezier(0.4, 0, 1, 1) forwards' });
        setTimeout(function () {
            $win.hide().css({ animation: '' });
        }, 260);
    });

    $('#aiko-chat-fullscreen').on('click', function () {
        $('#aiko-chat-window').hide();
        let params = '?thread=' + thread_id;
        if (currentSessionName) params += '&session=' + currentSessionName;
        if (isThinking) {
            params += '&thinking=1';
            const lastUserMsg = $('#aiko-chat-messages .aiko-message.user').last().find('.aiko-bubble').text().trim();
            if (lastUserMsg) params += '&pending=' + encodeURIComponent(lastUserMsg);
        }
        window.location.href = '/aiko_chat' + params;
    });

    // ── NEW CHAT ──────────────────────────────────────────────────────────
    $('#aiko-new-chat-btn').on('click', function () { startNewChat(); });

    function startNewChat() {
        thread_id          = frappe.utils.get_random(10);
        currentSessionName = null;
        currentRequestId   = null;
        messageCount       = 0;
        abortedRequests.clear();

        $('#aiko-limit-banner').remove();
        $('#aiko-chat-send').prop('disabled', false);
        $('#aiko-chat-input').prop('disabled', false).attr('placeholder', 'Ask something…');
        $('.aiko-chat-input-area').removeClass('aiko-input-disabled');

        $('#aiko-chat-messages').html('');
        $('#aiko-scroll-btn').addClass('hidden');
        showEmptyState();
        hideSessionsPanel();
        $('#aiko-chat-input').focus();
    }

    // ── HISTORY PANEL ─────────────────────────────────────────────────────
    $('#aiko-history-btn').on('click', function () {
        const panel = $('#aiko-sessions-panel');
        if (panel.hasClass('hidden')) showSessionsPanel();
        else hideSessionsPanel();
    });

    $('#aiko-sessions-close').on('click', function () { hideSessionsPanel(); });

    function showSessionsPanel() {
        $('#aiko-sessions-panel').removeClass('hidden');
        loadSessionsList();
    }

    function hideSessionsPanel() {
        $('#aiko-sessions-panel').addClass('hidden');
    }

    function loadSessionsList() {
        $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Loading chats…</div>');
        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
            callback: function (r) {
                if (r.message && r.message.success) {
                    renderSessionsList(r.message.sessions);
                } else {
                    $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Could not load chats.</div>');
                }
            },
            error: function () {
                $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Network error.</div>');
            }
        });
    }

    function renderSessionsList(sessions) {
        if (!sessions || sessions.length === 0) {
            $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">No previous chats found.</div>');
            return;
        }
        let html = '';
        sessions.forEach(function (s) {
            const timeLabel = formatRelativeTime(s.preview_time || s.last_active);
            const title     = sessionDisplayTitle(s);
            const isActive  = (s.name === currentSessionName) ? 'active' : '';
            html += `
                <div class="aiko-session-item ${isActive}" data-session-name="${s.name}" data-thread-id="${s.thread_id}">
                    <div class="aiko-session-title">${escapeHtml(title)}</div>
                    <div class="aiko-session-preview">${escapeHtml(s.preview || '')}</div>
                    <div class="aiko-session-time">${timeLabel}</div>
                </div>`;
        });
        $('#aiko-sessions-list').html(html);
        $('#aiko-sessions-list').off('click', '.aiko-session-item').on('click', '.aiko-session-item', function () {
            loadSession($(this).data('session-name'), $(this).data('thread-id'));
        });
    }

    // ── LOAD SESSION ──────────────────────────────────────────────────────
    function loadSession(sessionName, sessionThreadId) {
        hideSessionsPanel();
        currentSessionName = sessionName;
        thread_id          = sessionThreadId;
        $('#aiko-chat-messages').html('<div class="aiko-sessions-loading" id="aiko-msg-loading">Loading messages…</div>');

        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
            args: { session_name: sessionName, limit: 20 },
            callback: function (r) {
                $('#aiko-msg-loading').remove();
                $('#aiko-chat-messages').html('');

                if (r.message && r.message.success) {
                    const msgs = r.message.messages;
                    if (msgs.length === 0) {
                        showEmptyState();
                    } else {
                        messageCount = 0;
                        msgs.forEach(function (m) { appendMessage(m.role, m.content, false, m.creation); });
                        checkMessageLimit();
                        scrollToBottom();
                    }
                } else {
                    showEmptyState();
                }
            },
            error: function () {
                $('#aiko-msg-loading').remove();
                showEmptyState();
            }
        });
    }

    // ── MARKDOWN RENDERER ─────────────────────────────────────────────────
    function renderMarkdown(text) {
        text = text.replace(/\r\n/g, '\n').replace(/[ \t]+$/gm, '');

        const codeBlocks = [];
        text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, function (_, lang, code) {
            const idx = codeBlocks.length;
            codeBlocks.push({ lang: lang || 'text', code: code.trimEnd() });
            return `\x00CODE${idx}\x00`;
        });

        const tables = [];
        text = text.replace(/^(\|.+\|\n)([ \t]*\|[-| :]+\|\n)((?:[ \t]*\|.+\|\n?)+)/gm,
            function (_, header, _sep, body) {
                const idx = tables.length;

                function parseRow(row) {
                    return row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
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
                const th = headers.map(h => `<th>${inlineMarkdown(h)}</th>`).join('');
                const tr = rows.map(r =>
                    '<tr>' + r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('') + '</tr>'
                ).join('');

                tables.push(
                    `<div class="aiko-table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`
                );
                return `\x00TABLE${idx}\x00`;
            }
        );

        let html = text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
            .replace(/^### (.+)$/gm,  '<h3>$1</h3>')
            .replace(/^## (.+)$/gm,   '<h2>$1</h2>')
            .replace(/^# (.+)$/gm,    '<h1>$1</h1>')
            .replace(/\*\*\*(.+?)\*\*\*/gs, '<strong><em>$1</em></strong>')
            .replace(/\*\*(.+?)\*\*/gs,     '<strong>$1</strong>')
            .replace(/\*(.+?)\*/gs,         '<em>$1</em>')
            .replace(/_([^_]+)_/g,          '<em>$1</em>')
            .replace(/`([^`]+)`/g,          '<code>$1</code>')
            .replace(/^---$/gm,             '<hr>')
            .replace(/^&gt; (.+)$/gm,       '<blockquote><p>$1</p></blockquote>')
            .replace(/^\s*[-*] (.+)$/gm,    '<li>$1</li>')
            .replace(/^\s*\d+\. (.+)$/gm,   '<oli>$1</oli>')
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        html = html.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, m => '<ul>' + m + '</ul>');
        html = html.replace(/(<oli>[\s\S]*?<\/oli>\n?)+/g, m =>
            '<ol>' + m.replace(/<oli>/g, '<li>').replace(/<\/oli>/g, '</li>') + '</ol>');

        html = html.split(/\n{2,}/).map(function (block) {
            block = block.trim();
            if (!block) return '';
            if (/^<(h[1-6]|ul|ol|hr|blockquote|pre|div)/.test(block)) return block;
            if (/^\x00TABLE\d+\x00$/.test(block)) return block;
            return '<p>' + block.replace(/\n/g, '<br>') + '</p>';
        }).join('\n');

        html = html.replace(/\x00TABLE(\d+)\x00/g, (_, idx) => tables[parseInt(idx)]);

        html = html.replace(/\x00CODE(\d+)\x00/g, function (_, idx) {
            const { lang, code } = codeBlocks[parseInt(idx)];
            const escaped = code
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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

    // ── MESSAGE BUILDING ──────────────────────────────────────────────────
    function buildMessageHtml(role, text, creation) {
        let content = (role === 'assistant') ? renderMarkdown(text) : escapeHtml(text);
        const time  = formatTimestamp(creation);
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
                    <div class="aiko-bubble">${content}</div>
                    <div class="aiko-message-footer">
                        <span class="aiko-timestamp">${time}</span>
                        ${copyBtn}
                    </div>
                </div>
            </div>`;
    }

    function appendMessage(role, text, doScroll, creation) {
        if (doScroll === undefined) doScroll = true;
        $('#aiko-chat-messages').find('.aiko-empty-state').remove();
        $('#aiko-chat-messages').append(buildMessageHtml(role, text, creation));
        messageCount++;
        if (doScroll) {
            if (isScrolledUp) {
                $('#aiko-scroll-label').text('New message ↓');
                $('#aiko-scroll-btn').removeClass('hidden').addClass('aiko-scroll-btn-new');
            } else {
                scrollToBottom();
            }
        }
    }

    function scrollToBottom() {
        const el = $('#aiko-chat-messages')[0];
        el.scrollTop = el.scrollHeight;
        isScrolledUp = false;
        $('#aiko-scroll-btn').addClass('hidden');
        $('#aiko-scroll-label').text('↓');
        $('#aiko-scroll-btn').removeClass('aiko-scroll-btn-new');
    }

    // ── COPY BUTTONS ──────────────────────────────────────────────────────
    $('#aiko-chat-messages').on('click', '.aiko-copy-btn', function () {
        const text = $(this).data('text');
        navigator.clipboard && navigator.clipboard.writeText(text).then(() => {
            $(this).text('Copied!');
            const self = this;
            setTimeout(function () {
                $(self).html(`
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg> Copy`);
            }, 1500);
        });
    });

    $('#aiko-chat-messages').on('click', '.aiko-code-copy', function () {
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

    // ── THINKING ──────────────────────────────────────────────────────────
    function showThinking() {
        isThinking = true;

        $('#aiko-chat-send').hide();
        $('#aiko-stop-btn').css('display', 'flex');
        $('#aiko-chat-button').addClass('aiko-thinking-pulse');

        const $bubble = $(`
        <div class="aiko-message assistant" id="aiko-thinking">
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
                        <line x1="6.5"  y1="27" x2="15.5" y2="27" stroke="#7c3aed" stroke-width="0.8" class="aiko-wheel"/>
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

        $('#aiko-chat-messages').find('.aiko-empty-state').remove();
        $('#aiko-chat-messages').append($bubble);
        startThinkCycle($bubble.find('.aiko-think-text')[0]);
        scrollToBottom();
    }

    function removeThinking() {
        stopThinkCycle();
        isThinking = false;
        $('#aiko-chat-button').removeClass('aiko-thinking-pulse');
        $('#aiko-thinking').remove();
        $('#aiko-stop-btn').hide();
        $('#aiko-chat-send').show();
    }

    // ── STOP BUTTON ───────────────────────────────────────────────────────
    $('#aiko-stop-btn').on('click', function () {
        if (!isThinking) return;
        responseStopped = true;
        const stoppedRequestId = currentRequestId;
        if (stoppedRequestId) {
            abortedRequests.add(stoppedRequestId);
            frappe.call({
                method: 'frappe_assistant_core.aiko.api.cancel_chat',
                args: { request_id: stoppedRequestId },
            });
        } else {
            abortedRequests.add('thread:' + thread_id);
        }
        if (pendingXhr && typeof pendingXhr.abort === 'function') {
            pendingXhr.abort();
        }
        removeThinking();
        appendMessage('assistant', '_Response stopped._');
        scrollToBottom();
        frappe.call({
            method: 'frappe_assistant_core.aiko.api.save_stopped_message',
            args: { thread_id: thread_id },
        });
        messageCount++;
        checkMessageLimit();
            });

    // ── MESSAGE LIMIT ─────────────────────────────────────────────────────
    function checkMessageLimit() {
        if (messageCount >= 20) {
            $('#aiko-chat-send').prop('disabled', true);
            $('#aiko-chat-input').prop('disabled', true).attr('placeholder', 'Message limit reached.');
            $('.aiko-chat-input-area').addClass('aiko-input-disabled');

            if (!$('#aiko-limit-banner').length) {
                $('.aiko-chat-input-area').before(`
                    <div id="aiko-limit-banner" class="aiko-limit-banner">
                        <p>This chat has reached 20 messages.<br>Start a new session to continue.</p>
                        <button class="aiko-limit-new-chat-btn" id="aiko-widget-limit-new-chat">+ New Chat</button>
                    </div>`);
                $('#aiko-widget-limit-new-chat').on('click', function () { startNewChat(); });
            }
        }
    }

    // ── SEND ──────────────────────────────────────────────────────────────
    function sendMessage() {
        if (isThinking) return;
        const input = $('#aiko-chat-input');
        const text  = input.val().trim();
        if (!text) return;

        input.val('').css('height', 'auto');
        appendMessage('user', text);
        currentRequestId = frappe.utils.get_random(10);
        responseStopped = false;
        showThinking();

        frappe.call({
            method: 'frappe_assistant_core.aiko.api.chat',
            args: { message: text, thread_id: thread_id, request_id: currentRequestId },
            callback: function (r) {
                if (!r.message || !r.message.success) {
                    if (!isThinking) return;
                    removeThinking();
                    appendMessage('assistant', 'Could not start the request. Please try again.');
                }
            },
            error: function () {
                if (!isThinking) return;
                removeThinking();
                appendMessage('assistant', 'Network error or server unavailable.');
            }
        });
    }

    $('#aiko-chat-input').on('keydown', function (e) {
        if (e.which === 13 && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    $('#aiko-chat-input').on('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 100) + 'px';
    });

    $('#aiko-chat-send').on('click', function () { sendMessage(); });

    // ── REALTIME LISTENERS ────────────────────────────────────────────────
    frappe.realtime.on('aiko_stage', function (data) {
        if (!isThinking) return;
        if (data.thread_id  !== thread_id)        return;
        if (data.request_id !== currentRequestId) return;
        updateThinkingStage(data.stage);
    });

    function showResponseNotification(previewText) {
        $('#aiko-notif-badge').show().addClass('visible');
        if (!$('#aiko-chat-window').is(':visible')) {
            const preview = previewText.replace(/[#*`]/g, '').substring(0, 60);
            $('#aiko-toast').text('AIKO: ' + preview + (previewText.length > 60 ? '…' : ''));
            $('#aiko-toast').fadeIn(200);
            clearTimeout(window._aikoToastTimer);
            window._aikoToastTimer = setTimeout(function () {
                $('#aiko-toast').fadeOut(300);
            }, 4000);
        }
    }

    function clearResponseNotification() {
        $('#aiko-notif-badge').hide().removeClass('visible');
        $('#aiko-toast').fadeOut(200);
    }
    frappe.realtime.on('aiko_done', function (data) {
        if (data.thread_id !== thread_id) return;
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
        removeThinking();
        if (data.success) {
            appendMessage('assistant', data.data);
            if (data.session_name && !currentSessionName) {
                currentSessionName = data.session_name;
            }
            showResponseNotification(data.data);
            checkMessageLimit();
        } else {
            appendMessage('assistant', data.error || 'An error occurred.');
        }
    });


    // ── VOICE INPUT (live preview + whisper refine) ──────────────────────────
function initVoiceInput() {
    const micBtn = document.getElementById('aiko-mic-btn');
    const chatInput = document.getElementById('aiko-chat-input');
    if (!micBtn || !chatInput) return;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        micBtn.style.display = 'none';
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let liveRecognition = null;
    let liveBaseText = '';

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let stream = null;

    function startLivePreview() {
        if (!SpeechRecognition) return;
        liveRecognition = new SpeechRecognition();
        liveRecognition.continuous = true;
        liveRecognition.interimResults = true;
        liveRecognition.lang = 'en-IN';

        liveRecognition.onresult = (event) => {
            let finalText = '';
            let interimText = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) finalText += transcript;
                else interimText += transcript;
            }
            if (finalText) liveBaseText += finalText;
            chatInput.value = (liveBaseText + interimText).trim();
            chatInput.style.height = 'auto';
            chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
        };

        liveRecognition.onerror = (e) => {
            console.warn('Live preview error (non-fatal):', e.error);
        };

        try {
            liveRecognition.start();
        } catch (e) {
            console.warn('Live preview could not start:', e);
        }
    }

    function stopLivePreview() {
        if (liveRecognition) {
            try { liveRecognition.stop(); } catch (e) {}
            liveRecognition = null;
        }
    }

    async function startRecording() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            console.error('Mic access error:', err);
            frappe.show_alert({ message: 'Microphone access denied', indicator: 'red' });
            return;
        }

        audioChunks = [];
        liveBaseText = '';
        chatInput.value = '';

        const mimeType = MediaRecorder.isTypeSupported('audio/webm')
            ? 'audio/webm'
            : 'audio/ogg';
        mediaRecorder = new MediaRecorder(stream, { mimeType });

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            stream.getTracks().forEach((t) => t.stop());
            const audioBlob = new Blob(audioChunks, { type: mimeType });
            transcribeBlob(audioBlob, mimeType);
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        startLivePreview();
    }

    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            micBtn.classList.remove('recording');
        }
        stopLivePreview();
    }

    function transcribeBlob(audioBlob, mimeType) {
        micBtn.classList.add('aiko-mic-transcribing');
        const placeholderBefore = chatInput.placeholder;
        chatInput.placeholder = 'Refining transcription…';

        const reader = new FileReader();
        reader.onloadend = function () {
            const base64Audio = reader.result.split(',')[1];

            frappe.call({
                method: 'frappe_assistant_core.api.voice_transcriber.transcribe_base64',
                args: {
                    audio_base64: base64Audio,
                    model_size: 'medium'
                },
                callback: function (r) {
                    micBtn.classList.remove('aiko-mic-transcribing');
                    chatInput.placeholder = placeholderBefore;

                    if (r.message && r.message.success && r.message.text) {
                        chatInput.value = r.message.text.trim();
                        chatInput.style.height = 'auto';
                        chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
                        chatInput.focus();
                    }
                    // If whisper fails, the live preview text (already in the box) stays as-is — silent fallback
                },
                error: function () {
                    micBtn.classList.remove('aiko-mic-transcribing');
                    chatInput.placeholder = placeholderBefore;
                    // Live preview text stays in the box even if whisper refine fails
                }
            });
        };
        reader.readAsDataURL(audioBlob);
    }

    micBtn.addEventListener('click', () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    });
}

initVoiceInput();

});