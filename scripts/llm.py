"""
LLM Client Wrapper: get_client / call_llm

MiniMax M2.7 thinking content is embedded in the content stream,
wrapped in <think>...</think> tags.
Ollama is compatible with the OpenAI API via OLLAMA_BASE_URL / OLLAMA_MODEL_NAME.
"""

import sys
import re
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
             show_thinking: bool = True) -> str:
    client, model, max_tokens = get_client(model_name)

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

        if show_thinking:
            _stream_print(piece)

    if show_thinking:
        _stream_flush()

    full = "".join(raw_buf)
    # Strip <think>...</think> from the returned value
    answer = re.sub(r'<think>.*?</think>', '', full, flags=re.DOTALL).strip()
    return answer


# ── Streaming Display State ───────────────────────────────────
_display_buf = ""
_in_think = False

def _stream_print(piece: str):
    global _display_buf, _in_think
    _display_buf += piece

    while True:
        if not _in_think:
            tag_start = _display_buf.find("<think>")
            if tag_start == -1:
                # No think tag yet
                safe = _display_buf[:-6] if len(_display_buf) > 6 else ""
                if safe:
                    print(safe, end="", flush=True)
                    _display_buf = _display_buf[len(safe):]
                break
            else:
                # Print content before <think>
                before = _display_buf[:tag_start]
                if before:
                    print(before, end="", flush=True)
                _display_buf = _display_buf[tag_start + len("<think>"):]
                _in_think = True
                print("\n  \033[2m[thinking]\033[0m", flush=True)
        else:
            tag_end = _display_buf.find("</think>")
            if tag_end == -1:
                # Still inside think
                safe = _display_buf[:-8] if len(_display_buf) > 8 else ""
                if safe:
                    print(f"\033[2m{safe}\033[0m", end="", flush=True)
                    _display_buf = _display_buf[len(safe):]
                break
            else:
                thinking_text = _display_buf[:tag_end]
                if thinking_text:
                    print(f"\033[2m{thinking_text}\033[0m", end="", flush=True)
                _display_buf = _display_buf[tag_end + len("</think>"):]
                _in_think = False
                print("\n  \033[2m[/thinking]\033[0m", flush=True)

def _stream_flush():
    global _display_buf, _in_think
    if _display_buf:
        if _in_think:
            print(f"\033[2m{_display_buf}\033[0m", flush=True)
            print("\n  \033[2m[/thinking]\033[0m", flush=True)
        else:
            print(_display_buf, end="", flush=True)
    _display_buf = ""
    _in_think = False
