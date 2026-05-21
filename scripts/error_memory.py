"""
LaTeX 错误知识库：记录编译错误模式和修复方案，供后续转录时注入 prompt。

存储位置：<project_root>/latex_error_memory.json
格式：
  {
    "entries": [
      {
        "error_pattern": "Undefined control sequence \\foo",
        "fix": "将 \\foo 替换为正确命令或删除",
        "example_before": "\\foo{text}",
        "example_after": "\\textbf{text}",
        "count": 3,
        "last_seen": "2026-05-21"
      },
      ...
    ]
  }
"""

import json
import re
from datetime import date
from pathlib import Path

_MEMORY_PATH = Path(__file__).parent.parent / "latex_error_memory.json"
_MAX_ENTRIES = 50


def _load() -> dict:
    if _MEMORY_PATH.exists():
        try:
            return json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"entries": []}


def _save(data: dict) -> None:
    _MEMORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_fix(error_pattern: str, fix: str,
               example_before: str = "", example_after: str = "") -> None:
    """Record a successfully resolved error pattern into the knowledge base."""
    data = _load()
    entries = data["entries"]

    # Normalize: strip line numbers so similar errors merge
    normalized = re.sub(r'\b\d+\b', 'N', error_pattern).strip()[:120]

    for entry in entries:
        if entry["error_pattern"] == normalized:
            entry["count"] += 1
            entry["last_seen"] = str(date.today())
            if example_before:
                entry["example_before"] = example_before
            if example_after:
                entry["example_after"] = example_after
            if fix and fix != _infer_fix(error_pattern):
                entry["fix"] = fix[:300]
            break
    else:
        entries.append({
            "error_pattern": normalized,
            "fix": fix[:300],
            "example_before": example_before[:200],
            "example_after": example_after[:200],
            "count": 1,
            "last_seen": str(date.today()),
        })

    entries.sort(key=lambda x: x["count"], reverse=True)
    data["entries"] = entries[:_MAX_ENTRIES]
    _save(data)


def build_memory_prompt() -> str:
    """Return a prompt fragment listing known error patterns to avoid."""
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return ""

    lines = ["\n【历史错误记录（根据过往编译报错总结，务必避免）】"]
    for e in entries[:15]:
        line = f"- 错误：{e['error_pattern']}  →  修复：{e['fix']}"
        if e.get("example_before") and e.get("example_after"):
            line += f"\n    错误写法：{e['example_before']}"
            line += f"\n    正确写法：{e['example_after']}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def summarize_fixes(errors_before: list[dict], tex_before: str, tex_after: str,
                    model_name: str = "") -> None:
    """Use LLM to summarize what was fixed, then record into memory.

    Falls back to rule-based inference if model_name is empty.
    """
    if not errors_before:
        return

    if model_name:
        _summarize_with_llm(errors_before, tex_before, tex_after, model_name)
    else:
        _summarize_rule_based(errors_before, tex_before, tex_after)


_DIFF_CHUNK_CHARS = 6000   # max chars per LLM call
_DIFF_CONTEXT_LINES = 3    # surrounding context lines per diff hunk


def _extract_diff_hunks(original: str, reviewed: str) -> list[str]:
    """Return unified-diff hunks between original and reviewed as a list of strings.

    Each hunk includes _DIFF_CONTEXT_LINES of surrounding context so the LLM
    can understand what was changed and why.
    """
    import difflib
    orig_lines = original.splitlines(keepends=True)
    rev_lines  = reviewed.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, rev_lines,
        fromfile="original", tofile="reviewed",
        n=_DIFF_CONTEXT_LINES,
    ))
    if not diff:
        return []

    # Split into individual hunks (lines starting with "@@")
    hunks: list[list[str]] = []
    current: list[str] = []
    for line in diff:
        if line.startswith("@@") and current:
            hunks.append(current)
            current = []
        current.append(line)
    if current:
        hunks.append(current)

    return ["".join(h) for h in hunks]


def _batch_hunks(hunks: list[str], max_chars: int) -> list[str]:
    """Group hunks into batches that each fit within max_chars."""
    batches: list[str] = []
    buf = ""
    for hunk in hunks:
        if buf and len(buf) + len(hunk) > max_chars:
            batches.append(buf)
            buf = ""
        buf += hunk
    if buf:
        batches.append(buf)
    return batches


def _call_learn_llm(model_name: str, diff_text: str) -> list[dict]:
    """Ask LLM to extract fix rules from a diff chunk. Returns list of rule dicts."""
    from .llm import call_llm

    system = (
        "你是 LaTeX 专家。以下是一段 unified diff，'-' 行是原始错误写法，'+' 行是修正后写法。\n"
        "从中总结出通用的 LaTeX 排版规则，避免下次转录时再犯同样的错误。\n"
        "规则必须具体可执行，例如：'下划线 _ 在正文中必须转义为 \\_'。\n"
        "只输出 JSON 数组，格式：\n"
        '[{"error": "错误描述", "fix": "规避规则一句话", '
        '"before": "错误写法片段", "after": "正确写法片段"}]\n'
        "只输出 JSON，不要任何解释。"
    )
    user = f"diff 内容：\n{diff_text}\n\n请输出 JSON 规则数组："

    try:
        raw = call_llm(model_name, system, user, temperature=0.0, show_thinking=False)
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return []


def learn_from_review(original: str, reviewed: str, model_name: str) -> None:
    """Extract fix rules from the diff between original and reviewed LaTeX.

    Strategy:
    1. Compute unified diff — only changed lines are sent to the LLM, not full text.
    2. Batch hunks into chunks ≤ _DIFF_CHUNK_CHARS so nothing is truncated.
    3. Each batch is summarized independently; results are merged and de-duped.
    """
    if not original or not reviewed or original.strip() == reviewed.strip():
        return

    hunks = _extract_diff_hunks(original, reviewed)
    if not hunks:
        return

    batches = _batch_hunks(hunks, _DIFF_CHUNK_CHARS)
    total_rules = 0

    for i, batch in enumerate(batches, 1):
        items = _call_learn_llm(model_name, batch)
        for item in items:
            if isinstance(item, dict) and item.get("fix"):
                record_fix(
                    item.get("error", "Review Correction"),
                    item.get("fix", ""),
                    item.get("before", ""),
                    item.get("after", ""),
                )
                total_rules += 1

    if total_rules:
        print(f"  [Memory] 从 Review 中学习了 {total_rules} 条新规则"
              f"（{len(batches)} 批次，{len(hunks)} 个 diff 块）")


def _summarize_with_llm(errors: list[dict], tex_before: str, tex_after: str,
                        model_name: str) -> None:
    """Ask LLM to extract (error_pattern, fix, before_snippet, after_snippet) pairs."""
    from .llm import call_llm

    error_list = "\n".join(f"- {e['message']}" for e in errors[:10])

    # Only send a diff-like context: first 60 lines of before and after to keep tokens low
    before_sample = "\n".join(tex_before.splitlines()[:60])
    after_sample = "\n".join(tex_after.splitlines()[:60])

    system = (
        "你是 LaTeX 错误分析专家。根据编译报错列表和修复前后的代码片段，"
        "总结每个错误的修复规律，输出 JSON 数组。\n"
        "每个元素格式：\n"
        '{"error_pattern": "错误类型描述", "fix": "修复方法一句话", '
        '"example_before": "错误写法片段", "example_after": "正确写法片段"}\n'
        "只输出 JSON 数组，不要任何其他文字。"
    )
    user = (
        f"编译报错：\n{error_list}\n\n"
        f"修复前（前60行）：\n{before_sample}\n\n"
        f"修复后（前60行）：\n{after_sample}\n\n"
        "请输出 JSON 数组总结修复规律："
    )

    try:
        raw = call_llm(model_name, system, user, temperature=0.0, show_thinking=False)
        # Extract JSON array
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            raise ValueError("no JSON array found")
        items = json.loads(m.group(0))
        for item in items:
            if isinstance(item, dict) and item.get("error_pattern"):
                record_fix(
                    item.get("error_pattern", ""),
                    item.get("fix", ""),
                    item.get("example_before", ""),
                    item.get("example_after", ""),
                )
        print(f"  [Memory] 记录 {len(items)} 条修复规律")
    except Exception as e:
        # Fallback to rule-based on any failure
        print(f"  [Memory] LLM 总结失败（{e}），使用规则兜底")
        _summarize_rule_based(errors, tex_before, tex_after)


def _summarize_rule_based(errors: list[dict], tex_before: str, tex_after: str) -> None:
    """Rule-based fallback: record error message + inferred fix."""
    before_lines = tex_before.splitlines()
    after_lines = tex_after.splitlines()

    for err in errors:
        ln = err.get("line_no", 0)
        msg = err.get("message", "")
        if not msg:
            continue

        example_before, example_after = "", ""
        if ln > 0:
            b_idx = ln - 1
            example_before = before_lines[b_idx].strip() if b_idx < len(before_lines) else ""
            # after may have shifted lines; best effort same index
            example_after = after_lines[b_idx].strip() if b_idx < len(after_lines) else ""

        record_fix(msg, _infer_fix(msg), example_before, example_after)


def _infer_fix(error_msg: str) -> str:
    msg = error_msg.lower()
    if "undefined control sequence" in msg:
        return "检查命令拼写，确保反斜杠和命令名正确，或补充所需宏包"
    if "missing $ inserted" in msg:
        return "数学符号/命令必须在 $...$ 或 \\[...\\] 数学环境内使用"
    if "undefined citation" in msg or "\\cite{" in error_msg:
        return "在 thebibliography 环境中补充对应的 \\bibitem{key}"
    if "undefined reference" in msg or "\\ref{" in error_msg:
        return "确保 \\label{key} 存在且与 \\ref{key} 的 key 一致"
    if "environment" in msg and "undefined" in msg:
        return "检查环境名拼写（使用完整名称：theorem/lemma/proof 等），确保已在 preamble 中定义"
    if "missing \\begin{document}" in msg:
        return "确保文件包含 \\begin{document} ... \\end{document} 结构"
    if "extra }" in msg or "too many }" in msg:
        return "删除多余的 } 括号，检查 \\begin{env}} 等双括号错误"
    if "runaway argument" in msg:
        return "检查括号是否配对，通常是 { 未关闭"
    if "file not found" in msg:
        return "检查 \\input 或 \\includegraphics 引用的文件是否存在"
    return "根据报错上下文修正对应行的 LaTeX 语法"
