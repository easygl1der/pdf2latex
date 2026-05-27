#!/usr/bin/env python3
"""Ollama streaming client for Markdown-to-LaTeX conversion (query_ollama.py).

Usage:
    python3 scripts/query_ollama.py <model> <prompt_file> <output_tex_file>

Streams the response token-by-token to stderr (so the user can watch progress),
then writes the complete collected response to the output .tex file.

Features:
  - Real-time streaming output (stream: True)
  - <think>...</think> blocks shown in dim gray
  - Timer: time-to-first-token + total elapsed + tokens/sec
  - temperature: 0 for deterministic output
  - Proxy-bypassed (Ollama is local)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

# ANSI color codes
DIM   = "\033[2m"
RESET = "\033[0m"
CYAN  = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BOLD  = "\033[1m"


def stream_ollama(model: str, prompt: str, host: str = "127.0.0.1:11434") -> str:
    """Stream response from Ollama, printing tokens to stderr in real time.
    Returns the complete response as a string."""

    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0},
    }

    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    t_start = time.time()
    t_first_token: float | None = None
    full_response: list[str] = []
    in_think = False
    think_buffer = ""
    total_tokens = 0
    prompt_tokens = 0

    print(f"{CYAN}>>> 等待 {model} 首个 token...{RESET}", file=sys.stderr, flush=True)

    try:
        with opener.open(req, timeout=900) as resp:
            for raw_line in resp:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                token: str = chunk.get("response", "")
                done: bool = chunk.get("done", False)

                # Record time-to-first-token
                if token and t_first_token is None:
                    t_first_token = time.time()
                    wait = t_first_token - t_start
                    print(
                        f"\r{CYAN}>>> 首个 token 等待: {wait:.1f}s  开始输出...{RESET}",
                        file=sys.stderr, flush=True,
                    )
                    print("-" * 60, file=sys.stderr, flush=True)

                # --- Handle <think> blocks ---
                if "<think>" in token:
                    in_think = True
                    # Print [思考] label at start of think block
                    pre, post = token.split("<think>", 1)
                    if pre:
                        sys.stderr.write(pre)
                    sys.stderr.write(f"\n{DIM}[思考]\n")
                    sys.stderr.write(post)
                    sys.stderr.flush()
                    full_response.append(token)
                    continue

                if in_think:
                    if "</think>" in token:
                        in_think = False
                        pre, post = token.split("</think>", 1)
                        sys.stderr.write(pre)
                        sys.stderr.write(f"{RESET}\n[/思考]\n")
                        if post:
                            sys.stderr.write(post)
                        sys.stderr.flush()
                    else:
                        sys.stderr.write(f"{DIM}{token}{RESET}")
                        sys.stderr.flush()
                    full_response.append(token)
                    continue

                # --- Normal output token ---
                sys.stderr.write(token)
                sys.stderr.flush()
                full_response.append(token)

                if done:
                    total_tokens = chunk.get("eval_count", 0)
                    prompt_tokens = chunk.get("prompt_eval_count", 0)
                    break

    except Exception as e:
        print(f"\n{YELLOW}>>> 错误: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - t_start
    tps = total_tokens / elapsed if elapsed > 0 else 0
    t_gen = elapsed - (t_first_token - t_start if t_first_token else elapsed)

    print(f"\n{'-' * 60}", file=sys.stderr)
    print(f"{GREEN}{BOLD}⏱  完成！{RESET}", file=sys.stderr)
    print(f"   总耗时:       {elapsed:.1f}s", file=sys.stderr)
    if t_first_token:
        print(f"   首token等待:  {t_first_token - t_start:.1f}s", file=sys.stderr)
        print(f"   纯生成耗时:   {t_gen:.1f}s", file=sys.stderr)
    print(f"   Prompt tokens: {prompt_tokens}", file=sys.stderr)
    print(f"   输出 tokens:   {total_tokens}", file=sys.stderr)
    print(f"   生成速率:     {tps:.1f} tokens/s", file=sys.stderr)
    print(f"{'-' * 60}", file=sys.stderr, flush=True)

    return "".join(full_response)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python3 query_ollama.py <model> <prompt_file> <output_tex_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    model_name  = sys.argv[1]
    prompt_file = sys.argv[2]
    output_file = sys.argv[3]

    # Read prompt
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    except Exception as e:
        print(f"Error reading prompt file '{prompt_file}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{CYAN}{'=' * 60}", file=sys.stderr)
    print(f"  模型: {BOLD}{model_name}{RESET}{CYAN}", file=sys.stderr)
    print(f"  Prompt 大小: {len(prompt_text)} chars / ~{len(prompt_text.split())} words", file=sys.stderr)
    print(f"{'=' * 60}{RESET}\n", file=sys.stderr, flush=True)

    # Stream and collect response
    response = stream_ollama(model_name, prompt_text)

    # Write to output file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(response)
        print(f"{GREEN}>>> 已写入: {output_file}{RESET}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing output file '{output_file}': {e}", file=sys.stderr)
        sys.exit(1)
