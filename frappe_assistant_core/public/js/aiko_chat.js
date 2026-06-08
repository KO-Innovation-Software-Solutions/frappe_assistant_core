/* AIKO Chatbot JS */

class AikoChatWidget {
    constructor() {
        this.isOpen = false;
        this.threadId = localStorage.getItem('aiko_thread_id') || this.generateId();
        localStorage.setItem('aiko_thread_id', this.threadId);
        this.render();
        this.bindEvents();
    }

    generateId() {
        return 'aiko_' + Math.random().toString(36).substr(2, 9);
    }

    render() {
        // Only render if not already present
        if (document.getElementById('aiko-chat-widget')) return;

        const widgetHtml = `
            <div id="aiko-chat-widget">
                <div id="aiko-chat-window">
                    <div id="aiko-chat-header">
                        <span>🤖 AIKO Assistant</span>
                        <button id="aiko-close-btn">&times;</button>
                    </div>
                    <div id="aiko-chat-messages">
                        <div class="aiko-message ai">Hi there! I am AIKO. How can I help you with Kofleetz today?</div>
                    </div>
                    <div id="aiko-chat-input-container">
                        <input type="text" id="aiko-chat-input" placeholder="Ask AIKO..." autocomplete="off">
                        <button id="aiko-chat-send">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </div>
                <div id="aiko-chat-button" title="Chat with AIKO">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', widgetHtml);

        this.window = document.getElementById('aiko-chat-window');
        this.button = document.getElementById('aiko-chat-button');
        this.closeBtn = document.getElementById('aiko-close-btn');
        this.input = document.getElementById('aiko-chat-input');
        this.sendBtn = document.getElementById('aiko-chat-send');
        this.messagesContainer = document.getElementById('aiko-chat-messages');
    }

    bindEvents() {
        if (!this.button) return;

        this.button.addEventListener('click', () => this.toggle());
        this.closeBtn.addEventListener('click', () => this.toggle());

        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });
    }

    toggle() {
        this.isOpen = !this.isOpen;
        if (this.isOpen) {
            this.window.classList.add('open');
            this.input.focus();
        } else {
            this.window.classList.remove('open');
        }
    }

    addMessage(text, sender, isHtml = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `aiko-message ${sender}`;

        if (isHtml) {
            msgDiv.innerHTML = text; // Expecting markdown converted to HTML from backend
        } else {
            msgDiv.textContent = text;
        }

        this.messagesContainer.appendChild(msgDiv);
        this.scrollToBottom();
    }

    addTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'aiko-message ai aiko-typing';
        indicator.id = 'aiko-typing-indicator';
        indicator.innerHTML = `
            <div class="aiko-dot"></div>
            <div class="aiko-dot"></div>
            <div class="aiko-dot"></div>
        `;
        this.messagesContainer.appendChild(indicator);
        this.scrollToBottom();
    }

    removeTypingIndicator() {
        const indicator = document.getElementById('aiko-typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    sendMessage() {
        const text = this.input.value.trim();
        if (!text) return;

        this.input.value = '';
        this.input.disabled = true;
        this.sendBtn.disabled = true;

        this.addMessage(text, 'user');
        this.addTypingIndicator();

        frappe.call({
            method: 'frappe_assistant_core.aiko.api.chat',
            args: {
                message: text,
                thread_id: this.threadId
            },
            callback: (r) => {
                this.removeTypingIndicator();
                this.input.disabled = false;
                this.sendBtn.disabled = false;
                this.input.focus();

                if (r.message && r.message.success) {
                    // Use marked.js if available in Frappe, otherwise raw text
                    let formattedResponse = r.message.data;
                    if (typeof marked !== 'undefined') {
                        formattedResponse = marked(formattedResponse);
                    } else if (typeof showdown !== 'undefined') {
                        let converter = new showdown.Converter();
                        formattedResponse = converter.makeHtml(formattedResponse);
                    } else {
                        // Simple fallback for bold and line breaks
                        formattedResponse = formattedResponse.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
                    }
                    this.addMessage(formattedResponse, 'ai', true);
                } else {
                    const errorMsg = (r.message && r.message.error) ? r.message.error : 'Failed to connect to AIKO.';
                    this.addMessage('Error: ' + errorMsg, 'ai');
                }
            },
            error: (r) => {
                this.removeTypingIndicator();
                this.input.disabled = false;
                this.sendBtn.disabled = false;
                this.addMessage('Error connecting to server.', 'ai');
            }
        });
    }
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', () => {
    // Inject only if user is logged in
    if (frappe.session && frappe.session.user !== 'Guest') {
        window.aikoChat = new AikoChatWidget();
    }
});
