"""
LLM Client Wrapper: get_client / call_llm

Ollama is compatible with the OpenAI API via OLLAMA_BASE_URL / OLLAMA_MODEL_NAME.
"""

import sys
import time
import threading
import re
from openai import OpenAI
from .config import MODELS

_client_cache = {}

def get_client(model_name: str, timeout: float = 300.0) -> tuple:
    # Use (model_name, timeout) as cache key to allow timeout changes
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
    """Finds and removes the longest overlap between the end of old_text and start of new_text."""
    if not old_text or not new_text:
        return new_text
        
    # Look back up to 150 characters for a match
    max_check = min(len(old_text), len(new_text), 150)
    
    # 1. Exact match
    for i in range(max_check, 0, -1):
        if old_text.endswith(new_text[:i]):
            return new_text[i:]
    
    # 2. Fuzzy match (skip common 'corrector' chars added by LLMs in Part N+1)
    # If Part N ends in math mode or command, Part N+1 often adds a redundant $, \, or space
    if new_text[0] in ["$", " ", "\\", "{", "}", "\n"]:
        sub_new = new_text[1:]
        max_check = min(len(old_text), len(sub_new), 150)
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

    def timer_thread():
        start_time = time.time()
        while not first_token_received.is_set():
            elapsed = time.time() - start_time
            label = f"Waiting for model response (Part {continuation_count})"
            print(f"\r  [LLM] {label} ({elapsed:.1f}s)...", end="", flush=True)
            time.sleep(0.1)

    try:
        while True:
            if continuation_count > 1:
                print(f"\n--- [CONTINUING OUTPUT PART {continuation_count}] ---", flush=True)

            # Start timer for each part
            first_token_received.clear()
            t = threading.Thread(target=timer_thread, daemon=True)
            t.start()

            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            current_chunk_buf = []
            finish_reason = None

            for chunk in stream:
                if not chunk.choices: continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
                piece = delta.content or ""
                if piece:
                    if not first_token_received.is_set():
                        first_token_received.set()
                        print("\r" + " " * 60 + "\r", end="", flush=True)
                    current_chunk_buf.append(piece)
                    print(piece, end="", flush=True)

            part_text = "".join(current_chunk_buf)
            parts.append(part_text)
            
            # Smart Continuation Logic
            is_truncated = False
            if continuation_count < 5:
                # 1. API Limit
                if finish_reason in ["length", "max_tokens"]:
                    is_truncated = True
                
                # 2. Structural/Heuristic check
                full_text_so_far = "".join(parts)
                has_start = "\\documentclass" in full_text_so_far or "\\begin{document}" in full_text_so_far
                has_end = "\\end{document}" in full_text_so_far[-100:]
                
                if has_start and not has_end:
                    is_truncated = True
                
                # 3. Micro-check for mid-command
                if not is_truncated and len(part_text) > 500:
                    last_snippet = part_text[-20:].strip()
                    if last_snippet and last_snippet[-1] in ["\\", "{", "[", "(", ",", ":", "+", "-", "=", "_", "^"]:
                        is_truncated = True
                    elif full_text_so_far.count("$") % 2 != 0 or full_text_so_far.count("$$") % 2 != 0:
                        is_truncated = True

            if is_truncated:
                continuation_count += 1
                math_hint = ""
                if full_text_so_far.count("$") % 2 != 0:
                    math_hint = " You are currently INSIDE a math block ($). Resume the math content directly without adding new delimiters."
                elif full_text_so_far.count("$$") % 2 != 0:
                    math_hint = " You are currently INSIDE a display math block ($$). Resume the content directly."

                print(f"\n\n[Auto-Detect] Truncated at {len(full_text_so_far)} chars. Stitching Part {continuation_count}...", flush=True)
                messages.append({"role": "assistant", "content": part_text})
                messages.append({"role": "user", "content": f"Your previous response was cut off.{math_hint} Please continue EXACTLY from the last character you printed. DO NOT repeat anything. Output ONLY the remaining content."})
            else:
                break
    finally:
        first_token_received.set()

    # Final Stitching with Deduplication
    if not parts: return ""
    
    final_result = parts[0]
    for i in range(1, len(parts)):
        prev_part = final_result
        next_part = parts[i]
        cleaned_next = _deduplicate_overlap(prev_part, next_part)
        final_result += cleaned_next

    print("\n", flush=True)
    return final_result
