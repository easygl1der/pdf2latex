#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./md2latex.sh INPUT.md [OUTPUT.tex]

Environment:
  OLLAMA_API_KEY or OPENAI_API_KEY       Required API key.
  OLLAMA_BASE_URL or OPENAI_BASE_URL     Default: https://ollama.com/v1
  OLLAMA_MODEL or MODEL                  Default: nemotron-3-super:cloud
  MD2LATEX_CHUNK_CHARS                   Default: 12000
  MD2LATEX_MAX_TOKENS                    Default: 12000
  MD2LATEX_COMPILE                       1 to run xelatex, 0 to skip. Default: 1

Examples:
  ./md2latex.sh demo/demo.md
  MD2LATEX_COMPILE=0 ./md2latex.sh demo/demo.md demo/demo.tex
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

INPUT="${1:-}"
if [[ -z "$INPUT" ]]; then
  echo "Error: missing INPUT.md" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input file not found: $INPUT" >&2
  exit 2
fi

OUTPUT="${2:-${INPUT%.md}.tex}"
API_KEY="${OLLAMA_API_KEY:-${OPENAI_API_KEY:-}}"

if [[ -z "$API_KEY" ]]; then
  echo "Error: set OLLAMA_API_KEY or OPENAI_API_KEY first." >&2
  exit 2
fi

export MD2LATEX_INPUT="$INPUT"
export MD2LATEX_OUTPUT="$OUTPUT"
export MD2LATEX_API_KEY="$API_KEY"
export MD2LATEX_BASE_URL="${OLLAMA_BASE_URL:-${OPENAI_BASE_URL:-https://ollama.com/v1}}"
export MD2LATEX_MODEL="${OLLAMA_MODEL:-${MODEL:-nemotron-3-super:cloud}}"
export MD2LATEX_CHUNK_CHARS="${MD2LATEX_CHUNK_CHARS:-12000}"
export MD2LATEX_MAX_TOKENS="${MD2LATEX_MAX_TOKENS:-12000}"
export MD2LATEX_COMPILE="${MD2LATEX_COMPILE:-1}"

python3 - <<'PY'
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"Error: {name} must be an integer, got {raw!r}")
    if value <= 0:
        raise SystemExit(f"Error: {name} must be positive, got {value}")
    return value


input_path = Path(os.environ["MD2LATEX_INPUT"]).resolve()
output_path = Path(os.environ["MD2LATEX_OUTPUT"]).resolve()
api_key = os.environ["MD2LATEX_API_KEY"]
base_url = os.environ["MD2LATEX_BASE_URL"].rstrip("/")
model = os.environ["MD2LATEX_MODEL"]
chunk_chars = env_int("MD2LATEX_CHUNK_CHARS", 12000)
max_tokens = env_int("MD2LATEX_MAX_TOKENS", 12000)
compile_pdf = os.environ.get("MD2LATEX_COMPILE", "1") not in {"0", "false", "False", "no", "No"}


SYSTEM_PROMPT = r"""You are a LaTeX conversion engine.
Convert Markdown from a parsed academic PDF into faithful LaTeX body content.
Rules:
- Output raw LaTeX only.
- Do not include \documentclass, preamble, \begin{document}, or \end{document}.
- Preserve mathematical meaning, symbols, labels, references, tables, lists, and section structure.
- Prefer \( ... \) for inline math and display equations as:
\[
...
\]
- Keep image paths unchanged inside \includegraphics when images appear.
- Use standard packages only: amsmath, amssymb, mathtools, amsthm, graphicx, booktabs, longtable, array, hyperref.
- If OCR text is noisy, transcribe it conservatively instead of inventing missing content.
"""


def split_markdown(text: str, limit: int) -> list[str]:
    lines = text.splitlines(keepends=True)
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        starts_section = re.match(r"^#{1,3}\s+\S", line) is not None
        if starts_section and current:
            sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))

    chunks: list[str] = []
    for section in sections:
        if len(section) <= limit:
            chunks.append(section)
            continue

        paragraphs = re.split(r"(\n\s*\n)", section)
        buf = ""
        for part in paragraphs:
            if len(buf) + len(part) <= limit:
                buf += part
                continue
            if buf.strip():
                chunks.append(buf)
                buf = ""
            if len(part) <= limit:
                buf = part
                continue
            for i in range(0, len(part), limit):
                piece = part[i : i + limit]
                if piece.strip():
                    chunks.append(piece)
        if buf.strip():
            chunks.append(buf)

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def clean_latex(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:latex|tex)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    begin = text.find(r"\begin{document}")
    if begin != -1:
        text = text[begin + len(r"\begin{document}") :]
    end = text.find(r"\end{document}")
    if end != -1:
        text = text[:end]
    text = re.sub(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", "", text)
    text = re.sub(r"\\usepackage(?:\[[^\]]*\])?\{[^}]+\}", "", text)
    return text.strip()


def api_url() -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def post_chat(messages: list[dict[str, str]], attempt: int = 1) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        api_url(),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code} from {api_url()}: {detail}") from exc
    except URLError as exc:
        if attempt < 3:
            time.sleep(2 * attempt)
            return post_chat(messages, attempt + 1)
        raise RuntimeError(f"Network error while calling {api_url()}: {exc}") from exc

    try:
        data = json.loads(raw)
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unexpected API response: {raw[:1000]}") from exc

    if not content.strip():
        raise RuntimeError(f"API returned empty content. Response summary: {raw[:1000]}")
    return content


def build_preamble(source_dir: Path) -> str:
    rel_source = os.path.relpath(source_dir, output_path.parent)
    rel_images = os.path.join(rel_source, "images")
    graphic_paths = ["./"]
    for item in (rel_source, rel_images):
        item = item.replace("\\", "/")
        if item != ".":
            graphic_paths.append(item.rstrip("/") + "/")

    graphicspath = "".join("{" + path + "}" for path in graphic_paths)
    return rf"""\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{amsmath,amssymb,mathtools,amsthm}}
\usepackage{{graphicx}}
\usepackage{{booktabs,longtable,array}}
\usepackage{{enumitem}}
\usepackage{{caption}}
\usepackage{{float}}
\usepackage[hidelinks]{{hyperref}}
\setmainfont{{Latin Modern Roman}}
\graphicspath{{{graphicspath}}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.6em}}
\begin{{document}}
"""


def compile_with_xelatex(tex_path: Path) -> None:
    if shutil.which("xelatex") is None:
        print("Warning: xelatex not found; wrote TeX only.", file=sys.stderr)
        return

    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-output-directory",
        str(tex_path.parent),
        str(tex_path),
    ]
    last = None
    for _ in range(2):
        last = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if last.returncode != 0:
            break
    if last and last.returncode != 0:
        log_path = tex_path.with_suffix(".compile.log")
        log_path.write_text(last.stdout, encoding="utf-8")
        tail = "\n".join(last.stdout.splitlines()[-40:])
        raise RuntimeError(f"xelatex failed. Log: {log_path}\n{tail}")


def main() -> int:
    markdown = input_path.read_text(encoding="utf-8")
    chunks = split_markdown(markdown, chunk_chars)
    if not chunks:
        raise SystemExit("Error: input Markdown is empty.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Model: {model}")
    print(f"Endpoint: {api_url()}")
    print(f"Chunks: {len(chunks)}")

    body_parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        print(f"Converting chunk {index}/{len(chunks)} ({len(chunk)} chars)...", flush=True)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Convert this Markdown fragment to LaTeX body content.\n\n{chunk}",
            },
        ]
        body_parts.append(clean_latex(post_chat(messages)))

    tex = build_preamble(input_path.parent) + "\n\n".join(body_parts) + "\n\\end{document}\n"
    output_path.write_text(tex, encoding="utf-8")
    print(f"Wrote: {output_path}")

    if compile_pdf:
        print("Compiling with xelatex...")
        compile_with_xelatex(output_path)
        print(f"Wrote: {output_path.with_suffix('.pdf')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
PY
