from .base import BaseProvider

class AnthropicProvider(BaseProvider):
    def __init__(self, settings):
        super().__init__(settings)
        from langchain_anthropic import ChatAnthropic
        
        self.model = getattr(self.settings, "anthropic_model", "claude-3-5-sonnet-20240620")
        self.api_key = getattr(self.settings, "anthropic_api_key", None)

        if not self.api_key:
            import frappe
            self.api_key = frappe.conf.get("anthropic_api_key")

        self.llm = ChatAnthropic(
            model_name=self.model,
            api_key=self.api_key,
            temperature=0.0
        )
