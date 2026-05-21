"""
LaTeX Error Knowledge Base: Records compilation error patterns and abstract fix strategies.
"""

import json
import re
from datetime import date
from pathlib import Path

_MEMORY_PATH = Path(__file__).parent.parent / "latex_error_memory.json"
_MAX_ENTRIES = 30


def _load() -> dict:
    if _MEMORY_PATH.exists():
        try:
            return json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"entries": []}


def _save(data: dict) -> None:
    _MEMORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_fix(abstract_pattern: str, fix_rule: str,
               example_before: str = "", example_after: str = "") -> None:
    """Record a categorized fix rule into the knowledge base."""
    data = _load()
    entries = data["entries"]

    # Deduplicate based on abstract pattern
    for entry in entries:
        if entry["pattern"] == abstract_pattern:
            entry["count"] += 1
            entry["last_seen"] = str(date.today())
            # Update examples only if new ones are provided and it's a frequent error
            if example_before and entry["count"] % 5 == 0:
                entry["example_before"] = example_before
                entry["example_after"] = example_after
            break
    else:
        entries.append({
            "pattern": abstract_pattern,
            "fix": fix_rule[:300],
            "example_before": example_before[:200],
            "example_after": example_after[:200],
            "count": 1,
            "last_seen": str(date.today()),
        })

    entries.sort(key=lambda x: x["count"], reverse=True)
    data["entries"] = entries[:_MAX_ENTRIES]
    _save(data)


def build_memory_prompt() -> str:
    """Return a prompt fragment of abstract rules and concrete examples."""
    data = _load()
    entries = data.get("entries", [])
    if not entries:
        return ""

    lines = ["\n【Learned LaTeX Fix Patterns (Avoid these common issues)】"]
    for e in entries[:10]:
        line = f"- Issue Category: {e['pattern']}\n  Rule: {e['fix']}"
        if e.get("example_before"):
            line += f"\n  Example Bad: {e['example_before']}\n  Example Good: {e['example_after']}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def summarize_fixes(issues: list[dict], tex_before: str, tex_after: str,
                    model_name: str) -> None:
    """Use LLM to abstract the fix into a general rule and record it."""
    from .llm import call_llm

    # Only attempt abstraction if there's an actual change
    if tex_before.strip() == tex_after.strip():
        return

    system = (
        "You are a LaTeX expert. Analyze the fix made to the code and abstract it into a general rule.\n"
        "Categorize the error into a high-level pattern (e.g., 'Unescaped Special Characters', 'Missing Environment Closure').\n"
        "Output ONLY a JSON object:\n"
        '{"pattern": "Short category name", "fix": "One sentence general rule", '
        '"before": "Specific short bad snippet", "after": "Specific short fixed snippet"}\n'
        "Do NOT record trivial line shifts. Focus on the technical fix."
    )
    user = (
        f"Original Issues: {[i['msg'] for i in issues]}\n\n"
        f"Snippet Before Fix:\n{tex_before}\n\n"
        f"Snippet After Fix:\n{tex_after}"
    )

    try:
        raw = call_llm(model_name, system, user, temperature=0.0, show_thinking=False)
        # Basic JSON extraction
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            res = json.loads(match.group(0))
            record_fix(res["pattern"], res["fix"], res["before"], res["after"])
    except Exception:
        # Silently fail to maintain pipeline flow
        pass
