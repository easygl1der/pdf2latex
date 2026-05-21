"""
配置：API Keys、模型列表、输出目录、LaTeX 模板库
"""

import os
from pathlib import Path
from typing import TypedDict, Annotated, List
import operator

# ── API Keys ──────────────────────────────────────────────────
MINERU_API_KEY  = os.getenv("MINERU_API_KEY",  "")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY",  "")

# ── 模型配置 ──────────────────────────────────────────────────
MODELS = {
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "api_key":  lambda: MINIMAX_API_KEY,
        "model":    "MiniMax-M2.7-highspeed",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key":  lambda: OPENAI_API_KEY,
        "model":    "gpt-4o",
    },
}

# ── 输出目录 ──────────────────────────────────────────────────
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── LaTeX 模板库 ──────────────────────────────────────────────
TEMPLATES = {

    "amsart": {
        "desc": "AMS Article — 适合数学论文/笔记，自带定理环境",
        "preamble": r"""\documentclass{amsart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage[UTF8]{ctex}
\usepackage{hyperref}

\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{definition}[theorem]{Definition}
\theoremstyle{remark}
\newtheorem{remark}{Remark}[section]
\newtheorem{example}{Example}[section]

\title{__TITLE__}
\author{Notes}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\begin{abstract}
本文档由 pdf2latex 自动生成，基于原始 PDF 转换。
\end{abstract}
\maketitle
\tableofcontents
__BODY__
\end{document}
""",
        "style_hint": "使用 AMS 风格：theorem/lemma/definition/remark 环境，数学内容用 align* 或 equation 环境",
    },

    "article": {
        "desc": "标准 Article — 通用文章，适合教材笔记",
        "preamble": r"""\documentclass[12pt, a4paper]{article}
\usepackage[UTF8]{ctex}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\geometry{top=2.5cm, bottom=2.5cm, left=3cm, right=3cm}
\usepackage{hyperref, xcolor, enumitem}

\newtheorem{theorem}{定理}[section]
\newtheorem{lemma}[theorem]{引理}
\newtheorem{definition}[theorem]{定义}
\theoremstyle{remark}
\newtheorem*{remark}{注}

\title{__TITLE__}
\author{笔记}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\maketitle
\tableofcontents
\newpage
__BODY__
\end{document}
""",
        "style_hint": "使用标准 article 风格：section/subsection 层级，中文定理环境名（定理/引理/定义/注）",
    },

    "ctexart": {
        "desc": "CTeX Article — 中文优先，适合中文教材",
        "preamble": r"""\documentclass[12pt, a4paper, UTF8]{ctexart}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{hyperref, xcolor}

\newtheorem{theorem}{定理}[section]
\newtheorem{lemma}[theorem]{引理}
\newtheorem{definition}[theorem]{定义}
\newtheorem{example}[theorem]{例}
\theoremstyle{remark}
\newtheorem*{remark}{注记}

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
""",
        "style_hint": "使用 CTeX 风格：所有环境名用中文，章节用 section，中文排版优先",
    },

    "beamer": {
        "desc": "Beamer 幻灯片 — 将教材内容转成演示文稿",
        "preamble": r"""\documentclass{beamer}
\usepackage[UTF8]{ctex}
\usepackage{amsmath, amssymb}
\usetheme{Madrid}
\usecolortheme{default}

\title{__TITLE__}
\author{Notes}
\date{\today}
""",
        "body_wrapper": r"""\begin{document}
\begin{frame}
\titlepage
\end{frame}
\begin{frame}{目录}
\tableofcontents
\end{frame}
__BODY__
\end{document}
""",
        "style_hint": "使用 Beamer 风格：每章对应一个 section，每个知识点是一个 frame，重要内容用 block 环境",
    },
}

# ── LangGraph 状态类型 ────────────────────────────────────────

class Chapter(TypedDict):
    index: int
    title: str
    line_start: int
    line_end: int

class ChapterOutput(TypedDict):
    index: int
    title: str
    latex_body: str

class PipelineState(TypedDict):
    pdf_path:        str
    markdown_path:   str
    template_name:   str
    model_name:      str
    doc_title:       str
    chapters:        List[Chapter]
    chapter_outputs: Annotated[List[ChapterOutput], operator.add]
    final_latex:     str

class WriterInput(TypedDict):
    chapter:       Chapter
    markdown_path: str
    all_titles:    List[str]
    template_name: str
    model_name:    str
