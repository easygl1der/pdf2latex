"""
LLM 客户端封装：get_client / call_llm
"""

from openai import OpenAI
from .config import MODELS

_client_cache = {}

def get_client(model_name: str) -> tuple:
    if model_name not in _client_cache:
        cfg = MODELS[model_name]
        _client_cache[model_name] = (
            OpenAI(api_key=cfg["api_key"](), base_url=cfg["base_url"]),
            cfg["model"],
        )
    return _client_cache[model_name]

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3) -> str:
    client, model = get_client(model_name)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=temperature,
        max_tokens=196608,
    )
    return resp.choices[0].message.content
