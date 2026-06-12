$(document).on('startup', function () {
    if (frappe.session.user === "Guest") return;

    function injectAikoWidget() {
        // Widget already exists — just make sure it's still in the body
        // (Frappe SPA sometimes moves/detaches DOM nodes on navigation)
        const existing = document.getElementById('aiko-chat-widget');
        if (existing) {
            // Re-append to body if it got detached during SPA navigation
            if (!document.body.contains(existing)) {
                document.body.appendChild(existing);
            }
            return; // Never re-init logic
        }

        // First time: build the HTML and init logic once
        const chatHtml = `
            <div id="aiko-chat-widget">
                <div id="aiko-chat-button" title="Chat with AIKO">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                </div>
                <div id="aiko-chat-window" style="display: none;">
                    <div class="aiko-chat-header">
                        <h4>AIKO Assistant</h4>
                        <div class="aiko-header-actions">
                            <button id="aiko-history-btn" title="Chat History">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                            </button>
                            <button id="aiko-new-chat-btn" title="New Chat">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
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

                    <div class="aiko-chat-messages" id="aiko-chat-messages">
                        <div id="aiko-load-more" class="aiko-load-more hidden">
                            <button id="aiko-load-more-btn">Load older messages</button>
                        </div>
                        <!-- Welcome message injected by JS once -->
                    </div>
                    <div class="aiko-chat-input-area">
                        <input type="text" id="aiko-chat-input" placeholder="Ask something..." autocomplete="off" />
                        <button id="aiko-chat-send">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                        </button>
                    </div>
                </div>
            </div>
        `;

        $('body').append(chatHtml);
        initAikoLogic();
    }

    function initAikoLogic() {
        let thread_id = frappe.utils.get_random(10);
        let isThinking = false;
        let currentSessionName = null;
        let oldestMessageCreation = null;
        let hasMoreMessages = false;
        let isLoadingHistory = false;

        // Show welcome message once on first load only
        appendWelcomeMessage();

        // ── OPEN / CLOSE ──────────────────────────────────────────────────────────
        // Purely toggles visibility — never touches message list
        $('#aiko-chat-button').on('click', function () {
            const win = $('#aiko-chat-window');
            win.toggle();
            if (win.is(':visible')) $('#aiko-chat-input').focus();
        });

        $('#aiko-chat-close').on('click', function () {
            $('#aiko-chat-window').hide();
        });

        // ── NEW CHAT ──────────────────────────────────────────────────────────────
        $('#aiko-new-chat-btn').on('click', function () { startNewChat(); });

        function startNewChat() {
            thread_id = frappe.utils.get_random(10);
            currentSessionName = null;
            oldestMessageCreation = null;
            hasMoreMessages = false;
            // Only place messages are ever cleared — explicit user action
            $('#aiko-chat-messages').html(`
                <div id="aiko-load-more" class="aiko-load-more hidden">
                    <button id="aiko-load-more-btn">Load older messages</button>
                </div>
            `);
            bindLoadMoreBtn();
            hideSessionsPanel();
            appendWelcomeMessage();
            $('#aiko-chat-input').focus();
        }

        // ── HISTORY PANEL ─────────────────────────────────────────────────────────
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
            $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Loading chats...</div>');
            frappe.call({
                method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
                callback: function (r) {
                    if (r.message && r.message.success) renderSessionsList(r.message.sessions);
                    else $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Could not load chats.</div>');
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
                const title = s.title || ('Chat ' + (s.thread_id || s.name).substring(0, 8));
                const isActive = (s.name === currentSessionName) ? 'active' : '';
                html += `
                    <div class="aiko-session-item ${isActive}" data-session-name="${s.name}" data-thread-id="${s.thread_id}">
                        <div class="aiko-session-title">${escapeHtml(title)}</div>
                        <div class="aiko-session-preview">${escapeHtml(s.preview || '')}</div>
                        <div class="aiko-session-time">${timeLabel}</div>
                    </div>
                `;
            });
            $('#aiko-sessions-list').html(html);
            $('#aiko-sessions-list').off('click', '.aiko-session-item').on('click', '.aiko-session-item', function () {
                loadSession($(this).data('session-name'), $(this).data('thread-id'));
            });
        }

        // ── LOAD SESSION ──────────────────────────────────────────────────────────
        function loadSession(sessionName, sessionThreadId) {
            hideSessionsPanel();
            currentSessionName = sessionName;
            thread_id = sessionThreadId;
            oldestMessageCreation = null;
            hasMoreMessages = false;

            $('#aiko-chat-messages').html(`
                <div id="aiko-load-more" class="aiko-load-more hidden">
                    <button id="aiko-load-more-btn">Load older messages</button>
                </div>
                <div class="aiko-sessions-loading" id="aiko-msg-loading">Loading messages...</div>
            `);
            bindLoadMoreBtn();

            frappe.call({
                method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
                args: { session_name: sessionName, limit: 20 },
                callback: function (r) {
                    $('#aiko-msg-loading').remove();
                    if (r.message && r.message.success) {
                        const msgs = r.message.messages;
                        hasMoreMessages = r.message.has_more;
                        if (msgs.length === 0) {
                            appendWelcomeMessage();
                        } else {
                            msgs.forEach(function (m) { appendMessage(m.role, m.content, false); });
                            oldestMessageCreation = msgs[0].creation;
                            scrollToBottom();
                        }
                        if (hasMoreMessages) $('#aiko-load-more').removeClass('hidden');
                    } else {
                        appendWelcomeMessage();
                    }
                },
                error: function () {
                    $('#aiko-msg-loading').remove();
                    appendWelcomeMessage();
                }
            });
        }

        // ── LOAD MORE ─────────────────────────────────────────────────────────────
        function bindLoadMoreBtn() {
            $('#aiko-chat-messages').off('click', '#aiko-load-more-btn').on('click', '#aiko-load-more-btn', function () {
                loadOlderMessages();
            });
        }
        bindLoadMoreBtn();

        $('#aiko-chat-messages').on('scroll', function () {
            if ($(this).scrollTop() < 60 && hasMoreMessages && !isLoadingHistory) loadOlderMessages();
        });

        function loadOlderMessages() {
            if (!currentSessionName || !hasMoreMessages || isLoadingHistory) return;
            isLoadingHistory = true;
            const btn = $('#aiko-load-more-btn');
            btn.text('Loading...').prop('disabled', true);
            frappe.call({
                method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
                args: { session_name: currentSessionName, limit: 20, before_creation: oldestMessageCreation },
                callback: function (r) {
                    isLoadingHistory = false;
                    btn.text('Load older messages').prop('disabled', false);
                    if (r.message && r.message.success) {
                        const msgs = r.message.messages;
                        hasMoreMessages = r.message.has_more;
                        if (msgs.length > 0) {
                            const container = $('#aiko-chat-messages')[0];
                            const prevScrollHeight = container.scrollHeight;
                            const fragment = msgs.map(m => buildMessageHtml(m.role, m.content)).join('');
                            $('#aiko-load-more').after(fragment);
                            container.scrollTop = container.scrollHeight - prevScrollHeight;
                            oldestMessageCreation = msgs[0].creation;
                        }
                        if (!hasMoreMessages) $('#aiko-load-more').addClass('hidden');
                    }
                },
                error: function () {
                    isLoadingHistory = false;
                    btn.text('Load older messages').prop('disabled', false);
                }
            });
        }

        // ── MESSAGING ─────────────────────────────────────────────────────────────
        function buildMessageHtml(role, text) {
            let content = text;
            if (frappe.markdown) content = frappe.markdown(text);
            return `<div class="aiko-message ${role}"><div class="aiko-bubble">${content}</div></div>`;
        }

        function appendMessage(role, text, doScroll = true) {
            $('#aiko-chat-messages').append(buildMessageHtml(role, text));
            if (doScroll) scrollToBottom();
        }

        function appendWelcomeMessage() {
            // Guard: only show if no messages exist yet
            if ($('#aiko-chat-messages .aiko-message').length === 0) {
                appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
            }
        }

        function scrollToBottom() {
            const el = $('#aiko-chat-messages')[0];
            el.scrollTop = el.scrollHeight;
        }

        function showThinking() {
            isThinking = true;
            $('#aiko-chat-messages').append(`
                <div class="aiko-message assistant" id="aiko-thinking">
                    <div class="aiko-bubble thinking-bubble">
                        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                    </div>
                </div>
            `);
            scrollToBottom();
        }

        function removeThinking() {
            isThinking = false;
            $('#aiko-thinking').remove();
        }

        function sendMessage() {
            if (isThinking) return;
            const input = $('#aiko-chat-input');
            const text = input.val().trim();
            if (!text) return;
            input.val('');
            appendMessage('user', text);
            showThinking();
            frappe.call({
                method: 'frappe_assistant_core.aiko.api.chat',
                args: { message: text, thread_id: thread_id },
                callback: function (r) {
                    removeThinking();
                    if (r.message && r.message.success) {
                        appendMessage('assistant', r.message.data);
                        // Track session so history panel stays in sync
                        if (r.message.session_name && !currentSessionName) {
                            currentSessionName = r.message.session_name;
                        }
                    } else {
                        appendMessage('error', r.message ? r.message.error : 'An error occurred.');
                    }
                },
                error: function () {
                    removeThinking();
                    appendMessage('error', 'Network error or server unavailable.');
                }
            });
        }

        $('#aiko-chat-send').on('click', sendMessage);
        $('#aiko-chat-input').on('keypress', function (e) {
            if (e.which == 13) sendMessage();
        });

        // ── HELPERS ───────────────────────────────────────────────────────────────
        function escapeHtml(str) {
            return String(str)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function formatRelativeTime(datetimeStr) {
            if (!datetimeStr) return '';
            const date = new Date(datetimeStr.replace(' ', 'T'));
            const now = new Date();
            const diffMins = Math.floor((now - date) / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);
            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return diffMins + 'm ago';
            if (diffHours < 24) return diffHours + 'h ago';
            if (diffDays < 7) return diffDays + 'd ago';
            return date.toLocaleDateString();
        }
    }

    // ── FRAPPE SPA ROUTE GUARD ────────────────────────────────────────────────────
    // _aikoListenersAttached ensures these handlers fire only once per browser session.
    // injectAikoWidget() itself is safe to call repeatedly — it re-attaches the
    // existing node if detached, and never re-runs initAikoLogic().
    injectAikoWidget();

    if (!window._aikoListenersAttached) {
        window._aikoListenersAttached = true;

        $(document).on('page-change', function () {
            if (frappe.session.user !== 'Guest') {
                injectAikoWidget();
            }
        });

        if (frappe.router) {
            frappe.router.on('change', function () {
                if (frappe.session.user !== 'Guest') {
                    injectAikoWidget();
                }
            });
        }
    }
});