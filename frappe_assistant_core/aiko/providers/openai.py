from .base import BaseProvider

class OpenAIProvider(BaseProvider):
    def __init__(self, settings):
        super().__init__(settings)
        from langchain_openai import ChatOpenAI
        import frappe
        
        try:
            self.api_key = self.settings.get_password("openai_api_key")
        except Exception:
            self.api_key = getattr(self.settings, "openai_api_key", None)
        
        if not self.api_key:
            frappe.throw("OpenAI API key is missing. Please set it in Assistant Core Settings.")
        
        self.api_key = self.api_key.strip()
        
        frappe.logger().info(f"OpenAI key length: {len(self.api_key)}, prefix: {self.api_key[:8]}")
        
        # Pull model and base_url from settings instead of hardcoding
        self.model = getattr(self.settings, "openai_model", None)
        self.base_url = getattr(self.settings, "openai_url", None)
        
        self.llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.0,
            max_tokens=4096,
        )