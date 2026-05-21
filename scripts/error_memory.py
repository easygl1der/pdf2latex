"""
LaTeX Error Knowledge Base: Records compilation error patterns and fix strategies
to be injected into prompts during future transcriptions.

Storage Location: <project_root>/latex_error_memory.json
Format:
  {
    "entries": [
      {
        "error_pattern": "Undefined control sequence \\foo",
        "fix": "Replace \\foo with the correct command or delete it",
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

    lines = ["\n【Historical Error Records (Summarized from past compilation errors, MUST AVOID)】"]
    for e in entries[:15]:
        line = f"- Error: {e['error_pattern']}  →  Fix: {e['fix']}"
        if e.get("example_before") and e.get("example_after"):
            line += f"\n    Incorrect usage: {e['example_before']}"
            line += f"\n    Correct usage: {e['example_after']}"
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
    """Return unified-diff hunks between original and reviewed as a list of strings."""
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
        "You are a LaTeX expert. Below is a unified diff, '-' lines are incorrect, "
        "'+' lines are corrected versions.\n"
        "Summarize general LaTeX typesetting rules from this to avoid the same mistakes in the future.\n"
        "Rules must be specific and actionable, e.g., 'Underscore _ in text must be escaped as \\_'.\n"
        "Output ONLY a JSON array in the following format:\n"
        '[{"error": "error description", "fix": "one-sentence fix rule", '
        '"before": "incorrect snippet", "after": "correct snippet"}]\n'
        "Output ONLY JSON, no explanation."
    )
    user = f"Diff content:\n{diff_text}\n\nPlease output the JSON rule array:"

    try:
        raw = call_llm(model_name, system, user, temperature=0.0, show_thinking=False)
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return []


def learn_from_review(original: str, reviewed: str, model_name: str) -> None:
    """Extract fix rules from the diff between original and reviewed LaTeX."""
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
        print(f"  [Memory] Learned {total_rules} new rules from Review "
              f"({len(batches)} batches, {len(hunks)} diff hunks)")


def _summarize_with_llm(errors: list[dict], tex_before: str, tex_after: str,
                        model_name: str) -> None:
    """Ask LLM to extract (error_pattern, fix, before_snippet, after_snippet) pairs."""
    from .llm import call_llm

    error_list = "\n".join(f"- {e['message']}" for e in errors[:10])

    # Only send a diff-like context: first 60 lines to keep tokens low
    before_sample = "\n".join(tex_before.splitlines()[:60])
    after_sample = "\n".join(tex_after.splitlines()[:60])

    system = (
        "You are a LaTeX error analysis expert. Based on the list of compilation errors and "
        "the code snippets before and after the fix, summarize the fix patterns and output a JSON array.\n"
        "Each element format:\n"
        '{"error_pattern": "error type description", "fix": "one-sentence fix method", '
        '"example_before": "incorrect snippet", "example_after": "correct snippet"}\n'
        "Output ONLY the JSON array, no other text."
    )
    user = (
        f"Compilation errors:\n{error_list}\n\n"
        f"Before fix (first 60 lines):\n{before_sample}\n\n"
        f"After fix (first 60 lines):\n{after_sample}\n\n"
        "Please output the JSON array summarizing fix patterns:"
    )

    try:
        raw = call_llm(model_name, system, user, temperature=0.0, show_thinking=False)
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
        print(f"  [Memory] Recorded {len(items)} fix patterns")
    except Exception as e:
        print(f"  [Memory] LLM summarization failed ({e}), using rule-based fallback")
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
            example_after = after_lines[b_idx].strip() if b_idx < len(after_lines) else ""

        record_fix(msg, _infer_fix(msg), example_before, example_after)


def _infer_fix(error_msg: str) -> str:
    msg = error_msg.lower()
    if "undefined control sequence" in msg:
        return "Check command spelling, ensure backslashes are correct, or add required packages"
    if "missing $ inserted" in msg:
        return "Math symbols/commands must be used within $...$ or \\[...\\] environments"
    if "undefined citation" in msg or "\\cite{" in error_msg:
        return "Add the corresponding \\bibitem{key} in the thebibliography environment"
    if "undefined reference" in msg or "\\ref{" in error_msg:
        return "Ensure \\label{key} exists and matches the key in \\ref{key}"
    if "environment" in msg and "undefined" in msg:
        return "Check environment spelling (use full names: theorem/lemma/proof etc.), ensure it is defined in preamble"
    if "missing \\begin{document}" in msg:
        return "Ensure the file contains the \\begin{document} ... \\end{document} structure"
    if "extra }" in msg or "too many }" in msg:
        return "Remove extra } braces, check for double brace errors like \\begin{env}}"
    if "runaway argument" in msg:
        return "Check for matching braces, usually a { is not closed"
    if "file not found" in msg:
        return "Check if files referenced by \\input or \\includegraphics exist"
    return "Fix LaTeX syntax according to the error context"
