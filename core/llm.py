import subprocess
import json
import requests
import os
import time
from abc import ABC, abstractmethod
from typing import Optional

class LLMProvider(ABC):
    @abstractmethod
    def call(self, system: str, user: str, temperature: float = 0.3) -> str:
        pass

class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "deepseek-v4-pro:cloud"):
        self.model = model
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.api_key = os.getenv("OLLAMA_API_KEY", "")

    def call(self, system: str, user: str, temperature: float = 0.3) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "stream": False
        }
        
        for attempt in range(3):
            try:
                if attempt > 0:
                    time.sleep(2 ** attempt)
                resp = requests.post(url, headers=headers, json=payload, timeout=300)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"  [Ollama Attempt {attempt+1} Failed] {e}")
                if attempt == 2: raise
        return ""

class CodexProvider(LLMProvider):
    def __init__(self, model: str = "gpt-5.5"):
        self.model = model

    def call(self, system: str, user: str, temperature: float = 0.3) -> str:
        # Use codex exec to run the prompt
        # We wrap the system and user prompt into a single command
        prompt = f"System: {system}\n\nUser: {user}"
        cmd = ["codex", "exec", "-m", self.model, prompt]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ Codex CLI Error: {e.stderr}")
            raise RuntimeError(f"Codex execution failed: {e.stderr}")

def get_provider(name: str, model: Optional[str] = None) -> LLMProvider:
    if name == "ollama":
        return OllamaProvider(model=model or "deepseek-v4-pro:cloud")
    elif name == "codex":
        return CodexProvider(model=model or "gpt-5.5")
    else:
        raise ValueError(f"Unknown provider: {name}")
