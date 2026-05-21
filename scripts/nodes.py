"""
Minimal LangGraph Nodes for pdf2latex
"""
import re
import subprocess
from pathlib import Path
from langgraph.types import Send
from .config import TEMPLATES, OUTPUT_ROOT, PipelineState, WriterInput
from .llm import call_llm

def _clean_res(res: str) -> str:
    """Remove code blocks and extra whitespace."""
    res = re.sub(r'```(?:latex)?\n?', '', res)
    res = re.sub(r'\n?```', '', res)
    return res.strip()

def classifier_node(state: PipelineState) -> dict:
    print("\n[Step 1] Classifier")
    sample = Path(state["markdown_path"]).read_text(encoding="utf-8")[:2000]
    res = call_llm(state["model_name"], "Is this a 'book' or a 'paper'? Output one word only.", sample, temperature=0, show_thinking=False)
    doc_type = "paper" if "paper" in res.lower() else "book"
    out_dir = OUTPUT_ROOT / Path(state["pdf_path"]).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    return {"doc_type": doc_type, "output_dir": str(out_dir)}

def route_by_doc_type(state: PipelineState) -> str:
    return "supervisor" if state["doc_type"] == "book" else "paper_writer"

def supervisor_node(state: PipelineState) -> dict:
    print("\n[Step 2] Supervisor")
    txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    # Basic split by H1
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

def compiler_node(state: PipelineState) -> dict:
    print("\n[Step 6] Compiler")
    p = Path(state["final_latex"])
    subprocess.run(["xelatex", "-interaction=nonstopmode", p.name], cwd=p.parent, capture_output=True)
    return {}
