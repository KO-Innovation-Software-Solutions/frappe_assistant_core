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
            msgDiv.innerHTML = text;
        } else {
            msgDiv.textContent = text;
        }

        this.messagesContainer.appendChild(msgDiv);
        this.scrollToBottom();
    }

    formatMarkdown(text) {
        if (typeof marked !== 'undefined') {
            return marked.parse ? marked.parse(text) : marked(text);
        } else if (typeof showdown !== 'undefined') {
            let converter = new showdown.Converter();
            return converter.makeHtml(text);
        } else {
            return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        }
    }

    renderStructuredResponse(data) {
        const responseContainer = document.createElement('div');
        responseContainer.className = 'aiko-message ai structured-response';
        
        // 1. Text Content
        if (data.messages && data.messages.length > 0) {
            let combinedContent = data.messages.map(m => m.content).join('\n\n');
            if (combinedContent.trim()) {
                const textDiv = document.createElement('div');
                textDiv.innerHTML = this.formatMarkdown(combinedContent);
                responseContainer.appendChild(textDiv);
            }
        }
        
        // 2. Document Cards
        if (data.documents && data.documents.length > 0) {
            data.documents.forEach(doc => {
                const card = document.createElement('div');
                card.className = 'aiko-document-card';
                card.innerHTML = `
                    <div class="aiko-document-card-title">📄 ${doc.doctype}</div>
                    <div style="font-size: 13px; color: #475569;">Name: <strong>${doc.name}</strong></div>
                    <button class="aiko-document-card-btn" onclick="frappe.set_route('Form', '${doc.doctype}', '${doc.name}')">Open Document</button>
                `;
                responseContainer.appendChild(card);
            });
        }
        
        // 3. Suggestions
        if (data.suggestions && data.suggestions.length > 0) {
            const suggestionsDiv = document.createElement('div');
            suggestionsDiv.className = 'aiko-suggestions';
            data.suggestions.forEach(s => {
                const chip = document.createElement('button');
                chip.className = 'aiko-suggestion-chip';
                chip.textContent = s;
                chip.onclick = () => {
                    this.input.value = s;
                    this.sendMessage();
                };
                suggestionsDiv.appendChild(chip);
            });
            responseContainer.appendChild(suggestionsDiv);
        }
        
        // 4. Activity Log
        if (data.activities && data.activities.length > 0) {
            const activityDiv = document.createElement('div');
            activityDiv.className = 'aiko-activity-section';
            
            const header = document.createElement('div');
            header.className = 'aiko-activity-header';
            header.innerHTML = `<span>▶ Agent Activity</span><span>${data.activities.length} steps</span>`;
            
            const list = document.createElement('div');
            list.className = 'aiko-activity-list collapsed'; // Auto-collapse when completed
            
            data.activities.forEach(act => {
                const item = document.createElement('div');
                item.className = 'aiko-activity-item';
                let icon = '⏳';
                if (act.status === 'success') icon = '✓';
                else if (act.status === 'error') icon = '❌';
                else if (act.status === 'thought') icon = '💭';
                
                if (act.status === 'thought' && act.args && act.args.text) {
                    item.style.flexDirection = 'column';
                    item.style.alignItems = 'flex-start';
                    item.innerHTML = `
                        <div style="display: flex; gap: 6px; font-weight: 600;">
                            <span class="aiko-activity-icon">${icon}</span> <span>Reasoning</span>
                        </div>
                        <div style="padding-left: 20px; color: #64748b; font-style: italic; white-space: pre-wrap; font-size: 11px;">${act.args.text}</div>
                    `;
                } else {
                    item.innerHTML = `<span class="aiko-activity-icon">${icon}</span> <span>${act.tool}</span>`;
                }
                list.appendChild(item);
            });
            
            header.onclick = () => {
                list.classList.toggle('collapsed');
                header.querySelector('span').textContent = list.classList.contains('collapsed') ? '▶ Agent Activity' : '▼ Agent Activity';
            };
            
            activityDiv.appendChild(header);
            activityDiv.appendChild(list);
            
            responseContainer.appendChild(activityDiv);
        }
        
        if (responseContainer.childNodes.length > 0) {
            this.messagesContainer.appendChild(responseContainer);
            this.scrollToBottom();
        } else {
            this.addMessage("Task completed successfully.", "ai");
        }
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
                    const data = r.message.data;
                    if (typeof data === 'string') {
                        this.addMessage(this.formatMarkdown(data), 'ai', true);
                    } else if (typeof data === 'object') {
                        this.renderStructuredResponse(data);
                    }
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
