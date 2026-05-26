import os
import requests
import json
import time
from .config import MODELS

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3,
             show_thinking: bool = False, max_retries: int = 3) -> str:
    """
    Robust LLM caller using 'requests' with a simple retry mechanism.
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

    last_error = None
    for attempt in range(max_retries):
        try:
            # Exponential backoff: 2s, 4s, 8s...
            if attempt > 0:
                wait_time = 2 ** attempt
                print(f"  [Retry {attempt}/{max_retries}] Waiting {wait_time}s...")
                time.sleep(wait_time)

            response = requests.post(url, headers=headers, json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Simple print for progress tracking
            print(content[:100] + "..." if len(content) > 100 else content, flush=True)
            return content
        except Exception as e:
            last_error = e
            print(f"  [Attempt {attempt+1} Failed] {e}")
            if 'response' in locals() and response.text:
                print(f"  Response Detail: {response.text}")
            
            # If it's a 4xx error (except 429), don't bother retrying
            if isinstance(e, requests.exceptions.HTTPError):
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    break

    print(f"❌ LLM Call Failed after {max_retries} attempts.")
    raise last_error
