"""Pick the LLM client from the LLM_PROVIDER setting."""
from app import config
from app.llm.base import LLMClient, LLMError
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient


def get_llm() -> LLMClient:
    if config.LLM_PROVIDER == "gemini":
        if not config.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY is missing. Copy .env.example to .env and add your key.")
        return OpenAICompatibleClient(config.GEMINI_BASE_URL, config.GEMINI_MODEL,
                                      api_key=config.GEMINI_API_KEY)
    if config.LLM_PROVIDER == "ollama":
        return OpenAICompatibleClient(config.OLLAMA_BASE_URL, config.OLLAMA_MODEL, timeout=120)
    if config.LLM_PROVIDER == "fake":
        return FakeLLM()
    raise LLMError(f"Unknown LLM_PROVIDER '{config.LLM_PROVIDER}' (use gemini, ollama or fake)")
