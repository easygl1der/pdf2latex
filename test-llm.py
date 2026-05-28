import os
import requests

base_url = "https://ollama.com/api"
model = "nemotron-3-super:cloud"
timeout = 120

api_key = os.getenv("OLLAMA_API_KEY")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

payload = {
    "model": model,
    "prompt": "你好，做个自我介绍",
    "stream": False,
}

resp = requests.post(
    f"{base_url}/generate",
    headers=headers,
    json=payload,
    timeout=timeout,
)

resp.raise_for_status()
print(resp.json())