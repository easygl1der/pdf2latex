"""
LLM 客户端封装：get_client / call_llm

MiniMax M2.7 的 thinking 内容直接混在 content 流里，
用 <think>...</think> 标签包裹，没有单独的 reasoning_content 字段。
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
        )
    return _client_cache[model_name]

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.3,
             show_thinking: bool = True) -> str:
    client, model = get_client(model_name)

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=temperature,
        max_tokens=196608,
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
    # Strip <think>...</think> from the returned value (keep only answer)
    import re
    answer = re.sub(r'<think>.*?</think>', '', full, flags=re.DOTALL).strip()
    return answer


# ── streaming display state ───────────────────────────────────
_display_buf = ""
_in_think = False

def _stream_print(piece: str):
    global _display_buf, _in_think
    _display_buf += piece

    while True:
        if not _in_think:
            tag_start = _display_buf.find("<think>")
            if tag_start == -1:
                # No think tag yet — safe to print everything except last 6 chars
                # (could be partial "<think" at the end)
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
                # Still inside think — print everything except last 8 chars
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
