"""
LangGraph 节点：supervisor / dispatch / chapter_writer / retriever / assembler
"""

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langgraph.types import Send

from .config import TEMPLATES, OUTPUT_ROOT, Chapter, ChapterOutput, PipelineState, WriterInput
from .llm import call_llm
from .error_memory import build_memory_prompt, summarize_fixes, learn_from_review


# ── 工具函数 ──────────────────────────────────────────────────

def _fix_latex_envs(tex: str, md_source: str = "") -> str:
    """Repair common malformed LaTeX syntax produced by LLMs.

    Patterns fixed:
      begin{env}        missing backslash
      \\begin env       missing braces
      end{env}          missing backslash
      \\end env         missing braces
      bibitem{key}      missing backslash
      \\begin{env}}     extra closing brace
      \\end{env}}       extra closing brace
      \\begin{cor}      abbreviated env name → corollary
      \\section[x]      [] vs {} on mandatory-arg commands
      missing \\begin{document} before \\begin{abstract}/\\maketitle
    """
    # Ensure \begin{document} exists before \begin{abstract} or \maketitle
    if r'\begin{document}' not in tex:
        for marker in (r'\begin{abstract}', r'\maketitle', r'\section'):
            idx = tex.find(marker)
            if idx != -1:
                tex = tex[:idx] + r'\begin{document}' + '\n\n' + tex[idx:]
                break
    # Missing backslash on begin/end
    tex = re.sub(r'(?<!\\)\bbegin\{', r'\\begin{', tex)
    tex = re.sub(r'(?<!\\)\bend\{',   r'\\end{',   tex)
    # Missing braces: `\begin word` or `\end word`
    tex = re.sub(r'\\begin\s+([A-Za-z\*]+)', r'\\begin{\1}', tex)
    tex = re.sub(r'\\end\s+([A-Za-z\*]+)',   r'\\end{\1}',   tex)
    # Extra closing brace: \begin{env}} or \end{env}}
    tex = re.sub(r'(\\(?:begin|end)\{[A-Za-z\*]+\})\}+', r'\1', tex)
    # Token audit: keyword-specific prefix rules (bibitem, item, ...)
    tex = _audit_token_rules(tex)
    # Full env token scan: find every begin/end occurrence and ensure correct form
    _env_aliases = {
        'cor':      'corollary',
        'thm':      'theorem',
        'lem':      'lemma',
        'prop':     'proposition',
        'defn':     'definition',
        'def':      'definition',
        'rmk':      'remark',
        'rem':      'remark',
        'ex':       'example',
        'exm':      'example',
        'pf':       'proof',
        'conj':     'conjecture',
        'soln':     'solution',
        'sol':      'solution',
        'obs':      'observation',
        'nota':     'notation',
        'eq':       'equation',
        # Non-standard custom names → nearest standard env
        'maintheorem':      'theorem',
        'mainthm':          'theorem',
        'lemm':             'lemma',
        'cor-kirillov':     'corollary',
        'cor-fin':          'corollary',
        'graham-refined':   'theorem',
    }
    for alias, canonical in _env_aliases.items():
        tex = re.sub(
            r'(\\(?:begin|end)\{)' + alias + r'(\})',
            r'\g<1>' + canonical + r'\2',
            tex,
        )
    # [] vs {} confusion on mandatory-arg commands
    for cmd in ('section', 'subsection', 'subsubsection', 'chapter',
                'paragraph', 'subparagraph', 'caption', 'label', 'ref',
                'cite', 'textbf', 'textit', 'emph', 'underline',
                'footnote', 'href', 'url'):
        tex = re.sub(
            r'(\\' + cmd + r')\[([^\]]*)\](?!\{)',
            r'\1{\2}',
            tex,
        )
    # Full token scan: find every begin/end occurrence and ensure correct form
    tex = _audit_env_tokens(tex)
    # Mismatched begin/end pairs: fix \end{X} to match its \begin{Y} on the stack
    tex = _fix_mismatched_envs(tex, md_source=md_source)
    # Normalize sub/superscript spacing: _ { → _{, ^ { → ^{, _ x → _x, ^ x → ^x
    tex = re.sub(r'([_^])\s+\{', r'\1{', tex)
    tex = re.sub(r'([_^])\s+([A-Za-z0-9])', r'\1\2', tex)
    # Remove space between math commands and their opening brace: \mathbf { → \mathbf{
    _MATH_CMDS_PAT = (
        r'mathbf|mathit|mathrm|mathbb|mathfrak|mathcal|mathsf|mathtt|mathscr'
        r'|overline|underline|widehat|widetilde|hat|tilde|vec|bar|dot|ddot'
        r'|sqrt|boldsymbol|pmb'
    )
    tex = re.sub(r'(\\(?:' + _MATH_CMDS_PAT + r'))\s+\{', r'\1{', tex)
    # For math font commands, also strip spaces inside braces: \mathbf{ x } → \mathbf{x}
    # (safe because these commands take a compact identifier, never prose)
    _MATH_FONT_PAT = r'mathbf|mathit|mathrm|mathbb|mathfrak|mathcal|mathsf|mathtt|mathscr|boldsymbol|pmb'
    def _strip_font_spaces(m: re.Match) -> str:
        inner = re.sub(r'\s+', '', m.group(2))
        return m.group(1) + inner + '}'
    tex = re.sub(r'(\\(?:' + _MATH_FONT_PAT + r')\{)([^{}]*)\}', _strip_font_spaces, tex)
    return tex


# ── Label-prefix → env name mapping (most reliable signal) ──────
_LABEL_PREFIX_TO_ENV: dict[str, str] = {
    'thm': 'theorem',       'theorem': 'theorem',
    'lem': 'lemma',         'lemma': 'lemma',
    'prop': 'proposition',  'proposition': 'proposition',
    'cor': 'corollary',     'corollary': 'corollary',
    'def': 'definition',    'defn': 'definition',   'definition': 'definition',
    'rem': 'remark',        'rmk': 'remark',        'remark': 'remark',
    'ex': 'example',        'exm': 'example',       'example': 'example',
    'proof': 'proof',       'pf': 'proof',
    'conj': 'conjecture',   'conjecture': 'conjecture',
    'sol': 'solution',      'soln': 'solution',     'solution': 'solution',
    'obs': 'observation',   'observation': 'observation',
    'nota': 'notation',     'notation': 'notation',
    'claim': 'claim',       'fact': 'fact',
}

# ── Content keyword hints (checked in order; first match wins) ───
_CONTENT_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^\s*Proof[\.\:\s]|^\s*证明[\.\：\s]', re.MULTILINE), 'proof'),
    (re.compile(r'\bTheorem\b|\b定理\b',     re.IGNORECASE), 'theorem'),
    (re.compile(r'\bLemma\b|\b引理\b',       re.IGNORECASE), 'lemma'),
    (re.compile(r'\bProposition\b|\b命题\b', re.IGNORECASE), 'proposition'),
    (re.compile(r'\bCorollary\b|\b推论\b',   re.IGNORECASE), 'corollary'),
    (re.compile(r'\bDefinition\b|\b定义\b',  re.IGNORECASE), 'definition'),
    (re.compile(r'\bRemark\b|\b注记\b',      re.IGNORECASE), 'remark'),
    (re.compile(r'\bExample\b|\b例题?\b',    re.IGNORECASE), 'example'),
    (re.compile(r'\bConjecture\b|\b猜想\b',  re.IGNORECASE), 'conjecture'),
]


def _infer_env_name(content: str, md_source: str = "") -> str | None:
    """Infer the correct env name from content between \\begin and \\end.

    Priority:
    1. \\label{prefix:...} — most reliable
    2. Keyword hints in the LaTeX content
    3. If md_source provided, search for the label key there
    """
    # 1. Label prefix
    label_m = re.search(r'\\label\{([A-Za-z]+)[:\-_]', content)
    if label_m:
        prefix = label_m.group(1).lower()
        if prefix in _LABEL_PREFIX_TO_ENV:
            return _LABEL_PREFIX_TO_ENV[prefix]

    # 2. Content keywords
    for pattern, env in _CONTENT_HINTS:
        if pattern.search(content):
            return env

    # 3. Markdown fallback: find label key in md_source and check surrounding text
    if md_source and label_m:
        key = label_m.group(0).lstrip('\\label{').rstrip('}')  # full label key
        idx = md_source.find(key)
        if idx != -1:
            snippet = md_source[max(0, idx - 200): idx + 200]
            for pattern, env in _CONTENT_HINTS:
                if pattern.search(snippet):
                    return env

    return None


def _fix_mismatched_envs(tex: str, md_source: str = "") -> str:
    """Fix mismatched \\begin{X} ... \\end{Y} pairs.

    For each mismatch, determine the correct env name by:
    1. Validity: if only one of X/Y is in _VALID_ENVS, trust the valid one.
    2. Content inference: \\label prefix, then keyword hints in the body.
    3. Markdown fallback: search md_source for the label key context.
    4. Last resort: trust \\begin{X} (original behavior).

    Both \\begin and \\end positions are tracked so either side can be fixed.
    """
    begin_re = re.compile(r'\\begin\{([A-Za-z][A-Za-z0-9\-\*]*)\}')
    end_re   = re.compile(r'\\end\{([A-Za-z][A-Za-z0-9\-\*]*)\}')

    tokens: list[tuple[int, int, str, str]] = []
    for m in begin_re.finditer(tex):
        tokens.append((m.start(), m.end(), 'begin', m.group(1)))
    for m in end_re.finditer(tex):
        tokens.append((m.start(), m.end(), 'end', m.group(1)))
    tokens.sort(key=lambda t: t[0])

    # Stack stores (envname, token_start, token_end) so we can fix either side
    stack: list[tuple[str, int, int]] = []
    replacements: list[tuple[int, int, str]] = []

    for start, end, kind, envname in tokens:
        if kind == 'begin':
            stack.append((envname, start, end))
            continue

        # \end token
        if not stack:
            continue  # stray \end — leave as-is

        top_name, top_start, top_end = stack[-1]
        stack.pop()

        if top_name == envname:
            continue  # matched — nothing to do

        # Mismatch: determine correct env name
        top_valid = top_name in _VALID_ENVS
        cur_valid = envname in _VALID_ENVS
        content_between = tex[top_end:start]

        if top_valid and not cur_valid:
            correct = top_name          # \end{Y} is the typo
        elif cur_valid and not top_valid:
            correct = envname           # \begin{X} is the typo
        else:
            inferred = _infer_env_name(content_between, md_source)
            correct = inferred if inferred else top_name  # fallback: trust begin

        if top_name != correct:
            replacements.append((top_start, top_end, f'\\begin{{{correct}}}'))
        if envname != correct:
            replacements.append((start, end, f'\\end{{{correct}}}'))

    if not replacements:
        return tex

    result = list(tex)
    for s, e, new_text in sorted(replacements, key=lambda x: x[0], reverse=True):
        result[s:e] = list(new_text)
    return "".join(result)


# Valid LaTeX environment names (built-in + amsthm standard set)
_VALID_ENVS = frozenset({
    # Document structure
    'document', 'abstract', 'titlepage',
    # Sectioning content
    'verbatim', 'verbatim*', 'quote', 'quotation', 'verse',
    'center', 'flushleft', 'flushright',
    # Lists
    'itemize', 'enumerate', 'description',
    # Math
    'equation', 'equation*', 'align', 'align*', 'aligned',
    'gather', 'gather*', 'gathered', 'multline', 'multline*',
    'split', 'cases', 'array', 'matrix', 'pmatrix', 'bmatrix',
    'vmatrix', 'Vmatrix', 'Bmatrix', 'smallmatrix',
    'math', 'displaymath',
    # Floats
    'figure', 'figure*', 'table', 'table*', 'tabular', 'tabular*',
    'tabularx', 'longtable', 'minipage', 'wrapfigure',
    # Theorem-like (amsthm standard)
    'theorem', 'lemma', 'proposition', 'corollary', 'definition',
    'remark', 'example', 'proof', 'conjecture', 'claim',
    'fact', 'observation', 'notation', 'solution',
    # Bibliography
    'thebibliography',
    # Beamer
    'frame', 'block', 'alertblock', 'exampleblock', 'columns', 'column',
    # Misc
    'tikzpicture', 'scope', 'pgfpicture',
})

# Aliases that map to a valid canonical name
_ENV_ALIASES = {
    'cor':           'corollary',
    'thm':           'theorem',
    'lem':           'lemma',
    'prop':          'proposition',
    'defn':          'definition',
    'def':           'definition',
    'rmk':           'remark',
    'rem':           'remark',
    'ex':            'example',
    'exm':           'example',
    'pf':            'proof',
    'conj':          'conjecture',
    'soln':          'solution',
    'sol':           'solution',
    'obs':           'observation',
    'nota':          'notation',
    'eq':            'equation',
    'maintheorem':   'theorem',
    'mainthm':       'theorem',
    'lemm':          'lemma',
    'cor-kirillov':  'corollary',
    'cor-fin':       'corollary',
    'graham-refined':'theorem',
}


def _audit_env_tokens(tex: str) -> str:
    """Scan every occurrence of the word 'begin' and 'end' in the source.

    For each token, verify it forms a valid \\begin{envname} / \\end{envname}.
    Repairs applied in a single pass over the character stream:
      - bare begin{...}  → \\begin{...}
      - \\begin envname  → \\begin{envname}
      - \\begin{alias}   → \\begin{canonical}
      - unknown envname  → kept as-is (may be user-defined; don't break it)
    """
    # Pattern: optional backslash, word begin/end, then either {envname} or space+envname
    token_re = re.compile(
        r'(\\?)(?<!\w)(begin|end)(?!\w)'   # optional \ + keyword
        r'(\s*\{([A-Za-z][A-Za-z0-9\-\*]*)\}|\s+([A-Za-z][A-Za-z0-9\-\*]*))',
        re.IGNORECASE,
    )

    def _replace(m: re.Match) -> str:
        backslash = m.group(1)          # '' or '\\'
        keyword   = m.group(2).lower()  # 'begin' or 'end'
        # group 4: envname from {envname} form; group 5: from bare-word form
        envname = (m.group(4) or m.group(5) or '').strip()

        # Resolve alias
        canonical = _ENV_ALIASES.get(envname, envname)

        return f'\\{keyword}{{{canonical}}}'

    return token_re.sub(_replace, tex)


# ── Backslash-required command scan ──────────────────────────────
# Commands that must always appear as \cmd{...} — never bare.
# Add a word here to include it in the full-scan pass; no other code changes needed.
_BACKSLASH_CMDS: frozenset[str] = frozenset({
    'bibitem',   # \bibitem{key}
    'label',     # \label{key}
    'ref',       # \ref{key}
    'cite',      # \cite{key}
    'item',      # \item
})

# Pre-compiled: longest keywords first to avoid partial matches (e.g. 'bibitem' before 'item')
_BACKSLASH_CMD_RE = re.compile(
    r'(?<!\\)(?<!\w)(' +
    '|'.join(re.escape(c) for c in sorted(_BACKSLASH_CMDS, key=len, reverse=True)) +
    r')(?!\w)',
)


def _audit_token_rules(tex: str) -> str:
    """Single-pass scan: ensure every command in _BACKSLASH_CMDS is preceded by \\."""
    return _BACKSLASH_CMD_RE.sub(r'\\\1', tex)


_LATEX_REVIEW_CHECKLIST = (
    "检查项目：\n"
    r"□ 【内容完整性】LaTeX 输出是否包含原始 Markdown 的全部内容？" "\n"
    r"  - 所有段落、定理、例题、公式、列表、参考文献均须保留，不得删减或合并" "\n"
    r"  - 禁止用省略号（...）或注释（% omitted）代替原文内容" "\n"
    r"□ 数学公式是否都正确用 $...$ 或 \[...\] 包裹？" "\n"
    r"□ 定理/定义/引理等是否用了完整的 LaTeX 环境名（严禁缩写）？" "\n"
    r"  禁止缩写：thm, lem, prop, cor, defn, def, rmk, rem, pf, ex, exm, conj, soln, sol" "\n"
    r"  必须完整：theorem, lemma, proposition, corollary, definition," "\n"
    r"  remark, example, proof, solution, conjecture, equation, align," "\n"
    r"  itemize, enumerate, figure, table, abstract, thebibliography" "\n"
    r"□ 【反斜杠】所有环境/命令是否有反斜杠？" "\n"
    r"  错误：begin{theorem}  正确：\begin{theorem}" "\n"
    r"  错误：end{proof}      正确：\end{proof}" "\n"
    r"  错误：bibitem{key}    正确：\bibitem{key}" "\n"
    r"□ 【花括号】\begin/\end 后是否有花括号？" "\n"
    r"  错误：\begin theorem  正确：\begin{theorem}" "\n"
    r"□ 【[] vs {}】以下命令的必选参数必须用 {}，不能用 []：" "\n"
    r"  \section{标题}  \caption{说明}  \label{key}  \cite{key}" "\n"
    r"  \textbf{文字}   \emph{文字}     \footnote{注}" "\n"
    r"  可选参数才用 []，如 \section[短标题]{长标题}" "\n"
    r"□ 是否有裸露的特殊字符（&, %, #, _ 等）未被转义？" "\n"
    r"□ 参考文献条目是否写成 \bibitem{key}？" "\n"
)


# ── 合并审查 Agent ────────────────────────────────────────────────
# Single agent covering syntax + math + citations in one LLM call.

_REVIEW_SYSTEM = (
    "你是 LaTeX 全面修复专家。一次性修正以下所有问题，不改变任何实质内容：\n"
    "\n【语法】\n"
    "1. \\begin{env}/\\end{env} 缺反斜杠 → 补上\n"
    "2. \\begin env（缺花括号）→ 改为 \\begin{env}\n"
    "3. 环境名缩写 → 完整名：thm→theorem, lem→lemma, cor→corollary, "
    "prop→proposition, defn/def→definition, rmk/rem→remark, "
    "pf→proof, ex/exm→example, conj→conjecture, soln/sol→solution\n"
    "4. \\section[x] 等必选参数误用 [] → 改为 {}\n"
    "5. bibitem/label/ref/cite/item 缺反斜杠 → 补上\n"
    "\n【数学】\n"
    "6. 裸露数学符号（x^2, \\alpha, \\sum 等）→ 用 $...$ 包裹\n"
    "7. 行间公式 $$...$$ → 改为 \\[...\\] 或 equation 环境\n"
    "8. 正文特殊字符 % # & _ ^ ~ 未转义 → 补反斜杠（数学环境内除外）\n"
    "\n【引用】\n"
    "9. \\cite{key} 无对应 \\bibitem{key} → 补充 \\bibitem\n"
    "10. \\ref{key} 无对应 \\label{key} → 补充 \\label 或改为文字\n"
    "11. 禁止新增 \\newtheorem 或 \\theoremstyle，未定义环境名改写为标准名\n"
    "\n【begin/end 配对】\n"
    "12. \\begin{X} 必须与 \\end{X} 配对，环境名完全一致 → 不一致时修正 \\end 的环境名\n"
    "    例：\\begin{lemma}...\\end{remark} → \\begin{lemma}...\\end{lemma}\n"
    "    例：\\begin{theorem}...\\end{proof} → \\begin{theorem}...\\end{theorem}\n"
    "\n只输出修正后的完整 LaTeX 片段，不要任何说明文字。"
)

_REVIEW_USER_TMPL = (
    "请一次性修正以下 LaTeX 片段中的所有问题（语法/数学/引用）：\n\n"
    "{body}\n\n只输出修正后的完整片段。"
)


# ── 条件触发：只有检测到可疑模式才调 LLM ────────────────────────

_REVIEW_TRIGGERS = [
    re.compile(r'(?<!\\)\b(begin|end)\{',          re.IGNORECASE),  # 裸露 begin/end
    re.compile(r'\$\$'),                                              # $$ 用法
    re.compile(r'(?<!\\)\b(bibitem|label|ref|cite|item)\b'),         # 缺反斜杠关键字
    re.compile(r'(?<!\\)\b(alpha|beta|gamma|delta|theta|lambda|mu|nu|xi|pi|sigma|tau|phi|psi|omega'
               r'|sum|int|prod|frac|sqrt|infty|partial|nabla|forall|exists)\b'),  # 裸露数学符号
    re.compile(r'(?<!\$)(?<!\{)(?<!\\)[_^](?!\{)'),                 # 裸露 _ ^
]

def _has_env_mismatch(tex: str) -> bool:
    """Return True if any \\begin{X}/\\end{Y} pair has mismatched env names."""
    begin_re = re.compile(r'\\begin\{([A-Za-z][A-Za-z0-9\-\*]*)\}')
    end_re   = re.compile(r'\\end\{([A-Za-z][A-Za-z0-9\-\*]*)\}')
    tokens = []
    for m in begin_re.finditer(tex):
        tokens.append((m.start(), 'begin', m.group(1)))
    for m in end_re.finditer(tex):
        tokens.append((m.start(), 'end', m.group(1)))
    tokens.sort(key=lambda t: t[0])
    stack: list[str] = []
    for _, kind, name in tokens:
        if kind == 'begin':
            stack.append(name)
        elif stack:
            if stack[-1] != name:
                return True
            stack.pop()
    return False

def _needs_review(tex: str) -> bool:
    """Return True if any suspicious pattern is found that warrants LLM review."""
    for pattern in _REVIEW_TRIGGERS:
        if pattern.search(tex):
            return True
    return _has_env_mismatch(tex)


def _review_latex(model_name: str, style_hint: str, latex_body: str,
                  extra_checks: str = "") -> str:
    """Single-pass review: skip if clean, one LLM call if issues detected."""
    if not _needs_review(latex_body):
        print("    [Review] 无可疑模式，跳过 LLM 审查", flush=True)
        return latex_body

    print("    [Review] 检测到可疑模式，启动审查...", flush=True)
    user = _REVIEW_USER_TMPL.replace("{body}", latex_body)
    if extra_checks:
        user += f"\n\n额外检查项：\n{extra_checks}"
    result = call_llm(model_name, _REVIEW_SYSTEM, user, temperature=0.1, show_thinking=True)
    result = re.sub(r'^```(?:latex)?\s*\n', '', result.strip(), flags=re.MULTILINE)
    result = re.sub(r'\n```\s*$', '', result.strip())
    if result:
        body = _fix_latex_envs(result)
        print("    [Review] 完成", flush=True)
        return body
    return latex_body



def _extract_json(raw: str):
    start = raw.find('{')
    if start == -1:
        return None
    for end in range(len(raw), start, -1):
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            continue
    return None

def _detect_doc_type(full_text: str, matches) -> str:
    """Classify the document as 'book' or 'paper'.

    Book signals: any heading title or body prose contains the word 'chapter'.
    Paper signals: presence of Abstract / References / Bibliography sections,
    or short document with few top-level headings.
    """
    text_lower = full_text.lower()

    # Strong book signal: "chapter" appears in a heading title
    for m in matches:
        if 'chapter' in m.group(2).lower():
            return "book"

    # Strong book signal: "chapter" in body prose (direct body under any heading)
    for i, m in enumerate(matches):
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        direct_body = full_text[m.end():content_end].lower()
        if re.search(r'\bchapter\b', direct_body):
            return "book"

    # Strong paper signal: has Abstract or References section
    if re.search(r'^#{1,3}\s+(abstract|references|bibliography|acknowledgements?)\s*$',
                 full_text, re.MULTILINE | re.IGNORECASE):
        return "paper"

    # Heuristic: short document with ≤12 top-level sections → paper
    total_lines = full_text.count('\n')
    top_headings = sum(1 for m in matches if len(m.group(1)) <= 2)
    if total_lines < 1500 and top_headings <= 12:
        return "paper"

    return "book"



def _detect_chapter_level(matches, full_text: str) -> int:
    """Return the heading level that represents top-level chapters.

    Searches the direct body text under each heading (up to the next heading
    of any level) for the word 'chapter'. Returns the shallowest level where
    that keyword appears in prose, skipping a lone level-1 document title.
    Falls back to the shallowest non-title level when no keyword is found.
    """
    levels = [len(m.group(1)) for m in matches]
    lone_h1 = levels.count(1) == 1

    for i, m in enumerate(matches):
        level = len(m.group(1))
        if level == 1 and lone_h1:
            continue
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else content_start + 400
        direct_body = full_text[content_start:content_end].lower()
        if re.search(r'\bchapter\b', direct_body):
            return level

    min_level = min(levels)
    if lone_h1 and min_level == 1:
        rest = [l for l in levels if l > 1]
        return min(rest) if rest else 1
    return min_level


# ── 关键词隐式标题检测 ────────────────────────────────────────

_LATEX_ENV_RULES = (
    "\n【内容完整性（最高优先级）】\n"
    "- 必须将原始 Markdown 的全部内容转换为 LaTeX，一字不漏\n"
    "- 所有段落、定理、例题、公式、列表、脚注、参考文献均须保留\n"
    "- 严禁用省略号（...）、注释（% omitted / % 略）或任何方式跳过原文内容\n"
    "- 如果内容很长，必须继续输出直到全部完成，不得截断\n"
    "\n【LaTeX 环境语法（严格执行）】\n"
    r"- 所有环境必须写成 \begin{环境名} ... \end{环境名}" "\n"
    r"- 反斜杠 \ 和花括号 {} 缺一不可" "\n"
    r"- 禁止写成 begin{theorem}（缺反斜杠）" "\n"
    r"- 禁止写成 \begin theorem（缺花括号）" "\n"
    r"- 正确示例：\begin{theorem} ... \end{theorem}" "\n"
    "- 环境名必须使用完整拼写，严禁使用缩写：\n"
    r"    禁止：thm, lem, prop, cor, defn, def, rmk, rem, pf, ex, exm, conj, soln, sol, obs, nota, eq" "\n"
    r"    必须：theorem, lemma, proposition, corollary, definition, remark, example," "\n"
    r"    proof, solution, conjecture, notation, claim, fact, observation," "\n"
    r"    equation, align, gather, itemize, enumerate, figure, table, tabular," "\n"
    r"    abstract, thebibliography" "\n"
    "\n【数学公式（严格执行）】\n"
    r"- 所有数学符号、变量、公式必须在数学环境内：行内用 $...$，行间用 \[...\] 或 equation/align 环境" "\n"
    r"- 禁止裸露的数学符号，例如：x^2、\alpha、\sum 必须写成 $x^2$、$\alpha$、$\sum$" "\n"
    r"- 行间公式禁止使用 $$...$$，改用 \[...\] 或 \begin{equation}...\end{equation}" "\n"
    r"- 正文中的特殊字符 % # & _ ^ ~ 必须转义（数学环境内除外）：\% \# \& \_ \^ \~" "\n"
    "\n【引用与标签（严格执行）】\n"
    r"- 参考文献条目必须写成 \bibitem{key}，禁止写成 bibitem{key}（缺反斜杠）" "\n"
    r"- 每个 \cite{key} 必须在 thebibliography 中有对应的 \bibitem{key}" "\n"
    r"- 每个 \ref{key} 必须有对应的 \label{key}" "\n"
    r"- \label、\ref、\cite 均须有反斜杠前缀" "\n"
    "\n【begin/end 配对（严格执行）】\n"
    r"- \begin{X} 必须与 \end{X} 配对，环境名必须完全一致" "\n"
    r"- 禁止 \begin{lemma}...\end{remark}、\begin{theorem}...\end{proof} 等错误配对" "\n"
    r"- 每个 \begin{X} 必须有且仅有一个对应的 \end{X}，不得多余也不得缺失" "\n"
    r"- 正确示例：\begin{lemma} ... \end{lemma}，\begin{remark} ... \end{remark}" "\n"
    "\n【禁止新增 \\newtheorem】\n"
    "- 严禁在输出中新增任何 \\newtheorem 或 \\theoremstyle 定义\n"
    "- 若遇到非标准环境名（如 maintheorem、lemm、cor-kirillov），直接改写为对应标准名\n"
)

# 匹配 "Chapter 1", "Section 2.3", "Part I", "1. Introduction" 等
_KEYWORD_HEADING = re.compile(
    r'^(?:'
    r'(?P<kw>chapter|section|part|subsection|subsubsection|appendix)'  # keyword-led
    r'[\s\.\-–—]*(?P<num>[\dIVXivx]+(?:[\.\-]\d+)*)?'
    r'[\s\.\-–—:：]*(?P<rest>.+)?'
    r'|(?P<num2>\d+(?:\.\d+)*)[\s\.\-–—:：]+(?P<rest2>[A-Z一-鿿].{2,})'  # numbered
    r')$',
    re.IGNORECASE,
)

def _find_implicit_headings(lines: list[str]) -> list[dict]:
    """Detect headings that lack # markers but look structural by keyword/context."""
    results = []
    n = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        m = _KEYWORD_HEADING.match(stripped)
        if not m:
            continue
        # Context check: preceded or followed by blank line (or start/end of file)
        prev_blank = (i == 0) or (lines[i - 1].strip() == "")
        next_blank = (i == n - 1) or (lines[i + 1].strip() == "")
        if not (prev_blank or next_blank):
            continue
        # Infer level from keyword
        kw = (m.group("kw") or "").lower()
        level_map = {"part": 1, "chapter": 2, "section": 3,
                     "subsection": 4, "subsubsection": 5, "appendix": 2}
        level = level_map.get(kw, 3)  # numbered headings default to section
        results.append({"line_no": i + 1, "title": stripped, "level": level})
    return results


def classifier_node(state: PipelineState) -> dict:
    """Step 1b: LLM 判断文档类型 book vs paper，写入 doc_type。"""
    print(f"\n[Step 1b] Classifier 判断文档类型")
    md_path = Path(state["markdown_path"])
    full_text = md_path.read_text(encoding="utf-8")

    # 取前 3000 字符作为样本，足够判断类型
    sample = full_text[:3000]

    system = """你是文档类型分类专家。
根据给定的 Markdown 文本片段，判断原始文档是「书籍/教材（book）」还是「学术论文/文章（paper）」。

判断依据：
- book：有多个章节（Chapter/Part），内容较长，结构层次深，通常无 Abstract/References 节
- paper：有 Abstract、Introduction、Conclusion、References 等标准论文节，篇幅较短

只输出一个单词：book 或 paper，不要任何解释。"""

    user = f"文档片段：\n\n{sample}"

    result = call_llm(state["model_name"], system, user, temperature=0.0, show_thinking=False)
    doc_type = "paper" if "paper" in result.lower() else "book"
    print(f"  文档类型: {doc_type}")

    pdf_stem = Path(state["pdf_path"]).stem
    output_dir = OUTPUT_ROOT / pdf_stem
    output_dir.mkdir(parents=True, exist_ok=True)

    return {"doc_type": doc_type, "output_dir": str(output_dir)}


def route_by_doc_type(state: PipelineState) -> str:
    return "supervisor" if state["doc_type"] == "book" else "paper_writer"


def paper_writer_node(state: PipelineState) -> dict:
    """Paper 路径：直接将整篇 Markdown 转为完整 main.tex，不拆章节。"""
    print(f"\n[Paper] 直接转换整篇论文")
    tpl = TEMPLATES[state["template_name"]]
    md_path = Path(state["markdown_path"])
    full_text = md_path.read_text(encoding="utf-8")
    output_dir = Path(state["output_dir"])

    title_match = re.search(r'^#\s+(.+)$', full_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem

    system = (
        f"你是专业的 LaTeX 排版助手。\n"
        f"将给定的学术论文 Markdown 内容转换为完整的 LaTeX 正文"
        r"（\begin{document} 到 \end{document} 之间的部分，不含 \documentclass）。"
        f"\n\n【模板风格要求】\n{tpl['style_hint']}\n\n"
        f"【输出规则】\n"
        r"- 只输出 \maketitle 之后到 \end{document} 之前的正文内容" "\n"
        f"- 数学公式用 $...$  或 \\[...\\] 包裹\n"
        f"- 保留 Abstract、Introduction、Conclusion、References 等标准节结构\n"
        r"- 参考文献用 \begin{thebibliography} 环境或直接列出" "\n"
        f"- 【严禁删减】原始 Markdown 的每一段、每一个定理/例题/公式/参考文献都必须出现在输出中，不得省略\n"
        + _LATEX_ENV_RULES
        + build_memory_prompt()
    )
    user = f"请将以下论文内容转换为 LaTeX 正文片段：\n\n{full_text}"

    latex_body = call_llm(state["model_name"], system, user, temperature=0.2)
    latex_body = re.sub(r'<think>.*?</think>', '', latex_body, flags=re.DOTALL)
    latex_body = re.sub(r'&lt;/?think&gt;', '', latex_body, flags=re.IGNORECASE)
    latex_body = _fix_latex_envs(latex_body, md_source=full_text)

    print(f"  [Paper] 格式审查...")
    original_before_review = latex_body
    latex_body = _review_latex(state["model_name"], tpl["style_hint"], latex_body)
    learn_from_review(original_before_review, latex_body, state["model_name"])

    preamble = tpl["preamble"].replace("__TITLE__", title)
    document = tpl["body_wrapper"].replace("__BODY__", latex_body)
    final = preamble + document

    main_path = output_dir / "main.tex"
    main_path.write_text(final, encoding="utf-8")
    print(f"  ✓ main.tex ({len(final)} 字符)")

    return {"doc_title": title, "final_latex": str(main_path)}


def supervisor_node(state: PipelineState) -> dict:
    print(f"\n[Step 2] Supervisor 分析文档结构")

    md_path = Path(state["markdown_path"])
    full_text = md_path.read_text(encoding="utf-8")
    lines = full_text.splitlines()
    total_lines = len(lines)
    print(f"  Markdown 总行数: {total_lines}")

    # ── 路径 A: Markdown # 标题 ──────────────────────────────
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    md_matches = list(heading_pattern.finditer(full_text))

    # ── 路径 B: 关键词隐式标题 ───────────────────────────────
    implicit = _find_implicit_headings(lines)

    # 已被路径 A 覆盖的行号集合（避免重复）
    md_line_nos = set()
    for m in md_matches:
        ln = full_text[:m.start()].count('\n') + 1
        md_line_nos.add(ln)

    # ── 合并：构建统一的 heading 列表 ────────────────────────
    # 每条记录: (line_no, title, level)
    all_headings: list[tuple[int, str, int]] = []

    for m in md_matches:
        ln = full_text[:m.start()].count('\n') + 1
        all_headings.append((ln, m.group(2).strip(), len(m.group(1))))

    for imp in implicit:
        if imp["line_no"] not in md_line_nos:
            all_headings.append((imp["line_no"], imp["title"], imp["level"]))
            print(f"  [隐式标题] 行 {imp['line_no']}: {imp['title']}")

    all_headings.sort(key=lambda x: x[0])

    # ── 文档类型 & 输出目录 ──────────────────────────────────
    doc_type = _detect_doc_type(full_text, md_matches)
    pdf_stem = Path(state["pdf_path"]).stem
    output_dir = OUTPUT_ROOT / pdf_stem
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  文档类型: {doc_type}")
    print(f"  输出目录: {output_dir}")

    # ── 文档标题（第一个 H1，或文件名）───────────────────────
    title_match = re.search(r'^#\s+(.+)$', full_text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem

    # ── 构建 Chapter 列表 ────────────────────────────────────
    chapters = []
    for i, (ln, ch_title, level) in enumerate(all_headings):
        # 跳过孤立的 H1 文档标题（第一个且唯一的 H1）
        if level == 1 and i == 0 and sum(1 for _, _, l in all_headings if l == 1) == 1:
            continue
        line_end = all_headings[i + 1][0] - 1 if i + 1 < len(all_headings) else total_lines
        chapters.append(Chapter(
            index=len(chapters) + 1,
            title=ch_title,
            level=level,
            line_start=ln,
            line_end=line_end,
        ))

    if not chapters:
        chapters.append(Chapter(index=1, title=title, level=1,
                                line_start=1, line_end=total_lines))

    print(f"  文档标题: {title}")
    print(f"  识别章节: {len(chapters)} 个")
    for c in chapters:
        print(f"    [{c['index']}] (H{c['level']}) {c['title']} (行 {c['line_start']}-{c['line_end']})")

    return {"doc_title": title, "doc_type": doc_type,
            "output_dir": str(output_dir), "chapters": chapters}



# ── Step 3: 并行分发 ──────────────────────────────────────────

def dispatch_chapters(state: PipelineState):
    print(f"\n[Step 3] 并行分发 {len(state['chapters'])} 个 Sub-Agent")
    return [
        Send("chapter_writer", {
            "chapter":       ch,
            "markdown_path": state["markdown_path"],
            "all_titles":    [c["title"] for c in state["chapters"]],
            "template_name": state["template_name"],
            "model_name":    state["model_name"],
            "doc_type":      state["doc_type"],
            "output_dir":    state["output_dir"],
        })
        for ch in state["chapters"]
    ]


# ── Step 3a: Chapter Writer ───────────────────────────────────

def chapter_writer_node(state: WriterInput) -> dict:
    ch = state["chapter"]
    tpl = TEMPLATES[state["template_name"]]
    level = ch.get("level", 2)
    level_cmd = {1: r"\chapter", 2: r"\section", 3: r"\subsection",
                 4: r"\subsubsection", 5: r"\paragraph", 6: r"\subparagraph"}.get(level, r"\section")
    print(f"  [Sub-Agent #{ch['index']}] 写作: {ch['title']} (H{level}, 行 {ch['line_start']}-{ch['line_end']})")

    lines = Path(state["markdown_path"]).read_text(encoding="utf-8").splitlines()
    content = "\n".join(lines[ch["line_start"] - 1 : ch["line_end"]])
    print(f"    内容长度: {len(content)} 字符")

    system = (
        f"你是专业的 LaTeX 排版助手。\n"
        f"将给定的章节内容转换为标准 LaTeX 格式的正文片段。\n\n"
        f"【模板风格要求】\n{tpl['style_hint']}\n\n"
        f"【输出规则】\n"
        f"- 只输出 LaTeX 正文片段（从 {level_cmd} 开始，不含 \\documentclass）\n"
        f"- 该章节标题级别为 H{level}，对应 LaTeX 命令 {level_cmd}，子标题依此类推\n"
        f"- 数学公式务必用 $...$ 或 \\[...\\] 包裹\n"
        f"- 保留原文的定理、定义、例题等结构\n"
        f"- 末尾加注释 % === END CHAPTER {ch['index']} ===\n"
        f"- 【严禁删减】原始内容的每一段、每一个定理/例题/公式都必须出现在输出中，不得省略\n"
        + _LATEX_ENV_RULES
        + build_memory_prompt()
    )
    user = f"""请将以下内容（第 {ch['index']} 章：{ch['title']}）转换为 LaTeX 正文片段。
全书章节（供上下文参考）：{', '.join(state['all_titles'])}

原始内容：
{content}"""

    latex_body = call_llm(state["model_name"], system, user, temperature=0.2)
    latex_body = re.sub(r'<think>.*?</think>', '', latex_body, flags=re.DOTALL)
    latex_body = re.sub(r'&lt;/?think&gt;', '', latex_body, flags=re.IGNORECASE)
    latex_body = _fix_latex_envs(latex_body, md_source=content)

    output_dir = Path(state["output_dir"])
    sub_path = output_dir / f"chapter-{ch['index']}.tex"
    sub_path.write_text(latex_body, encoding="utf-8")

    return {"chapter_outputs": [{"index": ch["index"], "title": ch["title"],
                                  "latex_body": latex_body}]}


# ── Step 4: Retriever ─────────────────────────────────────────

def retriever_node(state: PipelineState) -> dict:
    chapters = sorted(state["chapter_outputs"], key=lambda x: x["index"])
    print(f"\n[Step 4] Retriever 并行审查 {len(chapters)} 个章节", flush=True)
    tpl = TEMPLATES[state["template_name"]]
    model_name = state["model_name"]
    output_dir = Path(state["output_dir"])
    reviewed_map: dict[int, dict] = {}

    def _review_chapter(ch: dict) -> dict:
        print(f"  [#{ch['index']}] 开始审查: {ch['title']}", flush=True)
        extra = (
            f"□ 章节层级是否用了 \\section / \\subsection？\n"
            f"□ 末尾是否有 % === END CHAPTER {ch['index']} ===？\n"
        )
        reviewed_body = _review_latex(model_name, tpl["style_hint"], ch["latex_body"],
                                      extra_checks=extra)
        learn_from_review(ch["latex_body"], reviewed_body, model_name)
        sub_path = output_dir / f"chapter-{ch['index']}-reviewed.tex"
        sub_path.write_text(reviewed_body, encoding="utf-8")
        print(f"  [#{ch['index']}] 审查完成: {ch['title']}", flush=True)
        return {**ch, "latex_body": reviewed_body}

    max_workers = min(len(chapters), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_review_chapter, ch): ch["index"] for ch in chapters}
        for fut in as_completed(futures):
            result = fut.result()
            reviewed_map[result["index"]] = result

    reviewed = [reviewed_map[ch["index"]] for ch in chapters]
    return {"reviewed_outputs": reviewed}


from .cite_tool import search_crossref, search_arxiv, format_bibitem, extract_citations, extract_bibitems


# ── Step 4b: Reference Manager ────────────────────────────────

def ref_manager_node(state: PipelineState) -> dict:
    print(f"\n[Step 4b] Reference Manager 自动补全参考文献")
    output_dir = Path(state["output_dir"])
    
    # 汇总所有章节的 LaTeX
    combined_latex = ""
    for ch in state["chapter_outputs"]:
        combined_latex += ch["latex_body"] + "\n"
    
    # 1. 提取所有 \cite 过的 keys
    cite_keys = extract_citations(combined_latex)
    # 2. 提取已有的 \bibitem
    existing_bibs = extract_bibitems(combined_latex)
    
    all_keys = sorted(list(set(cite_keys) | set(existing_bibs.keys())))
    print(f"  识别到 {len(all_keys)} 条文献引用")
    
    final_bibitems = []
    for key in all_keys:
        # 如果已经有详细信息（非空），先尝试用已有信息
        info = existing_bibs.get(key, "").strip()
        
        # 逻辑：如果信息少于 10 个字符，认为是缺失信息，去联网找
        if len(info) < 10:
            print(f"    检索 {key} ...", end="", flush=True)
            # 改进查询构造：尝试将 CamelCase 或 紧凑格式 拆分开
            # 比如 GaoXiong2025 -> Gao Xiong 2025
            query = re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
            query = re.sub(r'([A-Za-z])([0-9])', r'\1 \2', query)
            query = re.sub(r'([0-9])([A-Z])', r'\1 \2', query)
            query = query.replace("-", " ").replace("_", " ")
            
            # 第一步：搜 CrossRef
            res = search_crossref(query)
            # 第二步：如果 CrossRef 没结果，搜 arXiv
            if not res:
                res = search_arxiv(query)
                
            if res:
                formatted = format_bibitem(key, res)
                final_bibitems.append(formatted)
                source = "CrossRef" if "doi" in formatted.lower() else "arXiv"
                print(f" [✓ {source}]")
            else:
                final_bibitems.append(f"\\bibitem{{{key}}} {info if info else 'TODO: Missing reference data'}")
                print(" [✗ 未找到]")
        else:
            final_bibitems.append(f"\\bibitem{{{key}}} {info}")

    # 生成 bib.tex
    bib_content = "\\begin{thebibliography}{99}\n"
    bib_content += "\n".join(final_bibitems)
    bib_content += "\n\\end{thebibliography}"
    
    bib_path = output_dir / "bib.tex"
    bib_path.write_text(bib_content, encoding="utf-8")
    print(f"  ✓ 生成 {bib_path.name}")
    
    return {}


# ── Step 5: Assembler ─────────────────────────────────────────

def assembler_node(state: PipelineState) -> dict:
    print(f"\n[Step 5] 拼接 main.tex (模板: {state['template_name']})")
    tpl = TEMPLATES[state["template_name"]]
    output_dir = Path(state["output_dir"])
    doc_type = state.get("doc_type", "book")

    sorted_ch = sorted(state["reviewed_outputs"], key=lambda x: x["index"])

    body_parts = []
    for ch in sorted_ch:
        body_parts.append(f"\n% ===== 第 {ch['index']} 章: {ch['title']} =====\n")
        body_parts.append(ch["latex_body"])
        body_parts.append("\n")
    full_body = "\n".join(body_parts)
    
    # 如果有 bib.tex，在 body 结尾包含它
    bib_path = output_dir / "bib.tex"
    if bib_path.exists():
        full_body += "\n\\input{bib}\n"

    preamble = tpl["preamble"].replace("__TITLE__", state["doc_title"])
    document = tpl["body_wrapper"].replace("__BODY__", full_body)
    final = preamble + document

    main_path = output_dir / "main.tex"
    main_path.write_text(final, encoding="utf-8")
    print(f"  ✓ main.tex ({len(final)} 字符)")
    print(f"  ✓ 包含 {len(sorted_ch)} 个章节")

    if doc_type == "book":
        input_lines = []
        for ch in sorted_ch:
            input_lines.append(f"\\input{{chapter-{ch['index']}-reviewed}}")
        modular_body = "\n".join(input_lines)
        modular_document = tpl["body_wrapper"].replace("__BODY__", modular_body)
        modular_final = preamble + modular_document
        (output_dir / "main_modular.tex").write_text(modular_final, encoding="utf-8")
        print(f"  ✓ main_modular.tex (\\input 版本)")

    return {"final_latex": str(main_path)}


# ── Step 6: Compiler（xelatex 循环修复）────────────────────────

_MAX_COMPILE_ROUNDS = 50

def _run_xelatex(tex_path: Path) -> tuple[int, str]:
    """Run xelatex once (non-stop), return (returncode, log_text)."""
    result = subprocess.run(
        ["xelatex", "-interaction=nonstopmode", "-halt-on-error=0",
         tex_path.name],
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    log_path = tex_path.with_suffix(".log")
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else result.stdout
    return result.returncode, log_text


def _parse_errors(log_text: str) -> list[dict]:
    """Extract errors and unresolved references from xelatex log.

    Returns list of {line_no, message} dicts, deduplicated.
    Captures:
      - Hard errors:  ./main.tex:42: Undefined control sequence.
      - Bare ! errors without line numbers
      - Undefined citations: Citation `key' on page N undefined
      - Undefined labels:    Reference `key' on page N undefined
    """
    errors = []
    seen = set()

    # Hard errors with file:line: prefix
    for m in re.finditer(r'(?:\./)?\S+\.tex:(\d+):\s*(.+)', log_text):
        ln, msg = int(m.group(1)), m.group(2).strip()
        key = (ln, msg[:60])
        if key not in seen:
            seen.add(key)
            errors.append({"line_no": ln, "message": msg})

    # Bare "! Error" lines without line numbers
    for m in re.finditer(r'^!\s+(.+)$', log_text, re.MULTILINE):
        msg = m.group(1).strip()
        key = (0, msg[:60])
        if key not in seen:
            seen.add(key)
            errors.append({"line_no": 0, "message": msg})

    # Undefined citations: Citation `key' on page N undefined
    for m in re.finditer(r"Citation `([^']+)' on page \d+ undefined", log_text):
        msg = f"Undefined citation: \\cite{{{m.group(1)}}}"
        key = (0, msg[:60])
        if key not in seen:
            seen.add(key)
            errors.append({"line_no": 0, "message": msg})

    # Undefined labels/refs: Reference `key' on page N undefined
    for m in re.finditer(r"Reference `([^']+)' on page \d+ undefined", log_text):
        msg = f"Undefined reference: \\ref{{{m.group(1)}}}"
        key = (0, msg[:60])
        if key not in seen:
            seen.add(key)
            errors.append({"line_no": 0, "message": msg})

    return errors[:30]  # cap to avoid overwhelming LLM


def _build_error_context(tex_lines: list[str], errors: list[dict], window: int = 5) -> str:
    """Build a compact error report with surrounding source lines."""
    parts = []
    for err in errors:
        ln = err["line_no"]
        parts.append(f"错误（行 {ln}）：{err['message']}")
        if ln > 0:
            start = max(0, ln - window - 1)
            end = min(len(tex_lines), ln + window)
            snippet = "\n".join(
                f"  {'>>>' if i + 1 == ln else '   '} {i + 1:4d}: {tex_lines[i]}"
                for i in range(start, end)
            )
            parts.append(snippet)
        parts.append("")
    return "\n".join(parts)


def _fix_with_llm(model_name: str, tex: str, error_report: str) -> str:
    """Ask LLM to fix the LaTeX source given the error report."""
    system = (
        "你是 LaTeX 编译错误修复专家。根据 xelatex 编译报错，直接修正 LaTeX 源码。\n"
        "【输出格式严格要求】\n"
        "- 只输出修正后的完整 LaTeX 文件，从 \\documentclass 开始，到 \\end{document} 结束\n"
        "- 禁止在 LaTeX 代码前后输出任何分析、说明、总结或 Markdown 文字\n"
        "- 禁止输出代码块标记（```latex 等）\n"
        "- 第一行必须是 \\documentclass，最后一行必须是 \\end{document}\n"
        "只修复报错相关的问题，不改变文档内容和结构。\n"
        r"特别注意：\begin{env}/\end{env} 反斜杠和花括号缺一不可；"
        "环境名必须完整拼写（theorem/lemma/proof 等，禁止缩写）；"
        r"\section{} 等命令的必选参数用 {}，可选参数才用 []；"
        "未定义的 \\cite{key} 需在 thebibliography 中补充对应 \\bibitem{key}；"
        "未定义的 \\ref{key} 需确保对应 \\label{key} 存在。\n"
        "【禁止新增 \\newtheorem】\n"
        "- 严禁在 preamble 中新增任何 \\newtheorem 或 \\theoremstyle 定义\n"
        "- 模板已定义的标准环境：theorem, lemma, proposition, corollary, definition, "
        "remark, example, proof, conjecture, claim, fact, observation\n"
        "- 如果正文中出现未定义的环境（如 maintheorem, cor-kirillov, graham-refined, lemm 等），"
        "必须将其改写为上述标准环境名，而不是在 preamble 中新增 \\newtheorem\n"
        "- 例：\\begin{maintheorem} → \\begin{theorem}，\\begin{lemm} → \\begin{lemma}\n"
    )
    user = (
        "以下是 xelatex 编译报错信息（含上下文代码）：\n\n"
        + error_report
        + "\n\n" + _LATEX_REVIEW_CHECKLIST
        + "\n\n完整 LaTeX 源文件：\n"
        + tex
        + "\n\n请直接输出修正后的完整 LaTeX 文件，不要任何前缀说明。"
    )
    fixed = call_llm(model_name, system, user, temperature=0.1)

    # Strip markdown code fences
    fixed = re.sub(r'^```(?:latex)?\s*\n', '', fixed.strip(), flags=re.MULTILINE)
    fixed = re.sub(r'\n```\s*$', '', fixed.strip())

    # Strip any prose preamble before \documentclass
    doc_start = fixed.find(r'\documentclass')
    if doc_start > 0:
        fixed = fixed[doc_start:]

    return _fix_latex_envs(fixed)


def compiler_node(state: PipelineState) -> dict:
    """Step 6: xelatex 编译 → 读报错 → subagent LLM 修复，循环直到无错或达上限。"""
    print(f"\n[Step 6] xelatex 编译检查（最多 {_MAX_COMPILE_ROUNDS} 轮）")
    main_path = Path(state["final_latex"])
    model_name = state["model_name"]

    if not main_path.exists():
        print(f"  [跳过] 未找到 main.tex: {main_path}")
        return {}

    for round_no in range(1, _MAX_COMPILE_ROUNDS + 1):
        print(f"  [Round {round_no}/{_MAX_COMPILE_ROUNDS}] xelatex {main_path.name} ...")
        try:
            rc, log_text = _run_xelatex(main_path)
        except FileNotFoundError:
            print("  [跳过] xelatex 未安装，跳过编译检查")
            return {}
        except subprocess.TimeoutExpired:
            print("  [超时] xelatex 超时，跳过本轮")
            break

        errors = _parse_errors(log_text)
        if not errors:
            print(f"  ✓ 编译成功（Round {round_no}，无错误）")
            break

        print(f"  发现 {len(errors)} 个错误，subagent 修复...")
        for e in errors[:8]:
            print(f"    行 {e['line_no']}: {e['message'][:80]}")

        tex = main_path.read_text(encoding="utf-8")
        tex_lines = tex.splitlines()
        error_report = _build_error_context(tex_lines, errors)

        fixed_tex = _fix_with_llm(model_name, tex, error_report)

        # Sanity check: must start with \documentclass
        if not fixed_tex.lstrip().startswith('\\documentclass'):
            print("  [警告] LLM 输出不是合法 LaTeX，保留原文件跳过本轮")
            continue

        # Restore original template preamble to prevent LLM from injecting
        # spurious \newtheorem / \theoremstyle definitions
        tpl = TEMPLATES.get(state.get("template_name", ""), {})
        orig_preamble = tpl.get("preamble", "").replace("__TITLE__", state.get("doc_title", ""))
        if orig_preamble:
            body_start = fixed_tex.find(r'\begin{document}')
            if body_start != -1:
                fixed_tex = orig_preamble + "\n" + fixed_tex[body_start:]

        main_path.write_text(fixed_tex, encoding="utf-8")
        print(f"  修复完成，写回 {main_path.name}")

        # Record error patterns and fixes into persistent memory
        summarize_fixes(errors, tex, fixed_tex, model_name)

        if round_no == _MAX_COMPILE_ROUNDS:
            print(f"  [警告] 达到最大轮次 {_MAX_COMPILE_ROUNDS}，仍有错误，停止")

    return {}
