"""
Talking to the AI: an open-source model served by Ollama, used through LangChain.

ask_llm(prompt)        sends the prompt, returns the AI's answer as text (None if the AI cannot be reached)
read_json(answer)      finds the {...} JSON object in the answer
to_points(value, max)  turns a value from the answer into whole points between 0 and max
to_years(value)        turns a value from the answer into a number of years between 0 and 50
"""
import json
import re

from langchain_ollama import ChatOllama

from config.settings import LLM_MODEL, OLLAMA_BASE_URL

AI_UNAVAILABLE = "AI is not available right now. Please check that Ollama is running."

# Ollama's default context window is small and it silently cuts long prompts.
# 8192 tokens fits the instructions + job description + a full CV.
CONTEXT_WINDOW = 8192

# Some models (like qwen3) "think" before they answer: much slower, and not needed here. False turns it off.
THINKING = False


def ask_llm(prompt, json_mode=False):
    """
    Returns the model's answer as text, or None if the model is not reachable.
    json_mode=True forces valid JSON output and makes the answer repeatable (temperature 0, fixed seed).
    """
    try:
        if json_mode:
            llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, num_ctx=CONTEXT_WINDOW,
                             temperature=0, seed=42, format="json", reasoning=THINKING)
        else:
            llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, num_ctx=CONTEXT_WINDOW, temperature=0.2,
                             reasoning=THINKING)
        return llm.invoke(prompt).content
    except Exception as error:  # Ollama not running, model not pulled, etc.
        print(f"[LLM] Not available: {error}")
        return None


def read_json(answer):
    """The {...} object in the AI's answer as a dict, or None. Text around it is ignored: 'Sure! {"a": 1}' -> {"a": 1}"""
    if not answer:
        return None
    try:
        match = re.search(r"\{.*\}", answer, re.DOTALL)   # from the first "{" to the last "}"
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        return None
    if isinstance(data, dict):
        return data
    return None


def to_points(value, maximum):
    """A whole number between 0 and maximum, or None if the value is not a number. '10.6' -> 11, 99 -> maximum."""
    try:
        return max(0, min(maximum, round(float(value))))
    except (TypeError, ValueError):
        return None


def to_years(value):
    """A number of years between 0 and 50, or None if the value is not a number. '2.5' -> 2.5"""
    try:
        return max(0.0, min(50.0, float(value)))
    except (TypeError, ValueError):
        return None
