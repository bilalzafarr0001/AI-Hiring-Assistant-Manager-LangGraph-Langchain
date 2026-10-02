"""Connects to the open-source LLM through Ollama (via LangChain)."""
from langchain_ollama import ChatOllama

from config.settings import LLM_MODEL, OLLAMA_BASE_URL

# Ollama's default context window is small and it silently cuts long prompts.
# 8192 tokens fits the instructions + job description + a full CV.
CONTEXT_WINDOW = 8192


def ask_llm(prompt, json_mode=False):
    """
    Returns the model's answer as text, or None if the model is not reachable.
    json_mode=True forces valid JSON output and makes the answer repeatable (temperature 0, fixed seed).
    """
    try:
        if json_mode:
            llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, num_ctx=CONTEXT_WINDOW,
                             temperature=0, seed=42, format="json")
        else:
            llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, num_ctx=CONTEXT_WINDOW, temperature=0.2)
        return llm.invoke(prompt).content
    except Exception as error:  # Ollama not running, model not pulled, etc.
        print(f"[LLM] Not available: {error}")
        return None
