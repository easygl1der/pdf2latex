"""
Configuration: API Keys, Model Lists, Output Directories, LaTeX Template Library
"""

import os
from pathlib import Path
from typing import TypedDict, Annotated, List, Dict
import operator

# ── API Keys ──────────────────────────────────────────────────
MINERU_API_KEY  = os.getenv("MINERU_API_KEY",  "")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY",  "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── Model Configuration ───────────────────────────────────────
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL",   "http://localhost:11434/v1")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "nemotron-3-super:cloud")

MODELS = {
    "openai": {
        "base_url":   "https://api.openai.com/v1",
        "api_key":    lambda: OPENAI_API_KEY,
        "model":      "gpt-4o",
        "max_tokens": 16384,
    },
    "ollama": {
        "base_url":   OLLAMA_BASE_URL,
        "api_key":    lambda: "ollama",
        "model":      OLLAMA_MODEL_NAME, # Default: nemotron-3-super:cloud
        "max_tokens": 10000,
    },
    "deepseek": {
        "base_url":   "https://api.deepseek.com",
        "api_key":    lambda: DEEPSEEK_API_KEY,
        "model":      "deepseek-chat",
        "max_tokens": 8192,
    },
    "deepseek-v4": {
        "base_url":   OLLAMA_BASE_URL,
        "api_key":    lambda: "ollama",
        "model":      "deepseek-v4-flash:cloud",
        "max_tokens": 64000, 
    },
    "gemini": {
        "base_url":   OLLAMA_BASE_URL,
        "api_key":    lambda: "ollama",
        "model":      "gemini-3-flash-preview:cloud",
        "max_tokens": 64000, # Large output limit
    },
    "gemma-vision": {
        "base_url":   OLLAMA_BASE_URL,
        "api_key":    lambda: "ollama",
        "model":      "gemma4:31b-cloud",
        "max_tokens": 18000,
    },
    "gpt-oss": {
        "base_url":   OLLAMA_BASE_URL,
        "api_key":    lambda: "ollama",
        "model":      "gpt-oss:120b-cloud",
        "max_tokens": 32000,
    }
}

# ── Root Output Directory ───────────────────────────────────────
OUTPUT_ROOT = Path(__file__).parent.parent / "output"

# ── LaTeX Template Library ─────────────────────────────────────

class TemplateInfo(TypedDict):
    desc: str
    preamble: str
    body_wrapper: str
    style_hint: str
    detailed_instructions: str

TEMPLATES: Dict[str, TemplateInfo] = {

    "amsart": {
        "desc": "AMS Article — Professional math style with comprehensive theorem environments.",
        "preamble": r"""\documentclass{amsart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{fontspec}
\usepackage[fontset=mac, scheme=plain]{ctex}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref}
\usepackage{cleveref}

\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{definition}[theorem]{Definition}
\theoremstyle{remark}
\newtheorem{remark}{Remark}[section]
\newtheorem{example}{Example}[section]

\title{__TITLE__}
\author{__AUTHOR__}
\date{__DATE__}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
__BODY__

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
""",
        "style_hint": "Use AMS style: theorem/lemma/definition/remark environments, math in align* or equation. ALWAYS use \caption and \label for figures/tables.",
        "detailed_instructions": r"""
### AMSART Template Specific Instructions:
1. **Figures and Tables**:
   - ALWAYS use `\begin{figure}[H]` or `\begin{table}[H]` with the `float` package.
   - Every figure/table MUST have a `\caption{...}` and a `\label{figure:xxx}` or `\label{table:xxx}`.
   - Use `\includegraphics[width=0.8\textwidth]{...}` to ensure images fit the page.
   - For tables, use `booktabs` commands: `\toprule`, `\midrule`, `\bottomrule`.
2. **Theorem Environments**: Use standard AMS environments.
3. **Math Formatting**: Prefer `align*` for equations.
"""
    },

    "article": {
        "desc": "Standard Article — Clean and general-purpose, suitable for textbook notes.",
        "preamble": r"""\documentclass[12pt, a4paper]{article}
\usepackage{fontspec}
\usepackage[fontset=mac, scheme=plain]{ctex}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\geometry{top=2.5cm, bottom=2.5cm, left=3cm, right=3cm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref, xcolor, enumitem}
\usepackage{cleveref}

\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{definition}[theorem]{Definition}
\theoremstyle{remark}
\newtheorem*{remark}{Note}

\title{__TITLE__}
\author{__AUTHOR__}
\date{__DATE__}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
\newpage
__BODY__

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
""",
        "style_hint": "Use standard article style: section/subsection hierarchy, English theorem names. ALWAYS use \caption and \label for figures/tables.",
        "detailed_instructions": r"""
### Standard Article Template Specific Instructions:
1. **Figures and Tables**:
   - ALWAYS use `\begin{figure}[H]` or `\begin{table}[H]`.
   - Every figure/table MUST have a `\caption{...}` and a `\label{figure:xxx}` or `\label{table:xxx}`.
   - For tables, use `booktabs` (toprule/midrule/bottomrule).
2. **Structural Levels**: Start with `\section`.
"""
    },

    "ctexart": {
        "desc": "CTeX Article — Best for documents with significant Chinese content.",
        "preamble": r"""\documentclass[12pt, a4paper, UTF8]{ctexart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{caption}
\usepackage{float}
\usepackage{multirow}
\usepackage{algorithm}
\usepackage{algpseudocode}
\usepackage{hyperref}
\usepackage{cleveref}

\newtheorem{theorem}{定理}[section]
\newtheorem{lemma}[theorem]{引理}
\newtheorem{definition}[theorem]{定义}
\newtheorem{example}[theorem]{例}
\theoremstyle{remark}
\newtheorem*{remark}{注记}

\title{__TITLE__}
\author{__AUTHOR__}
\date{__DATE__}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
\newpage
__BODY__

\bibliographystyle{plain}
\bibliography{refs}
\end{document}
""",
        "style_hint": "Use CTeX style: Chinese environment names, section/subsection hierarchy.",
        "detailed_instructions": r"""
### CTeX Article Template Specific Instructions:
1. **Figures and Tables**:
   - ALWAYS use `\begin{figure}[H]` or `\begin{table}[H]`.
   - Every figure/table MUST have a `\caption{...}` and a `\label{figure:xxx}` or `\label{table:xxx}`.
"""
    },

    "beamer": {
        "desc": "Beamer Slides — For creating academic presentations.",
        "preamble": r"""\documentclass{beamer}
\usepackage{fontspec}
\usepackage[fontset=mac, scheme=plain]{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{caption}
\usetheme{Madrid}
\usecolortheme{default}

\title{__TITLE__}
\author{__AUTHOR__}
\date{__DATE__}
""",
        "body_wrapper": r"""\begin{document}
\begin{frame}
\titlepage
\end{frame}
\begin{frame}{Contents}
\tableofcontents
\end{frame}
__BODY__
\end{document}
""",
        "style_hint": "Use Beamer style: each key point as a frame, use block environments for emphasis.",
        "detailed_instructions": r"""
### Beamer Presentation Template Specific Instructions:
1. **Frames**: Every slide must be wrapped in a `\begin{frame}{...} ... \end{frame}`.
2. **Images**: Use `\begin{figure} \centering \includegraphics[height=0.6\textheight]{...} \end{figure}`.
"""
    },
}

# ── LangGraph State Types ─────────────────────────────────────

class Chapter(TypedDict):
    index: int
    title: str
    level: int
    line_start: int
    line_end: int

class ChapterOutput(TypedDict):
    index: int
    title: str
    markdown_body: str
    latex_body: str

class PipelineState(TypedDict):
    pdf_path:        str
    markdown_path:   str
    content_list_path: str
    template_name:   str
    model_name:      str
    mode:            str   # "notes" | "original"
    validate:        bool  # Enable surgical validation
    doc_title:       str
    doc_type:        str
    output_dir:      str
    chapters:        List[Chapter]
    chapter_outputs: Annotated[List[ChapterOutput], operator.add]
    final_latex:     str

class WriterInput(TypedDict):
    chapter:       Chapter
    markdown_path: str
    content_list_path: str
    all_titles:    List[str]
    template_name: str
    model_name:    str
    mode:          str
    doc_type:      str
    output_dir:    str
    pdf_path:      str
