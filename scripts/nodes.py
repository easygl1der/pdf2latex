"""
Minimal LangGraph Nodes for pdf2latex with Surgical Repair Loop
"""
import re
import subprocess
from pathlib import Path
from langgraph.types import Send
from .config import TEMPLATES, OUTPUT_ROOT, PipelineState, WriterInput
from .llm import call_llm
from .error_memory import build_memory_prompt, summarize_fixes

def _clean_res(res: str) -> str:
    """Remove code blocks and extra whitespace."""
    res = re.sub(r'```(?:latex)?\n?', '', res)
    res = re.sub(r'\n?```', '', res)
    return res.strip()

# ═══════════════════════════════════════════════════════════════
# Nodes
# ═══════════════════════════════════════════════════════════════

def classifier_node(state: PipelineState) -> dict:
    print("\n[Step 1] Classifier")
    sample = Path(state["markdown_path"]).read_text(encoding="utf-8")[:2000]
    res = call_llm(state["model_name"], "Is this a 'book' or a 'paper'? Output one word only.", sample, temperature=0, show_thinking=False)
    doc_type = "paper" if "paper" in res.lower() else "book"
    
    # User Requirement: Paper -> amsart, Book -> article
    tpl = "amsart" if doc_type == "paper" else "article"
    print(f"  - Classified as: {doc_type} -> Default Template: {tpl}")
    
    out_dir = OUTPUT_ROOT / Path(state["pdf_path"]).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    return {"doc_type": doc_type, "output_dir": str(out_dir), "template_name": tpl}

def route_by_doc_type(state: PipelineState) -> str:
    return "supervisor" if state["doc_type"] == "book" else "paper_writer"

def supervisor_node(state: PipelineState) -> dict:
    print("\n[Step 2] Supervisor")
    txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    matches = list(re.finditer(r'^#\s+(.+)$', txt, re.MULTILINE))
    lines = txt.splitlines()
    chapters = []
    for i, m in enumerate(matches):
        start = txt[:m.start()].count('\n') + 1
        end = txt[:matches[i+1].start()].count('\n') if i+1 < len(matches) else len(lines)
        chapters.append({"index": i+1, "title": m.group(1).strip(), "line_start": start, "line_end": end})
    if not chapters:
        chapters = [{"index": 1, "title": "Main", "line_start": 1, "line_end": len(lines)}]
    return {"chapters": chapters, "doc_title": Path(state["pdf_path"]).stem}

def dispatch_chapters(state: PipelineState):
    return [Send("chapter_writer", {**state, "chapter": ch}) for ch in state["chapters"]]

def chapter_writer_node(state: WriterInput) -> dict:
    ch = state["chapter"]
    print(f"  [Writer] {ch['title']}")
    lines = Path(state["markdown_path"]).read_text(encoding="utf-8").splitlines()
    content = "\n".join(lines[ch["line_start"]-1 : ch["line_end"]])
    tpl = TEMPLATES[state["template_name"]]
    system = f"Convert this Markdown to LaTeX snippet for {state['template_name']} style. {tpl['style_hint']}"
    res = _clean_res(call_llm(state["model_name"], system, content))
    return {"chapter_outputs": [{"index": ch["index"], "title": ch["title"], "latex_body": res}]}

def paper_writer_node(state: PipelineState) -> dict:
    print("\n[Paper Writer]")
    txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    tpl = TEMPLATES[state["template_name"]]
    system = f"Convert this Markdown to LaTeX for {state['template_name']} style. {tpl['style_hint']}"
    res = _clean_res(call_llm(state["model_name"], system, txt))
    final = tpl["preamble"].replace("__TITLE__", state["doc_title"]) + \
            tpl["body_wrapper"].replace("__BODY__", res)
    p = Path(state["output_dir"]) / "main.tex"
    p.write_text(final, encoding="utf-8")
    return {"final_latex": str(p)}

def retriever_node(state: PipelineState) -> dict:
    print("\n[Step 4] Retriever")
    for ch in state["chapter_outputs"]:
        ch["latex_body"] = _clean_res(call_llm(state["model_name"], "Fix LaTeX formatting errors in this code.", ch["latex_body"]))
    return {"chapter_outputs": state["chapter_outputs"]}

def assembler_node(state: PipelineState) -> dict:
    print("\n[Step 5] Assembler")
    tpl = TEMPLATES[state["template_name"]]
    sorted_ch = sorted(state["chapter_outputs"], key=lambda x: x["index"])
    body = "\n".join(c["latex_body"] for c in sorted_ch)
    final = tpl["preamble"].replace("__TITLE__", state["doc_title"]) + \
            tpl["body_wrapper"].replace("__BODY__", body)
    p = Path(state["output_dir"]) / "main.tex"
    p.write_text(final, encoding="utf-8")
    return {"final_latex": str(p)}

# ═══════════════════════════════════════════════════════════════
# Compiler with Surgical Repair
# ═══════════════════════════════════════════════════════════════

def _parse_latex_log(log_path: Path, source_text: str) -> list[dict]:
    """Extract errors with line numbers and find lines for citations."""
    if not log_path.exists(): return []
    log_content = log_path.read_text(encoding="utf-8", errors="ignore")
    lines = source_text.splitlines()
    issues = []
    
    # 1. Standard Error Pattern: main.tex:123: Message
    for m in re.finditer(r'(?:\./)?\S+\.tex:(\d+):\s*(.+)', log_content):
        issues.append({"line": int(m.group(1)), "msg": m.group(2).strip()})
        
    # 2. Citations (Search for the \cite{key} in source to find the line)
    if "Citation" in log_content and "undefined" in log_content:
        for m in re.finditer(r"Citation `([^']+)' on page \d+ undefined", log_content):
            key = m.group(1)
            # Find which line contains this cite key
            for i, line in enumerate(lines):
                if f"\\cite{{{key}}}" in line or f"\\cite{{ {key}" in line: # simple search
                    issues.append({"line": i + 1, "msg": f"Undefined citation '{key}'"})
                    break

    # 3. References (Search for \ref{key})
    if "Reference" in log_content and "undefined" in log_content:
        for m in re.finditer(r"Reference `([^']+)' on page \d+ undefined", log_content):
            key = m.group(1)
            for i, line in enumerate(lines):
                if f"\\ref{{{key}}}" in line:
                    issues.append({"line": i + 1, "msg": f"Undefined reference '{key}'"})
                    break

    return issues[:5]

def compiler_node(state: PipelineState) -> dict:
    print(f"\n[Step 6] Compiler (Line-Focused Surgical Repair)")
    p = Path(state["final_latex"])
    model = state["model_name"]
    xelatex_cmd = ["xelatex", "-interaction=nonstopmode", "-synctex=1", "-halt-on-error", p.name]
    
    for r in range(1, 4):
        print(f"  [Round {r}] Compiling...")
        subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True)
        
        # Check for BibTeX on first round
        aux = p.with_suffix(".aux")
        if r == 1 and aux.exists() and "\\citation" in aux.read_text(encoding="utf-8", errors="ignore"):
            print("  - Running BibTeX...")
            subprocess.run(["bibtex", p.stem], cwd=p.parent, capture_output=True)
            subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True)
        
        source_text = p.read_text(encoding="utf-8")
        issues = _parse_latex_log(p.with_suffix(".log"), source_text)
        
        if not issues:
            print("  ✓ Success: No line-specific errors found.")
            break
            
        print(f"  Fixing {len(issues)} issues at specific lines...")
        source_lines = source_text.splitlines()
        memory = build_memory_prompt()
        
        for issue in issues:
            ln = issue["line"]
            if 0 < ln <= len(source_lines):
                idx = ln - 1
                # Small window (2 lines before/after)
                start, end = max(0, idx-2), min(len(source_lines), idx+3)
                context = "\n".join(source_lines[start:end])
                
                print(f"    - Repairing line {ln}: {issue['msg'][:50]}")
                system = f"Fix the technical LaTeX error in this snippet. Ignore fonts/styling. Output ONLY fixed code.\n{memory}"
                user = f"Error at line {ln}: {issue['msg']}\nSnippet:\n{context}"
                
                fixed = _clean_res(call_llm(model, system, user))
                source_lines[start:end] = fixed.splitlines()
                summarize_fixes([{"message": issue["msg"]}], context, fixed, model)
                
        p.write_text("\n".join(source_lines), encoding="utf-8")
        
    return {}
