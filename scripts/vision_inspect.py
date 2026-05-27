#!/usr/bin/env python3
"""Vision analysis helper for inspect_pdf.sh.

Usage:
    python3 scripts/vision_inspect.py [--mode front|back] <model> <img1.jpg> [img2.jpg] ...

Modes:
    front (default): Analyze cover pages — identify LaTeX template, title, author, date, etc.
    back:            Analyze tail pages — identify bibliography / reference citation style.

Always bypasses system proxies — Ollama is local, it handles its own cloud routing.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request


PROMPT_FRONT = r"""Analyze these PDF page images (cover/front pages) and extract structured information.

Output the following in a clean, organized format:

1. LaTeX Template / Document Class
   - Likely documentclass (article, beamer, IEEEtran, acmart, revtex4, elsarticle, etc.)
   - Any visible journal/conference name or template indicators

2. \maketitle Required Fields
   - \title{}: Full title of the document
   - \author{}: All authors (list each separately)
   - \date{}: Publication or submission date
   - \institute{} or \affiliation{}: Author affiliations / institutions
   - \email{}: Author emails (if visible)
   - \thanks{}: Acknowledgment footnotes (if visible)

3. Additional Metadata
   - Abstract: First sentence or key phrase only
   - Keywords (if listed)
   - DOI / arXiv ID / Paper ID (if visible)
   - Journal / Conference name (if visible)

4. Structural Observations
   - Document language (English / Chinese / other)
   - Number of columns (1 or 2)
   - Special elements visible (figures, tables, algorithms, code)

If a field is not visible, write "Not visible"."""


PROMPT_BACK = r"""Analyze these PDF page images (final/back pages) and identify the bibliography and citation style.

Output the following in a clean, organized format:

1. Citation Style
   - Style name (e.g., IEEE, APA, MLA, Chicago, Vancouver, Nature, ACM, Harvard, BibTeX plain, etc.)
   - In-text citation format (e.g., [1], (Author, Year), superscript number, Author Year)

2. Reference List Format
   - Reference list title (e.g., "References", "Bibliography", "Works Cited")
   - Entry ordering (numbered, alphabetical by author, etc.)
   - Author format (Last, First. / First Last / Last F. etc.)
   - Title format (italics, quotes, plain, etc.)
   - Journal/Book format (abbreviated, full name, italics, etc.)
   - Year position (after author, at end, etc.)
   - URL/DOI format (if visible)

3. LaTeX Bibliography Package
   - Most likely LaTeX package: natbib / biblatex / bibtex plain / apacite / other
   - Suggested \bibliographystyle{} value (e.g., plain, unsrt, alpha, ieeetr, apalike)

4. Sample Entry
   - Copy or reconstruct one complete reference entry as shown in the document

If the pages show no references section, write "No references visible on these pages"."""


def main() -> None:
    args = list(sys.argv[1:])

    # Parse --mode flag
    mode = "front"
    if "--mode" in args:
        idx = args.index("--mode")
        mode = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if len(args) < 2:
        print("Usage: vision_inspect.py [--mode front|back] <model> <img1.jpg> ...", file=sys.stderr)
        sys.exit(1)

    model = args[0]
    image_paths = args[1:]
    prompt = PROMPT_FRONT if mode == "front" else PROMPT_BACK

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
        print(f"    [{mode}] Encoded: {os.path.basename(path)} ({size_kb}KB)", flush=True)

    if not images_b64:
        print("Error: no valid image files found", file=sys.stderr)
        sys.exit(1)

    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "options": {"temperature": 0},
    }

    url = "http://127.0.0.1:11434/api/generate"

    # Always bypass proxies — Ollama is local, it handles its own cloud routing
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    label = "front pages" if mode == "front" else "back pages (references)"
    print(f"\n    [{mode}] Querying {model} for {label}...", flush=True)
    try:
        with opener.open(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response_text = result.get("response", "").strip()
            print(response_text)
    except Exception as e:
        print(f"    [{mode}] API call failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
