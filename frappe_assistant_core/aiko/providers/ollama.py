from .base import BaseProvider

class OllamaProvider(BaseProvider):
    def __init__(self, settings):
        super().__init__(settings)
        from langchain_ollama import ChatOllama
        
        self.ollama_url = getattr(self.settings, "ollama_chat_api_url", "http://localhost:11434").rstrip("/")
        self.model = getattr(self.settings, "ollama_chat_model", "llama3.1")
        
        # Configure Ollama with optimized parameters
        self.llm = ChatOllama(
            model=self.model,
            validate_model_on_init=True,
            temperature=0.0,
            num_ctx=32000,
            base_url=self.ollama_url,
        )
