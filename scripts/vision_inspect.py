#!/usr/bin/env python3
"""Vision analysis helper for inspect_pdf.sh.

Usage:
    python3 scripts/vision_inspect.py <model> <img1.jpg> [img2.jpg] [img3.jpg]

Sends images as base64 to the local Ollama vision API and prints the LLM response.
Always bypasses system proxies — Ollama is local, it handles its own cloud routing.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request


PROMPT = r"""Analyze these PDF page images and extract structured information.

Identify and output the following in a clean, organized format:

1. LaTeX Template / Document Class
   - What documentclass is likely used? (e.g., article, beamer, IEEEtran, acmart, revtex4, elsarticle, etc.)
   - Any visible journal/conference name or template indicators

2. \maketitle Required Fields
   - \title{}: The full title of the document
   - \author{}: All authors (list each separately if multiple)
   - \date{}: Publication or submission date (if visible)
   - \institute{} or \affiliation{}: Author affiliations / institutions
   - \email{}: Author emails (if visible)
   - \thanks{}: Acknowledgment footnotes (if visible)

3. Additional Metadata
   - Abstract (first sentence or key phrase only)
   - Keywords (if listed)
   - DOI / arXiv ID / Paper ID (if visible)
   - Journal / Conference name (if visible)

4. Structural Observations
   - Document language (English / Chinese / other)
   - Approximate number of columns (1 or 2)
   - Any special elements visible (e.g., figures, tables, algorithms, code blocks)

Output everything in a clean structured format. If a field is not visible in the pages, write "Not visible"."""


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: vision_inspect.py <model> <img1.jpg> [img2.jpg] ...", file=sys.stderr)
        sys.exit(1)

    model = sys.argv[1]
    image_paths = sys.argv[2:]

    # Encode all images as base64
    images_b64: list[str] = []
    for path in image_paths:
        if not os.path.isfile(path):
            print(f"Warning: image not found, skipping: {path}", file=sys.stderr)
            continue
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        images_b64.append(encoded)
        size_kb = len(encoded) // 1024
        print(f"    ✅ Encoded: {os.path.basename(path)} ({size_kb}KB base64)", flush=True)

    if not images_b64:
        print("Error: no valid image files found", file=sys.stderr)
        sys.exit(1)

    payload = {
        "model": model,
        "prompt": PROMPT,
        "images": images_b64,
        "stream": False,
        "options": {"temperature": 0},
    }

    url = "http://127.0.0.1:11434/api/generate"

    # Always bypass proxies — Ollama is local, it routes cloud calls itself
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    print(f"\n    Querying {model} with {len(images_b64)} image(s), please wait...", flush=True)
    try:
        with opener.open(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response_text = result.get("response", "").strip()
            print(response_text)
    except Exception as e:
        print(f"    ❌ API call failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
