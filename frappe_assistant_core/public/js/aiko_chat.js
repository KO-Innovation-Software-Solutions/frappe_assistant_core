$(document).ready(function() {
    if (frappe.session.user === "Guest") return;

    const chatHtml = `
        <div id="aiko-chat-widget">
            <div id="aiko-chat-button" title="Chat with AIKO">
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
                        <button id="aiko-chat-fullscreen" title="Toggle Fullscreen">
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

                <div class="aiko-chat-messages" id="aiko-chat-messages">
                    <!-- messages rendered here dynamically -->
                </div>

                <!-- Scroll to bottom / New message pill -->
                <div id="aiko-scroll-btn" class="aiko-scroll-btn hidden">
                    <span id="aiko-scroll-label">↓</span>
                </div>

                <div class="aiko-chat-input-area">
                    <input type="file" id="aiko-file-input" accept="image/*,.pdf,.png,.jpg,.jpeg,.webp" style="display:none;position:absolute;top:-9999px;" />
                    <button id="aiko-attach-btn" title="Attach file or image">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                    </button>
                    <input type="text" id="aiko-chat-input" placeholder="Ask something..." autocomplete="off" />
                    <button id="aiko-chat-send">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                    </button>
                </div>

                <div id="aiko-file-preview-bar" style="display:none;">
                    <div id="aiko-file-preview-content"></div>
                    <button id="aiko-file-remove" title="Remove">&times;</button>
                </div>

                <div id="aiko-doctype-bar" style="display:none;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    <input type="text" id="aiko-doctype-input" placeholder="DocType to update (e.g. Sales Invoice, SI-0001)" autocomplete="off" />
                </div>

            </div>
        </div>
    `;

    $('body').append(chatHtml);

    // Force the correct layout via JS after render — overrides any Frappe CSS conflicts
    $('#aiko-chat-window').css({
        'display': 'none',
        'flex-direction': 'column',
        'overflow': 'hidden'
    });
    // Messages must NOT grow beyond available space — cap it so the input always shows
    $('#aiko-chat-messages').css({
        'flex': '1 1 auto',
        'overflow-y': 'auto',
        'min-height': '0'         // critical: without this, flex children don't shrink below content size
    });
    // Input area: flex row, always visible, never shrinks away
    $('.aiko-chat-input-area').css({
        'flex': '0 0 auto',
        'display': 'flex',
        'flex-direction': 'row',
        'align-items': 'center',
        'gap': '8px',
        'padding': '10px 12px',
        'background': '#fff',
        'border-top': '1px solid #f3f4f6'
    });
    // Attach button — force it visible with explicit dimensions
    $('#aiko-attach-btn').css({
        'display':         'inline-flex',
        'align-items':     'center',
        'justify-content': 'center',
        'width':           '36px',
        'height':          '36px',
        'min-width':       '36px',
        'padding':         '0',
        'margin':          '0',
        'border':          'none',
        'border-radius':   '50%',
        'background':      'none',
        'cursor':          'pointer',
        'color':           '#6366f1',
        'flex-shrink':     '0'
    });
    // Text input fills remaining space
    $('#aiko-chat-input').css({
        'flex': '1',
        'min-width': '0'
    });
    // Preview/doctype bars sit BELOW input, start hidden
    $('#aiko-file-preview-bar').css({
        'flex':        '0 0 auto',
        'display':     'none',
        'flex-direction': 'row',
        'align-items': 'center',
        'gap':         '8px',
        'padding':     '6px 12px',
        'background':  '#f5f3ff',
        'border-top':  '1px solid #e0d9ff',
        'font-size':   '12px',
        'color':       '#4b5563'
    });
    $('#aiko-file-preview-content').css({
        'display':       'flex',
        'align-items':   'center',
        'gap':           '8px',
        'flex':          '1',
        'overflow':      'hidden',
        'white-space':   'nowrap',
        'text-overflow': 'ellipsis'
    });
    $('#aiko-file-remove').css({
        'background':  'none',
        'border':      'none',
        'cursor':      'pointer',
        'font-size':   '20px',
        'color':       '#9ca3af',
        'line-height': '1',
        'padding':     '0 4px',
        'flex-shrink': '0'
    });
    $('#aiko-doctype-bar').css({
        'flex':        '0 0 auto',
        'display':     'none',
        'flex-direction': 'row',
        'align-items': 'center',
        'gap':         '8px',
        'padding':     '4px 12px',
        'background':  '#faf5ff',
        'border-top':  '1px solid #e9d5ff',
        'color':       '#7c3aed',
        'font-size':   '12px'
    });
    $('#aiko-doctype-input').css({
        'flex':       '1',
        'border':     'none',
        'background': 'transparent',
        'outline':    'none',
        'font-size':  '12px',
        'color':      '#374151'
    });

    let thread_id = frappe.utils.get_random(10);
    let isThinking = false;
    let attachedFile = null;
    let attachedFileDataUrl = null;
    let currentSessionName = null;
    let oldestMessageCreation = null;
    let hasMoreMessages = false;
    let isLoadingOlder = false;
    let hasAutoLoaded = false;
    let isScrolledUp = false;

    // ── SCROLL TRACKING ───────────────────────────────────────────────────────
    $('#aiko-chat-messages').on('scroll', function() {
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

    $('#aiko-scroll-btn').on('click', function() { scrollToBottom(); });

    // ── HELPERS ───────────────────────────────────────────────────────────────
    function formatTimestamp(dateStr) {
        const date = dateStr ? new Date(dateStr.replace(' ', 'T')) : new Date();
        return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }

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

    // ── AUTO-LOAD LAST SESSION ────────────────────────────────────────────────
    function autoLoadLastSession() {
        $('#aiko-chat-messages').html('<div class="aiko-sessions-loading" id="aiko-msg-loading">Loading...</div>');
        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_chat_sessions',
            callback: function(r) {
                if (r.message && r.message.success && r.message.sessions && r.message.sessions.length > 0) {
                    const latest = r.message.sessions[0];
                    loadSession(latest.name, latest.thread_id);
                } else {
                    $('#aiko-chat-messages').html('');
                    appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
                }
            },
            error: function() {
                $('#aiko-chat-messages').html('');
                appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
            }
        });
    }

    // ── OPEN / CLOSE ──────────────────────────────────────────────────────────
    $('#aiko-chat-button').on('click', function() {
        $('#aiko-chat-window').toggle();
        if ($('#aiko-chat-window').is(':visible')) {
            if (!hasAutoLoaded) {
                hasAutoLoaded = true;
                autoLoadLastSession();
            }
            $('#aiko-chat-input').focus();
        }
    });

    $('#aiko-chat-close').on('click', function() { $('#aiko-chat-window').hide(); });

    // ── FULLSCREEN ────────────────────────────────────────────────────────────
    $('#aiko-chat-fullscreen').on('click', function() {
        $('#aiko-chat-window').toggleClass('fullscreen');
        if ($('#aiko-chat-window').hasClass('fullscreen')) {
            $(this).html('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path></svg>');
        } else {
            $(this).html('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>');
        }
    });

    // ── NEW CHAT ──────────────────────────────────────────────────────────────
    $('#aiko-new-chat-btn').on('click', function() { startNewChat(); });

    function startNewChat() {
        thread_id = frappe.utils.get_random(10);
        currentSessionName = null;
        oldestMessageCreation = null;
        hasMoreMessages = false;
        isScrolledUp = false;
        $('#aiko-chat-messages').html('');
        $('#aiko-scroll-btn').addClass('hidden');
        appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
        hideSessionsPanel();
        $('#aiko-chat-input').focus();
    }

    // ── HISTORY PANEL ─────────────────────────────────────────────────────────
    $('#aiko-history-btn').on('click', function() {
        const panel = $('#aiko-sessions-panel');
        if (panel.hasClass('hidden')) showSessionsPanel();
        else hideSessionsPanel();
    });
    $('#aiko-sessions-close').on('click', function() { hideSessionsPanel(); });

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
            callback: function(r) {
                if (r.message && r.message.success) {
                    renderSessionsList(r.message.sessions);
                } else {
                    $('#aiko-sessions-list').html('<div class="aiko-sessions-loading">Could not load chats.</div>');
                }
            },
            error: function() {
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
        sessions.forEach(function(s) {
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
        $('#aiko-sessions-list').off('click', '.aiko-session-item').on('click', '.aiko-session-item', function() {
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
        isScrolledUp = false;
        $('#aiko-scroll-btn').addClass('hidden');
        $('#aiko-chat-messages').html('<div class="aiko-sessions-loading" id="aiko-msg-loading">Loading messages...</div>');

        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
            args: { session_name: sessionName, limit: 20 },
            callback: function(r) {
                $('#aiko-msg-loading').remove();
                $('#aiko-chat-messages').html('');
                if (r.message && r.message.success) {
                    const msgs = r.message.messages;
                    hasMoreMessages = r.message.has_more || false;
                    if (hasMoreMessages) {
                        $('#aiko-chat-messages').prepend(`
                            <div id="aiko-load-more" class="aiko-load-more">
                                <button id="aiko-load-more-btn">Load older messages</button>
                            </div>
                        `);
                        bindLoadMoreBtn();
                    }
                    if (msgs.length === 0) {
                        appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
                    } else {
                        msgs.forEach(function(m) { appendMessage(m.role, m.content, false, m.creation); });
                        oldestMessageCreation = msgs[0].creation;
                        scrollToBottom();
                    }
                } else {
                    appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
                }
            },
            error: function() {
                $('#aiko-msg-loading').remove();
                appendMessage('assistant', 'Hello! I am AIKO, your AI assistant. How can I help you today?');
            }
        });
    }

    // ── LOAD OLDER MESSAGES ───────────────────────────────────────────────────
    function bindLoadMoreBtn() {
        $('#aiko-chat-messages').off('click', '#aiko-load-more-btn').on('click', '#aiko-load-more-btn', function() {
            loadOlderMessages();
        });
    }

    function loadOlderMessages() {
        if (!currentSessionName || !hasMoreMessages || isLoadingOlder) return;
        isLoadingOlder = true;
        const btn = $('#aiko-load-more-btn');
        btn.text('Loading...').prop('disabled', true);
        frappe.call({
            method: 'frappe_assistant_core.api.assistant_api.get_session_messages',
            args: { session_name: currentSessionName, limit: 20, before_creation: oldestMessageCreation },
            callback: function(r) {
                isLoadingOlder = false;
                btn.text('Load older messages').prop('disabled', false);
                if (r.message && r.message.success) {
                    const msgs = r.message.messages;
                    hasMoreMessages = r.message.has_more || false;
                    if (msgs.length > 0) {
                        const container = $('#aiko-chat-messages')[0];
                        const prevScrollHeight = container.scrollHeight;
                        msgs.forEach(function(m) {
                            $('#aiko-load-more').after(buildMessageHtml(m.role, m.content, m.creation));
                        });
                        container.scrollTop = container.scrollHeight - prevScrollHeight;
                        oldestMessageCreation = msgs[0].creation;
                    }
                    if (!hasMoreMessages) { $('#aiko-load-more').remove(); }
                }
            },
            error: function() {
                isLoadingOlder = false;
                btn.text('Load older messages').prop('disabled', false);
            }
        });
    }

    // ── MESSAGING ─────────────────────────────────────────────────────────────
    function buildMessageHtml(role, text, creation) {
        let content = text;
        if (frappe.markdown) content = frappe.markdown(text);
        const time = formatTimestamp(creation);
        return `
            <div class="aiko-message ${role}">
                <div class="aiko-bubble">
                    ${content}
                    <div class="aiko-timestamp">${time}</div>
                </div>
            </div>`;
    }

    function appendMessage(role, text, doScroll, creation) {
        if (doScroll === undefined) doScroll = true;
        $('#aiko-chat-messages').append(buildMessageHtml(role, text, creation));
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

    function showThinking() {
        isThinking = true;
        $('#aiko-chat-send').prop('disabled', true).css({ 'background': '#c4b5fd', 'cursor': 'not-allowed' });
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
        $('#aiko-chat-send').prop('disabled', false).css({ 'background': '#6366f1', 'cursor': 'pointer' });
    }

    // ── FILE ATTACHMENT ───────────────────────────────────────────────────────
    $('#aiko-attach-btn').on('click', function() {
        if (isThinking) return;
        $('#aiko-file-input').val('').trigger('click');
    });

    $('#aiko-file-input').on('change', function() {
        const file = this.files[0];
        if (!file) return;
        const isImage = file.type.startsWith('image/');
        const isPdf   = file.type === 'application/pdf';
        if (!isImage && !isPdf) {
            frappe.msgprint('Only images (JPG, PNG, WEBP) and PDFs are supported.');
            return;
        }
        const reader = new FileReader();
        reader.onload = function(e) {
            const dataUrl = e.target.result;
            const base64  = dataUrl.split(',')[1];
            attachedFile = { name: file.name, type: file.type, base64: base64, isImage: isImage };
            attachedFileDataUrl = dataUrl;

            let previewHtml = '';
            if (isImage) {
                previewHtml = `<img src="${dataUrl}" style="width:32px;height:32px;object-fit:cover;border-radius:4px;border:1px solid #ddd;flex-shrink:0;" /> <span style="overflow:hidden;text-overflow:ellipsis;">${escapeHtml(file.name)}</span>`;
            } else {
                previewHtml = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>&nbsp;<span>${escapeHtml(file.name)}</span>`;
            }
            $('#aiko-file-preview-content').html(previewHtml);
            $('#aiko-file-preview-bar').css('display', 'flex');
            $('#aiko-doctype-bar').css('display', 'flex');
            $('#aiko-chat-input').attr('placeholder', 'Describe what to do with this file...');
        };
        reader.readAsDataURL(file);
    });

    $('#aiko-file-remove').on('click', function() { clearAttachment(); });

    function clearAttachment() {
        attachedFile = null;
        attachedFileDataUrl = null;
        $('#aiko-file-preview-bar').hide();
        $('#aiko-doctype-bar').hide();
        $('#aiko-doctype-input').val('');
        $('#aiko-file-input').val('');
        $('#aiko-chat-input').attr('placeholder', 'Ask something...');
    }

    // ── SEND ──────────────────────────────────────────────────────────────────
    function sendMessage() {
        if (isThinking) return;
        const input = $('#aiko-chat-input');
        const text = input.val().trim();
        if (!text && !attachedFile) return;

        const userText = text || 'Analyze this file.';
        const fileSnapshot = attachedFile ? Object.assign({}, attachedFile) : null;
        const fileDataUrl  = attachedFileDataUrl;
        input.val('');

        // Build user bubble
        if (fileSnapshot) {
            let filePreview = '';
            if (fileSnapshot.isImage) {
                filePreview = `<img src="${fileDataUrl}" style="max-width:180px;max-height:140px;border-radius:6px;border:1px solid rgba(0,0,0,0.1);display:block;margin-bottom:6px;" />`;
            } else {
                filePreview = `<div style="display:flex;align-items:center;gap:6px;font-size:12px;background:rgba(0,0,0,0.06);border-radius:4px;padding:4px 8px;margin-bottom:6px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>${escapeHtml(fileSnapshot.name)}</div>`;
            }
            const time = formatTimestamp();
            $('#aiko-chat-messages').append(`
                <div class="aiko-message user">
                    <div class="aiko-bubble">
                        ${filePreview}
                        ${escapeHtml(userText)}
                        <div class="aiko-timestamp">${time}</div>
                    </div>
                </div>`);
            if (!isScrolledUp) scrollToBottom();
        } else {
            appendMessage('user', userText);
        }

        showThinking();

        if (fileSnapshot) {
            const doctypeTarget = $('#aiko-doctype-input').val().trim();
            clearAttachment();
            frappe.call({
                method: 'frappe_assistant_core.aiko.api.chat_with_file',
                args: {
                    message: userText,
                    thread_id: thread_id,
                    file_name: fileSnapshot.name,
                    file_type: fileSnapshot.type,
                    file_data: fileSnapshot.base64,
                    doctype_target: doctypeTarget || ''
                },
                timeout: 120,
                callback: function(r) {
                    removeThinking();
                    if (r.message && r.message.success) {
                        appendMessage('assistant', r.message.data);
                        if (r.message.session_name && !currentSessionName) currentSessionName = r.message.session_name;
                        if (r.message.doctype_updated) appendMessage('assistant', '✅ Updated **' + r.message.doctype_updated + '** successfully.');
                    } else {
                        appendMessage('error', r.message ? r.message.error : 'An error occurred.');
                    }
                },
                error: function() {
                    removeThinking();
                    appendMessage('error', 'Network error or server unavailable.');
                }
            });
        } else {
            frappe.call({
                method: 'frappe_assistant_core.aiko.api.chat',
                args: { message: userText, thread_id: thread_id },
                callback: function(r) {
                    removeThinking();
                    if (r.message && r.message.success) {
                        appendMessage('assistant', r.message.data);
                        if (r.message.session_name && !currentSessionName) currentSessionName = r.message.session_name;
                    } else {
                        appendMessage('error', r.message ? r.message.error : 'An error occurred.');
                    }
                },
                error: function() {
                    removeThinking();
                    appendMessage('error', 'Network error or server unavailable.');
                }
            });
        }
    }

    $('#aiko-chat-send').on('click', sendMessage);
    $('#aiko-chat-input').on('keypress', function(e) {
        if (e.which == 13) sendMessage();
    });
});