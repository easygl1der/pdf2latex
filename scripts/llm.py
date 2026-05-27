"""
LLM Client Wrapper: simplified call_llm with structural continuation.
"""

import sys
import time
import threading
from openai import OpenAI
from .config import MODELS

_client_cache = {}

def get_client(model_name: str, timeout: float = 300.0) -> tuple:
    cache_key = (model_name, timeout)
    if cache_key not in _client_cache:
        cfg = MODELS[model_name]
        _client_cache[cache_key] = (
            OpenAI(
                api_key=cfg["api_key"](), 
                base_url=cfg["base_url"],
                timeout=timeout
            ),
            cfg["model"],
            cfg.get("max_tokens", 8192),
        )
    return _client_cache[cache_key]

def _deduplicate_overlap(old_text: str, new_text: str) -> str:
    """Standard deduplication for stitching parts."""
    if not old_text or not new_text: return new_text
    max_check = min(len(old_text), len(new_text), 200)
    for i in range(max_check, 0, -1):
        if old_text.endswith(new_text[:i]):
            return new_text[i:]
    # Fuzzy skip for leading common characters
    if new_text[0] in ["$", " ", "\\", "{", "}", "\n", "_", "^"]:
        sub_new = new_text[1:]
        max_check = min(len(old_text), len(sub_new), 200)
        for i in range(max_check, 0, -1):
            if old_text.endswith(sub_new[:i]):
                return sub_new[i:]
    return new_text

def call_llm(model_name: str, system: str, user: str, temperature: float = 0.0,
             show_thinking: bool = False, image_b64: str = None, timeout: float = 300.0) -> str:
    client, model, max_tokens = get_client(model_name, timeout=timeout)
    
    user_content = user
    if image_b64:
        mime_type = "image/jpeg" if image_b64.startswith("/9j/") else "image/png"
        user_content = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}}
        ]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]
    
    parts = []
    first_token_received = threading.Event()
    continuation_count = 1

    def timer_thread(part_num):
        start_time = time.time()
        while not first_token_received.is_set():
            elapsed = time.time() - start_time
            print(f"\r  [LLM] Waiting for Part {part_num} ({elapsed:.1f}s)...", end="", flush=True)
            time.sleep(0.1)

    try:
        while True:
            first_token_received.clear()
            t = threading.Thread(target=timer_thread, args=(continuation_count,), daemon=True)
            t.start()

            stream = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, 
                max_tokens=max_tokens, stream=True
            )

            current_chunk = []
            for chunk in stream:
                if not chunk.choices: continue
                piece = chunk.choices[0].delta.content or ""
                if piece:
                    if not first_token_received.is_set():
                        first_token_received.set()
                        print("\r" + " " * 60 + "\r", end="", flush=True)
                    current_chunk.append(piece)
                    print(piece, end="", flush=True)

            text = "".join(current_chunk)
            parts.append(text)
            
            # SIMPLIFIED CONTINUATION LOGIC
            is_truncated = False
            full_so_far = "".join(parts)
            
            # Rule: If it's a full doc but missing \end{document}, it's truncated.
            is_full_doc = "\\documentclass" in full_so_far or "\\begin{document}" in full_so_far
            has_end = "\\end{document}" in full_so_far[-100:]
            
            if is_full_doc and not has_end and continuation_count < 10:
                is_truncated = True

            if is_truncated:
                continuation_count += 1
                print(f"\n\n[Auto-Detect] Truncated. Stitching Part {continuation_count}...", flush=True)
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": "Please continue exactly from where you left off. Do not repeat anything. Just the remaining content."})
            else:
                break
    finally:
        first_token_received.set()

    # Stitch with deduplication
    res = parts[0]
    for i in range(1, len(parts)):
        res += _deduplicate_overlap(res, parts[i])
    print("\n", flush=True)
    return res
