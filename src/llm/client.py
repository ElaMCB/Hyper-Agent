"""Optional LLM client for summarisation and drafting."""

import os
from pathlib import Path


def llm_complete(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
) -> str:
    """Call LLM API. Returns the assistant reply. Raises if API key missing or call fails."""
    provider = (os.getenv("LLM_PROVIDER") or provider).lower()
    model = os.getenv("LLM_MODEL") or model

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Add to .env or disable LLM in config.")
        return _openai_complete(api_key, model, system_prompt, user_prompt)
    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add to .env or disable LLM in config.")
        return _anthropic_complete(api_key, model, system_prompt, user_prompt)
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use openai or anthropic.")


def _openai_complete(api_key: str, model: str, system: str, user: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
    )
    return (resp.choices[0].message.content or "").strip()


def _anthropic_complete(api_key: str, model: str, system: str, user: str) -> str:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("anthropic package required for provider=anthropic. pip install anthropic")
    client = Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return (msg.content[0].text if msg.content else "").strip()


def load_prompt(name: str, **variables: str) -> str:
    """Load a prompt from config/prompts/ and fill placeholders {{key}}."""
    repo_root = _find_repo_root()
    path = Path(repo_root) / "config" / "prompts" / name
    text = path.read_text(encoding="utf-8")
    for k, v in variables.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _find_repo_root() -> Path:
    """Assume we're in src/ or repo root."""
    cwd = Path.cwd()
    if (cwd / "config" / "config.yaml").exists():
        return cwd
    if (cwd.parent / "config" / "config.yaml").exists():
        return cwd.parent
    return cwd
