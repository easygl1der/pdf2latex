"""
LLM Client Wrapper: get_client / call_llm

Ollama is compatible with the OpenAI API via OLLAMA_BASE_URL / OLLAMA_MODEL_NAME.
"""

import sys
from openai import OpenAI
from .config import MODELS

_client_cache = {}

def get_client(model_name: str) -> tuple:
    if model_name not in _client_cache:
        cfg = MODELS[model_name]
        _client_cache[model_name] = (
            OpenAI(api_key=cfg["api_key"](), base_url=cfg["base_url"]),
            cfg["model"],
            cfg.get("max_tokens", 8192),
        )
    return _client_cache[model_name]

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3,
             show_thinking: bool = False) -> str:
    client, model, max_tokens = get_client(model_name)

    # Note: Nemotron-3-Super natively expects a prompt structure.
    # We pass it as standard chat messages here.
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    raw_buf = []

    for chunk in stream:
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content or ""
        if not piece:
            continue
        raw_buf.append(piece)
        print(piece, end="", flush=True)

    print("\n", flush=True)
    return "".join(raw_buf)
