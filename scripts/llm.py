import os
import requests
import json
from .config import MODELS

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3,
             show_thinking: bool = False) -> str:
    """
    Robust LLM caller using 'requests' to avoid compatibility issues with local proxies.
    """
    cfg = MODELS[model_name]
    url = f"{cfg['base_url']}/chat/completions"
    api_key = cfg["api_key"]()
    model = cfg["model"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": temperature,
        "stream": False
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Simple print for progress tracking
        print(content[:100] + "..." if len(content) > 100 else content, flush=True)
        return content
    except Exception as e:
        print(f"❌ LLM Call Failed: {e}")
        if 'response' in locals() and response.text:
            print(f"Response Detail: {response.text}")
        raise
