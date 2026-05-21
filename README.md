# pdf2latex — PDF to LaTeX Automatic Conversion Tool

## Overview
Given any PDF (textbook/paper/book), pdf2latex automatically converts it into a complete LaTeX project using a specified template.

## Architecture
```
PDF File
  │
  ▼  Step 1: MinerU API
[Transcription Node] ──→ output/converted.md
  │
  ▼  Step 2: Supervisor Agent
[Chapter Partitioning] ──→ [{index, title, content}, ...]
  │
  │  Send API (Parallel Dispatch)
  ├──→ [Sub-Agent Ch 1] ──┐
  ├──→ [Sub-Agent Ch 2] ──┤  Convert to LaTeX based on template
  └──→ [Sub-Agent Ch N] ──┤
                          │
  ▼  Step 4 (Gather)      │
[Retriever] ←─────────────┘  Formatting consistency check
  │
  ▼  Step 5
[Assembler] ──→ output/ch01_xxx.tex
            ──→ output/ch02_xxx.tex
            ──→ output/main.tex          (Full merged version)
            ──→ output/main_modular.tex  (Modular version with \input)
```

## Installation
```bash
pip install -r requirements.txt
```

## Configure API Keys
```bash
export MINERU_API_KEY="Your MinerU Key"     # Get from mineru.net
# Optional, needed when using OpenAI models:
export OPENAI_API_KEY="Your OpenAI Key"
```

## Usage

```bash
# List available templates
python main.py --list-templates

# Use amsart template (Mathematical paper style)
python main.py mybook.pdf --template amsart

# Use ctexart template (Chinese textbook style)
python main.py mybook.pdf --template ctexart --model ollama

# Use article template + OpenAI model
python main.py mybook.pdf --template article --model openai

# Generate Beamer slides
python main.py mybook.pdf --template beamer
```

## Available Templates

| Template Name | Use Case |
|---------------|----------|
| `amsart`      | Math papers/notes |
| `article`     | General purpose articles/notes |
| `ctexart`     | Chinese textbooks (Chinese prioritized) |
| `beamer`      | Presentations (Slides) |

## Adding Custom Templates
Add a new entry to the `TEMPLATES` dictionary in `scripts/config.py`:
```python
"mytemplate": {
    "desc": "My Template Description",
    "preamble": r"""\documentclass{...}
...
""",
    "body_wrapper": r"""\begin{document}
__BODY__
\end{document}
""",
    "style_hint": "Tell the AI what environments and styles to use",
},
```

## Output Files
- `output/<stem>/<stem>.md`       — MinerU transcription output (cached automatically).
- `output/<stem>/snippets/`      — Individual chapter tex files.
- `output/<stem>/reviewed_snippets/` — Snippets reviewed by the Retriever.
- `output/<stem>/main.tex`       — Merged version (compile directly).
- `output/<stem>/main_modular.tex` — Modular version (using \input for each chapter).
