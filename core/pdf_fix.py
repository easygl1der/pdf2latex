"""MinerU PDF 输出后处理修复模块。

修复 MinerU vlm/pipeline 模型在 PDF 解析中产生的系统性问题：
  1. 预组合字符 —— PDF 字体将 é 拆成 e + 独立音标符 ´
  2. \text{} 字符间距 —— PDF 逐字提取导致 "f o r a l l"
  3. 丢失 \to 箭头 —— PDF U+2192 箭头被 vlm 识别为双空格
  4. display math 中数字序列 —— tabular 排版导致 "1 2 3 4"
  5. Mojibake —— 编码回退产生 "Â´" 等乱码（via ftfy）

主入口：
    fixed_text = fix_all(markdown_text)

所有修复均为保守策略，不会修改 LaTeX math 符号语义（仅清理排版噪声）。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

try:
    import ftfy as _ftfy
    _HAS_FTFY = True
except ImportError:
    _HAS_FTFY = False


# ── 修复 1：独立音标符 + 字母 → 预组合字符 ─────────────────────────────────

_DIACRITIC_MAP: dict[str, str] = {}


def _build_diacritic_map() -> None:
    """构建"独立音标符 + 字母"→ 预组合字符的映射表。"""
    pairs = [
        ('\u00b4', '\u0301'),  # ´ ACUTE ACCENT         → COMBINING ACUTE
        ('\u0060', '\u0300'),  # ` GRAVE ACCENT          → COMBINING GRAVE
        ('\u00a8', '\u0308'),  # ¨ DIAERESIS             → COMBINING DIAERESIS
        ('\u02c6', '\u0302'),  # ˆ MODIFIER CIRCUMFLEX   → COMBINING CIRCUMFLEX
        ('\u02dc', '\u0303'),  # ˜ SMALL TILDE           → COMBINING TILDE
        ('\u02dd', '\u030b'),  # ˝ DOUBLE ACUTE          → COMBINING DOUBLE ACUTE
        ('\u02c7', '\u030c'),  # ˇ CARON                 → COMBINING CARON
        ('\u02d8', '\u0306'),  # ˘ BREVE                 → COMBINING BREVE
        ('\u02d9', '\u0307'),  # ˙ DOT ABOVE             → COMBINING DOT ABOVE
        ('\u00b8', '\u0327'),  # ¸ CEDILLA               → COMBINING CEDILLA
        ('\u02db', '\u0328'),  # ˛ OGONEK                → COMBINING OGONEK
        ('\u00af', '\u0304'),  # ¯ MACRON                → COMBINING MACRON
        ('\u02da', '\u030a'),  # ˚ RING ABOVE            → COMBINING RING ABOVE
    ]
    base_letters = 'aeiouycnszrldtgAEIOUYCNSZRLDTG'
    for standalone, combining in pairs:
        for letter in base_letters:
            combined = unicodedata.normalize('NFC', letter + combining)
            if combined != letter + combining:
                _DIACRITIC_MAP[standalone + letter] = combined
                _DIACRITIC_MAP[letter + standalone] = combined


_build_diacritic_map()


def fix_precomposed_chars(text: str) -> str:
    """将独立音标符+字母替换为预组合 Unicode 字符；调用 ftfy 修复 Mojibake。"""
    if _HAS_FTFY:
        text = _ftfy.fix_text(text)
    for pattern, replacement in _DIACRITIC_MAP.items():
        text = text.replace(pattern, replacement)
    return text


# ── 修复 2：\text{} 内字符间距 ───────────────────────────────────────────────

_TEXT_WORD_MAP: dict[str, str] = {
    'forall':  r'\forall',
    'exists':  r'\exists',
    'const':   r'\mathrm{const}',
    'sup':     r'\sup',
    'inf':     r'\inf',
    'max':     r'\max',
    'min':     r'\min',
    'lim':     r'\lim',
    'limsup':  r'\limsup',
    'liminf':  r'\liminf',
    'det':     r'\det',
    'log':     r'\log',
    'exp':     r'\exp',
    'sin':     r'\sin',
    'cos':     r'\cos',
    'tan':     r'\tan',
}


def fix_spaced_text_commands(text: str) -> str:
    r"""修复 \text{f o r a l l} → \forall（或 \text{forall}）。"""
    def _collapse(m: re.Match) -> str:
        content = m.group(1)
        tokens = content.split()
        if len(tokens) >= 3 and all(len(t) == 1 for t in tokens):
            word = ''.join(tokens)
            return _TEXT_WORD_MAP.get(word, r'\text{' + word + '}')
        return m.group(0)

    return re.sub(r'\\text\s*\{([^}]{3,})\}', _collapse, text)


def fix_spaced_roman_commands(text: str) -> str:
    r"""修复 \mathrm { l i n e a r } → \mathrm{linear} 等逐字 OCR 空格。"""
    def _collapse(m: re.Match) -> str:
        command = m.group(1)
        content = m.group(2)
        tokens = content.split()
        if len(tokens) < 3:
            return m.group(0)
        if all(len(t) == 1 or t == '~' for t in tokens):
            return f'\\{command}' + '{' + ''.join(tokens) + '}'
        return m.group(0)

    return re.sub(
        r'\\(mathrm|operatorname|mathsf|mathit|mathbf)\s*\{([^{}]{3,})\}',
        _collapse,
        text,
    )


def fix_adjacent_math_segments(text: str) -> str:
    r"""合并被 MinerU 拆开的相邻 inline math：$...\cong$ $\mathbb{...}$。"""
    connector_re = re.compile(
        r'(?:=|:=|\\cong|\\simeq|\\sim|\\in|\\subseteq?|\\supseteq?|'
        r'\\to|\\mapsto|\\cdot|[+\-*/,(])\s*$'
    )

    def _merge(m: re.Match) -> str:
        left = m.group(1).strip()
        right = m.group(2).strip()
        if connector_re.search(left):
            return f'${left} {right}$'
        return m.group(0)

    prev = None
    while prev != text:
        prev = text
        text = re.sub(
            r'(?<!\$)\$([^$\n]+?)\$\s+\$([^$\n]+?)\$(?!\$)',
            _merge,
            text,
        )
    return text


# ── 修复 3：数学环境中丢失的 \to 箭头 ───────────────────────────────────────

_ARROW_RIGHT_TRIGGERS = (
    r'\\mathbb', r'\\mathcal', r'\\mathfrak', r'\\mathbf',
    r'\\mathrm', r'\\mathit', r'\\mathsf', r'\\infty',
)
_ARROW_RIGHT_PAT = '|'.join(_ARROW_RIGHT_TRIGGERS)


def _fix_arrows_in_math(math: str) -> str:
    math = re.sub(
        r'([A-Za-z}\]^+])  (' + _ARROW_RIGHT_PAT + r')',
        r'\1 \\to \2', math,
    )
    math = re.sub(r'([A-Za-z}\]])  (\\infty)', r'\1 \\to \2', math)
    math = re.sub(r'(?<=[A-Z] )([A-Z])  ([A-Z]\b)', r'\1 \\to \2', math)
    return math


def fix_missing_arrows(text: str) -> str:
    r"""在 display math 和 inline math 中修复双空格 → \to。"""
    def fix_display(m: re.Match) -> str:
        return '$$\n' + _fix_arrows_in_math(m.group(1)) + '\n$$'

    text = re.sub(r'\$\$\n(.*?)\n\$\$', fix_display, text, flags=re.DOTALL)

    def fix_inline(m: re.Match) -> str:
        return '$' + _fix_arrows_in_math(m.group(1)) + '$'

    text = re.sub(
        r'(?<!\$)\$(?!\$)([^$\n]{1,300}?)(?<!\$)\$(?!\$)',
        fix_inline, text,
    )
    return text


# ── 修复 4：display math 中大数字字符间距 ────────────────────────────────────

def fix_digit_sequences(text: str) -> str:
    """修复 display math 中 "5 6 2 1" → "5621"（6+ 位以上才合并）。"""
    def _merge_digits(s: str) -> str:
        return re.sub(
            r'(?<!\d)(\d(?: \d){5,})(?!\d)',
            lambda m: m.group(0).replace(' ', ''),
            s,
        )

    def fix_display(m: re.Match) -> str:
        return '$$\n' + _merge_digits(m.group(1)) + '\n$$'

    return re.sub(r'\$\$\n(.*?)\n\$\$', fix_display, text, flags=re.DOTALL)


def fix_unicode_math_text_noise(text: str) -> str:
    r"""保守修复数学上下文里的 Unicode 数学符号噪声。"""
    replacements = {
        '−': '-',
        '∈': r'\in',
        'Φ': r'\Phi',
        'γ': r'\gamma',
        'π': r'\pi',
        'τ': r'\tau',
        'β': r'\beta',
    }

    def _replace_math_symbols(s: str) -> str:
        for old, new in replacements.items():
            s = s.replace(old, new)
        return s

    def fix_display(m: re.Match) -> str:
        return '$$\n' + _replace_math_symbols(m.group(1)) + '\n$$'

    text = re.sub(r'\$\$\n(.*?)\n\$\$', fix_display, text, flags=re.DOTALL)

    def fix_inline(m: re.Match) -> str:
        return '$' + _replace_math_symbols(m.group(1)) + '$'

    text = re.sub(
        r'(?<!\$)\$(?!\$)([^$\n]{1,300}?)(?<!\$)\$(?!\$)',
        fix_inline,
        text,
    )

    def fix_short_context(m: re.Match) -> str:
        before = m.group(1)
        symbol = m.group(2)
        after = m.group(3)
        return before + r'\(' + replacements[symbol] + r'\)' + after

    return re.sub(
        r'([A-Za-z0-9_{}() /\-]{0,20})([∈Φγπτβ])([A-Za-z0-9_{}() /\-]{0,20})',
        fix_short_context,
        text,
    )


# ── 修复 5：常见 LaTeX OCR 别名 / 残缺命令 ─────────────────────────────────

def fix_latex_ocr_aliases(text: str) -> str:
    r"""修复保守的 LaTeX OCR 错误，如 ``\ol`` 和 ``\to \i``."""
    if not text:
        return text
    text = re.sub(r'\\begin\s+\{', r'\\begin{', text)
    text = re.sub(r'\\end\s+\{', r'\\end{', text)
    text = re.sub(r'\\ol\b', r'\\overline', text)
    text = re.sub(r'\\to\s*\\i(?![A-Za-z])', r'\\to \\infty', text)
    text = re.sub(r'\\lim_\{([^{}]*)\\to\s*\\i\s*\}', r'\\lim_{\1\\to \\infty}', text)
    text = re.sub(r'\\lim_([A-Za-z0-9]+)\\to\s*\\i(?![A-Za-z])', r'\\lim_{\1\\to \\infty}', text)
    return text


def fix_markdown_section_headings(text: str) -> str:
    """将 2.1. 小节标题转成二级 Markdown 标题。"""
    def _heading(m: re.Match) -> str:
        title = m.group(1).strip()
        rest = (m.group(2) or "").strip()
        if rest:
            return f'## {title}\n\n{rest}'
        return f'## {title}'

    return re.sub(
        r'^(?!#)(\d+\.\d+\. [A-Z][^.]{3,100}\.)(?:\s+(.+))?$',
        _heading,
        text,
        flags=re.MULTILINE,
    )


def normalize_markdown_math_delimiters(text: str) -> str:
    r"""将 Markdown 数学分隔符规范化为 \( \) 和 \[ \]。"""
    text = re.sub(
        r'\$\$\s*\n?(.*?)\n?\s*\$\$',
        lambda m: '\\[\n' + m.group(1).strip() + '\n\\]',
        text,
        flags=re.DOTALL,
    )
    return re.sub(
        r'(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)',
        lambda m: r'\(' + m.group(1).strip() + r'\)',
        text,
    )


def _fix_latex_math_blocks(text: str, fixer) -> str:
    r"""对 \( \) 和 \[ \] 内部应用 fixer。"""
    text = re.sub(
        r'\\\[(.*?)\\\]',
        lambda m: '\\[\n' + fixer(m.group(1).strip()) + '\n\\]',
        text,
        flags=re.DOTALL,
    )
    return re.sub(
        r'\\\((.*?)\\\)',
        lambda m: r'\(' + fixer(m.group(1).strip()) + r'\)',
        text,
        flags=re.DOTALL,
    )


def fix_latex_math_spacing(text: str) -> str:
    r"""压紧数学环境里的 LaTeX OCR 空格，如 \mathbb { C } 和 _ { i }。"""
    def fix_math(math: str) -> str:
        math = re.sub(r'(\\[A-Za-z]+\*?)\s+\{', r'\1{', math)
        math = re.sub(r'([_^])\s+\{', r'\1{', math)
        math = re.sub(r'\{\s+([^{}\n]{1,80}?)\s+\}', r'{\1}', math)
        math = re.sub(r'\{-\s+([^{}\s]+)\}', r'{-\1}', math)
        math = re.sub(r'\s+([,;:])', r'\1', math)
        math = re.sub(r'([([{])\s+', r'\1', math)
        math = re.sub(r'\s+([)\]}])', r'\1', math)
        math = re.sub(r'(?<=[A-Za-z0-9}])\s+(\()', r'\1', math)
        math = re.sub(r'(?<=})\s+(?=\\[A-Za-z])', '', math)
        math = re.sub(r'\s+([_^])', r'\1', math)
        math = re.sub(r'([_^])\s+', r'\1', math)
        return math

    return _fix_latex_math_blocks(text, fix_math)


_SPACED_MATH_WORDS = {
    'D e s': 'Des',
    'F l': 'Fl',
    'G L': 'GL',
    'i d': 'id',
    'm i n': 'min',
    'p t': 'pt',
    'f l a g': 'flag',
}


def fix_spaced_math_words(text: str) -> str:
    """修复数学环境内少量白名单逐字词。"""
    def fix_math(math: str) -> str:
        for spaced, compact in _SPACED_MATH_WORDS.items():
            math = re.sub(rf'(?<![A-Za-z]){re.escape(spaced)}(?![A-Za-z])', compact, math)
        return math

    return _fix_latex_math_blocks(text, fix_math)


# ── 主修复入口 ────────────────────────────────────────────────────────────────

def fix_all(text: str) -> str:
    """依序应用全部修复，返回修复后的 Markdown 文本。"""
    text = fix_precomposed_chars(text)
    text = fix_spaced_text_commands(text)
    text = fix_spaced_roman_commands(text)
    text = fix_adjacent_math_segments(text)
    text = fix_missing_arrows(text)
    text = fix_unicode_math_text_noise(text)
    text = fix_digit_sequences(text)
    text = fix_latex_ocr_aliases(text)
    text = fix_markdown_section_headings(text)
    text = normalize_markdown_math_delimiters(text)
    text = fix_latex_math_spacing(text)
    text = fix_spaced_math_words(text)
    return text


# ── Markdown 分块（供 review_paper_pages 使用）────────────────────────────────

_HEADING_RE = re.compile(r'^#{1,4}\s+\S', re.MULTILINE)


def split_markdown_into_chunks(
    text: str,
    max_chars: int = 4000,
) -> list[str]:
    """将 Markdown 文本按节标题切分成审查友好的块列表。

    优先在 `#` 标题处切割；单个 section 超过 max_chars 时进一步按段落切。
    返回非空字符串列表，保持顺序。
    """
    if not text.strip():
        return []

    # 找出所有标题位置
    positions = [m.start() for m in _HEADING_RE.finditer(text)]
    if not positions:
        return _split_by_paragraphs(text, max_chars)

    # 按标题位置切段
    sections: list[str] = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        section = text[pos:end].strip()
        if section:
            sections.append(section)

    # 前置内容（标题前）
    preamble = text[: positions[0]].strip()
    if preamble:
        sections.insert(0, preamble)

    # 超过 max_chars 的 section 进一步切割
    chunks: list[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            chunks.append(sec)
        else:
            chunks.extend(_split_by_paragraphs(sec, max_chars))

    return [c for c in chunks if c.strip()]


def _split_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """按段落（双换行）切分，超长段落强制截断。"""
    paragraphs = re.split(r'\n{2,}', text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= max_chars:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(para) <= max_chars:
                buf = para
            else:
                for i in range(0, len(para), max_chars):
                    piece = para[i: i + max_chars].strip()
                    if piece:
                        chunks.append(piece)
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks
