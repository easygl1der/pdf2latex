import os
from pathlib import Path
from typing import Dict, TypedDict

# ── Paths ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT  = PROJECT_ROOT / "output"
PDF_ROOT     = PROJECT_ROOT / "pdf"

# ── API Keys ──────────────────────────────────────────────────
MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# ── LaTeX Templates ───────────────────────────────────────────
class Template(TypedDict):
    name: str
    desc: str
    preamble: str
    body_wrapper: str

TEMPLATES: Dict[str, Template] = {
    "amsart": {
        "name": "amsart",
        "desc": "AMS Article - Math Focused",
        "preamble": r"""\documentclass{amsart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Songti SC}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{cleveref}
\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\title{__TITLE__}
\author{pdf2latex}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
__BODY__
\end{document}
"""
    },
    "article": {
        "name": "article",
        "desc": "Standard Article",
        "preamble": r"""\documentclass[12pt, a4paper]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Songti SC}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\usepackage{graphicx}
\geometry{margin=2.5cm}
\usepackage{hyperref}
\title{__TITLE__}
\author{pdf2latex}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
\newpage
__BODY__
\end{document}
"""
    },
    "ctexart": {
        "name": "ctexart",
        "desc": "CTeX Article - Chinese Optimized",
        "preamble": r"""\documentclass[12pt, a4paper, UTF8]{ctexart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\usepackage{graphicx}
\geometry{margin=2.5cm}
\usepackage{hyperref}
\setCJKmainfont{Songti SC}
\title{__TITLE__}
\author{}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
\newpage
__BODY__
\end{document}
"""
    }
}
