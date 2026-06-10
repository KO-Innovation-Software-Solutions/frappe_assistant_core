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
                    <button id="aiko-chat-close">&times;</button>
                </div>
                <div class="aiko-chat-messages" id="aiko-chat-messages">
                    <div class="aiko-message assistant">
                        <div class="aiko-bubble">Hello! I am AIKO, your AI assistant. How can I help you today?</div>
                    </div>
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

    let thread_id = frappe.utils.get_random(10);
    let isThinking = false;

    $('#aiko-chat-button').on('click', function() {
        $('#aiko-chat-window').toggle();
        if ($('#aiko-chat-window').is(':visible')) {
            $('#aiko-chat-input').focus();
        }
    });

    $('#aiko-chat-close').on('click', function() {
        $('#aiko-chat-window').hide();
    });

    function appendMessage(role, text) {
        let content = text;
        if (frappe.markdown) {
            content = frappe.markdown(text);
        }
        const messageHtml = `
            <div class="aiko-message ${role}">
                <div class="aiko-bubble">${content}</div>
            </div>
        `;
        $('#aiko-chat-messages').append(messageHtml);
        $('#aiko-chat-messages').scrollTop($('#aiko-chat-messages')[0].scrollHeight);
    }

    function showThinking() {
        isThinking = true;
        const thinkingHtml = `
            <div class="aiko-message assistant" id="aiko-thinking">
                <div class="aiko-bubble thinking-bubble">
                    <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                </div>
            </div>
        `;
        $('#aiko-chat-messages').append(thinkingHtml);
        $('#aiko-chat-messages').scrollTop($('#aiko-chat-messages')[0].scrollHeight);
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
            args: {
                message: text,
                thread_id: thread_id
            },
            callback: function(r) {
                removeThinking();
                if (r.message && r.message.success) {
                    appendMessage('assistant', r.message.data);
                } else {
                    appendMessage('error', r.message ? r.message.error : 'An error occurred.');
                }
            },
            error: function(err) {
                removeThinking();
                appendMessage('error', 'Network error or server unavailable.');
            }
        });
    }

    $('#aiko-chat-send').on('click', sendMessage);
    $('#aiko-chat-input').on('keypress', function(e) {
        if (e.which == 13) {
            sendMessage();
        }
    });
});
