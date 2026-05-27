#!/usr/bin/env python3
"""LaTeX Intelligent Auto-Repair Agent (repair_latex.py).

Queries the local loopback Ollama REST API using the default 'nemotron-3-super:cloud'
model to automatically analyze compiler errors and repair the LaTeX source code in-place.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request


def query_ollama_repair(
    model: str, tex_code: str, error_log: str, host: str = "127.0.0.1:11434"
) -> str:
    url = f"http://{host}/api/generate"

    prompt = f"""You are a world-class LaTeX debugging agent.
We encountered compilation errors. Below is the original LaTeX source code and the exact XeLaTeX compiler error log.
Your task is to analyze the compiler errors and output a repaired, perfectly compilable version of the LaTeX source code.

【Critical Guidelines & Requirements】:
1. Return ONLY the complete, corrected LaTeX code. Start with \\documentclass and end with \\end{{document}}.
2. Do NOT wrap the code in markdown code blocks like ```latex or ```. Output the raw LaTeX code directly so it can be written straight to a .tex file.
3. Preserve all original sections, text paragraphs, bibliographies, and document structures. Do NOT summarize or shorten the document.
4. Fix the syntax errors (e.g. resolve unescaped characters, malformed math equations, missing packages, nested \\includegraphics commands, division-by-zero errors in tables/graphics).

Original LaTeX Source:
--------------------------------------------------
{tex_code}
--------------------------------------------------

XeLaTeX Compiler Error Log:
--------------------------------------------------
{error_log}
--------------------------------------------------
"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,  # Deterministic repair — same error must always yield same fix
        },
    }

    # Force direct loopback connection, bypass proxies
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        # Allow up to 10 minutes for repair generation
        with opener.open(req, timeout=600) as response:
            res = json.loads(response.read().decode("utf-8"))
            return str(res.get("response", "")).strip()
    except Exception as e:
        print(f"Error querying local Ollama REST API during repair: {e}", file=sys.stderr)
        sys.exit(1)


def clean_latex_response(content: str) -> str:
    """Post-process LLM response to ensure raw LaTeX content."""
    # 1. Strip <think>...</think> reasoning blocks if present
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # 2. Strip Thinking... done thinking logs
    content = re.sub(r"(?i)thinking\s*\.\.\..*?done\s*thinking\.?", "", content, flags=re.DOTALL).strip()

    # 3. Strip Markdown code block wrappers
    lines = content.splitlines()
    if len(lines) > 0 and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if len(lines) > 0 and lines[-1].strip().startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 repair_latex.py <model> <tex_file_path> <error_log_text_or_file>", file=sys.stderr)
        sys.exit(1)

    model_name = sys.argv[1]
    tex_path = sys.argv[2]
    error_input = sys.argv[3]

    # Read original tex code
    try:
        with open(tex_path, "r", encoding="utf-8") as f:
            original_code = f.read()
    except Exception as e:
        print(f"Error reading LaTeX file: {e}", file=sys.stderr)
        sys.exit(1)

    # Read error log (can be raw text or path to an error log file)
    if os.path.isfile(error_input):
        try:
            with open(error_input, "r", encoding="utf-8") as f:
                error_log = f.read()
        except Exception as e:
            print(f"Error reading error log file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        error_log = error_input

    print(f">>> Intelligent Repair Agent is analyzing and correcting {tex_path} using {model_name}...")
    repaired_raw = query_ollama_repair(model_name, original_code, error_log)
    repaired_code = clean_latex_response(repaired_raw)

    if not repaired_code.startswith("\\documentclass"):
        print("Warning: Repaired code does not start with \\documentclass. Aborting to prevent file corruption.", file=sys.stderr)
        sys.exit(1)

    # Overwrite the tex file in-place
    try:
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(repaired_code)
        print(f"✅ In-place repair successful! {tex_path} has been updated.")
    except Exception as e:
        print(f"Error writing repaired LaTeX file: {e}", file=sys.stderr)
        sys.exit(1)
