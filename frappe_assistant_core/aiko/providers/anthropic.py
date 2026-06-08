class AnthropicProvider:
    def __init__(self, settings):
        self.settings = settings
        # Space kept for initialization

    async def process_query(self, query: str, session, system_prompt: str, thread_id: str) -> dict:
        return {"messages": [{"type": "assistant", "content": "Anthropic implementation space reserved."}], "activities": [], "documents": [], "suggestions": []}
