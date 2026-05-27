#!/usr/bin/env python3
"""Ollama REST API client for Markdown-to-LaTeX conversion (query_ollama.py).

Usage:
    python3 scripts/query_ollama.py <model> <prompt_file> <output_tex_file>

Calls the local Ollama loopback API at 127.0.0.1:11434 with temperature=0
to ensure deterministic, reproducible LaTeX output every run.
Proxy is explicitly bypassed to avoid system proxy interference.
"""
from __future__ import annotations

import json
import sys
import urllib.request


def query_ollama(model: str, prompt: str, host: str = "127.0.0.1:11434") -> str:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,  # Deterministic output — no creativity, strict format conversion
        },
    }

    # Force direct loopback connection, bypass all system proxies
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        # Allow up to 15 minutes for large documents
        with opener.open(req, timeout=900) as response:
            res = json.loads(response.read().decode("utf-8"))
            return str(res.get("response", "")).strip()
    except Exception as e:
        print(f"Error querying Ollama API: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python3 query_ollama.py <model> <prompt_file> <output_tex_file>",
            file=sys.stderr,
        )
        sys.exit(1)

    model_name = sys.argv[1]
    prompt_file = sys.argv[2]
    output_file = sys.argv[3]

    # Read prompt from file
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    except Exception as e:
        print(f"Error reading prompt file '{prompt_file}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f">>> Querying {model_name} (temperature=0)...")
    response = query_ollama(model_name, prompt_text)

    # Write raw response to output file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(response)
        print(f">>> Response written to {output_file}")
    except Exception as e:
        print(f"Error writing output file '{output_file}': {e}", file=sys.stderr)
        sys.exit(1)
