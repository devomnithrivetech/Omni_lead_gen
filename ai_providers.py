"""
Unified AI provider fallback chain.

Tries providers in order until one succeeds:
  Groq → Cerebras → SambaNova → Together → Mistral → Claude Haiku

All free-tier providers. No new SDK installs needed — OpenAI-compatible
ones use plain requests. Only Groq and Claude use their own SDKs.

Usage:
    from ai_providers import generate

    text = generate("Your prompt here", max_tokens=200)
    # Returns "" if all providers fail.
"""
import requests
from config import (
    GROQ_API_KEY, GROQ_MODEL,
    CEREBRAS_API_KEY, SAMBANOVA_API_KEY, TOGETHER_API_KEY,
    ANTHROPIC_API_KEY,
)

# Provider configs for OpenAI-compatible REST calls
_OAI_PROVIDERS = [
    {
        "name": "Cerebras",
        "key": lambda: CEREBRAS_API_KEY,
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "llama-3.3-70b",
    },
    {
        "name": "SambaNova",
        "key": lambda: SAMBANOVA_API_KEY,
        "url": "https://api.sambanova.ai/v1/chat/completions",
        "model": "Meta-Llama-3.1-70B-Instruct",
    },
    {
        "name": "Together",
        "key": lambda: TOGETHER_API_KEY,
        "url": "https://api.together.xyz/v1/chat/completions",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
]


def _call_oai(provider: dict, messages: list, max_tokens: int) -> str:
    key = provider["key"]()
    if not key:
        return ""
    resp = requests.post(
        provider["url"],
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json={"model": provider["model"], "messages": messages, "max_tokens": max_tokens},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError("HTTP " + str(resp.status_code) + ": " + resp.text[:120])
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate(prompt: str, max_tokens: int = 200, system: str = "") -> str:
    """
    Call providers in order, return first successful response text.
    Returns "" if all providers fail or no keys are configured.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # 1. Groq
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content.strip()
            if text:
                return text
        except Exception as e:
            print(" [Groq err: " + str(e)[:50] + "]", end="")

    # 2-5. OpenAI-compatible providers
    for p in _OAI_PROVIDERS:
        if not p["key"]():
            continue
        try:
            text = _call_oai(p, messages, max_tokens)
            if text:
                print(" [via " + p["name"] + "]", end="")
                return text
        except Exception as e:
            print(" [" + p["name"] + " err: " + str(e)[:50] + "]", end="")

    # 6. Claude Haiku (last resort — costs money but tiny)
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            claude_msgs = [{"role": "user", "content": prompt}]
            kwargs = {"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                      "messages": claude_msgs}
            if system:
                kwargs["system"] = system
            msg = client.messages.create(**kwargs)
            text = msg.content[0].text.strip()
            if text:
                print(" [via Claude]", end="")
                return text
        except Exception as e:
            print(" [Claude err: " + str(e)[:50] + "]", end="")

    return ""
