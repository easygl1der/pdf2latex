import os
import requests
import json
import time
import base64
from .config import MODELS

def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3,
             show_thinking: bool = False, image_path: str = None, max_retries: int = 3) -> str:
    """
    Robust LLM caller using 'requests' with a simple retry mechanism, 
    supporting vision and execution timing.
    """
    cfg = MODELS[model_name]
    url = f"{cfg['base_url']}/chat/completions"
    api_key = cfg["api_key"]()
    model = cfg["model"]

    print(f"\n[LLM] Calling model: {model}")
    start_time = time.time()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = [{"role": "system", "content": system}]
    
    if image_path:
        base64_image = _encode_image(image_path)
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ],
        })
    else:
        messages.append({"role": "user", "content": user})

    payload = {
        "model": model,
        "messages": messages,
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
            
            if show_thinking:
                print(content, flush=True)
            else:
                print(content[:100] + "..." if len(content) > 100 else content, flush=True)

            end_time = time.time()
            print(f"[LLM] Thinking Time: {end_time - start_time:.2f}s")
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
