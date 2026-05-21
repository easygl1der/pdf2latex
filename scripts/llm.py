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
    
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user}
    ]
    
    full_response = []
    
    while True:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        current_turn_buf = []
        finish_reason = None

        for chunk in stream:
            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason
            
            piece = delta.content or ""
            if piece:
                current_turn_buf.append(piece)
                print(piece, end="", flush=True)

        full_response.extend(current_turn_buf)
        
        # If the model stopped because of length, we need to continue
        if finish_reason == "length":
            print("\n[Output Truncated] Requesting continuation...", flush=True)
            # Add the partial response as an assistant message
            messages.append({"role": "assistant", "content": "".join(current_turn_buf)})
            # Add a prompt to continue
            messages.append({"role": "user", "content": "Your previous response was truncated. Please continue exactly from where you left off. Do not repeat the preamble or any previous parts. Just continue the LaTeX code."})
        else:
            break

    print("\n", flush=True)
    return "".join(full_response)
