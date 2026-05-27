import os
import sys
import re
import subprocess
from pathlib import Path
from typing import TypedDict, Annotated, List
import operator
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from .config import TEMPLATES, OUTPUT_ROOT
from .llm import call_llm
from .prompts import load_prompt
from .writer_engine import create_skeleton, inject_content
from .mineru_convert_wrapper import mineru_convert_to_md

# ═══════════════════════════════════════════════════════════════
# State Management
# ═══════════════════════════════════════════════════════════════

class PipelineState(TypedDict):
    pdf_path: str
    markdown_path: str
    content_list_path: str
    template_name: str
    model_name: str
    mode: str
    doc_type: str        # 'book' or 'paper'
    doc_title: str
    doc_author: str
    doc_date: str
    output_dir: str
    skeleton: str        # LaTeX skeleton with placeholders
    chapters: List[dict] # For book mode
    chapter_outputs: Annotated[List[dict], operator.add]
    final_latex: str

class WriterInput(TypedDict):
    chapter: dict
    pdf_path: str
    markdown_path: str
    content_list_path: str
    template_name: str
    model_name: str
    mode: str

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _clean_res(res: str) -> str:
    # 1. Strip <think> tags (deepseek-v3 / r1)
    res = re.sub(r'<think>.*?</think>', '', res, flags=re.DOTALL).strip()
    # 2. Strip thinking blocks
    res = re.sub(r'(?i)thinking\s*\.\.\..*?done\s*thinking\.?', '', res, flags=re.DOTALL).strip()
    # 3. Strip latex code fences
    res = re.sub(r"^```latex\n", "", res, flags=re.MULTILINE)
    res = res.replace("```", "").strip()
    return res

def _get_pdf_first_page_image(pdf_path: str) -> str:
    import base64
    import fitz # PyMuPDF
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_data = pix.tobytes("jpg")
    doc.close()
    return base64.b64encode(img_data).decode("utf-8")

def _analyze_images(markdown_snippet: str, content_list_path: str, pdf_path: str) -> str:
    """Analyze images found in markdown snippet using Vision Agent in parallel."""
    import json
    import base64
    import fitz
    import time
    
    img_pattern = r'!\[\]\((images/[a-f0-9]+\.(?:jpg|png))\)'
    img_paths = list(set(re.findall(img_pattern, markdown_snippet)))
    if not img_paths or not content_list_path or not os.path.exists(content_list_path):
        return ""

    try:
        with open(content_list_path, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
    except Exception: return ""

    def process_single_image(img_path):
        start_time = time.time()
        page_num = 0
        for item in content_list:
            if item.get("img_path") == img_path:
                page_num = item.get("page_idx", 0) + 1
                break
        
        if page_num > 0:
            try:
                doc = fitz.open(pdf_path)
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_b64 = base64.b64encode(pix.tobytes("jpg")).decode("utf-8")
                doc.close()

                system = "You are a Vision Assistant. Analyze the provided PDF page to identify the layout and content of the figure/table referenced."
                user = f"Find the image referenced as '{img_path}'. Is it a single figure, a subfigure grid (e.g., 2x2), or a table? Describe its content and any captions."
                
                print(f"    [Vision] Starting analysis for {img_path} (Page {page_num})...")
                desc = call_llm("gemma-vision", system, user, temperature=0, show_thinking=False, image_b64=img_b64)
                elapsed = time.time() - start_time
                print(f"    [Vision] Finished {img_path} in {elapsed:.1f}s")
                return f"IMAGE: {img_path}\nPAGE: {page_num}\nDESCRIPTION: {desc}"
            except Exception as e:
                print(f"    [Warning] Failed to analyze image {img_path}: {e}")
                return None
        return None

    print(f"  [Vision] Analyzing {len(img_paths)} unique images in parallel...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_single_image, img_paths))

    final_results = [r for r in results if r]
    return "\n\n".join(final_results)


def get_style_prompt(mode: str = "original") -> str:
    path = Path(__file__).parent.parent / "docs" / "style-prompt.md"
    if not path.exists(): return ""
    return path.read_text(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════
# Nodes
# ═══════════════════════════════════════════════════════════════

def converter_node(state: PipelineState) -> dict:
    print(f"\n[Step 0] MinerU PDF Conversion")
    pdf_path = Path(state["pdf_path"])
    out_dir = OUTPUT_ROOT / pdf_path.stem
    
    # ── Cache Check ───────────────────────────────────────────
    md_file_path = out_dir / f"{pdf_path.stem}.md"
    content_list_json = out_dir / f"{pdf_path.stem}_content_list.json"
    if not content_list_json.exists():
        content_list_json = out_dir / f"{pdf_path.stem}.json"

    if md_file_path.exists() and content_list_json.exists():
        print(f"  [Cache] Found existing conversion in {out_dir}, skipping MinerU API call.")
        return {
            "markdown_path": str(md_file_path),
            "content_list_path": str(content_list_json),
            "output_dir": str(out_dir)
        }
    
    # ── No Cache: Run Conversion ──────────────────────────────
    print(f"  [MinerU] No cache found. Starting fresh conversion...")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_file = mineru_convert_to_md(str(pdf_path), out_dir)
    
    # Re-check paths after conversion
    content_list_json = out_dir / f"{pdf_path.stem}_content_list.json"
    if not content_list_json.exists():
        content_list_json = out_dir / f"{pdf_path.stem}.json"

    return {
        "markdown_path": md_file,
        "content_list_path": str(content_list_json) if content_list_json.exists() else "",
        "output_dir": str(out_dir)
    }


def classifier_node(state: PipelineState) -> dict:
    print("\n[Step 1] Classifier & Metadata Extraction (Vision Mode)")
    img_b64 = _get_pdf_first_page_image(state["pdf_path"])
    system = "You are a document classifier. extract TYPE (book/paper), TITLE, AUTHOR, DATE."
    user = "Analyze this page."
    res = call_llm("gemma-vision", system, user, image_b64=img_b64, timeout=120.0)
    
    doc_type = "paper"
    title, author, date = Path(state["pdf_path"]).stem, "Anonymous", "unknown"
    try:
        parts = res.split("|")
        for p in parts:
            if "TYPE:" in p: doc_type = "paper" if "paper" in p.lower() else "book"
            if "TITLE:" in p: title = p.split("TITLE:")[1].strip()
            if "AUTHOR:" in p: author = p.split("AUTHOR:")[1].strip()
            if "DATE:" in p: date = p.split("DATE:")[1].strip()
    except Exception: pass

    out_dir = Path(state["output_dir"])
    
    return {
        "doc_type": doc_type, 
        "template_name": "amsart" if doc_type == "paper" else "article",
        "doc_title": title, "doc_author": author, "doc_date": date
    }


def skeleton_node(state: PipelineState) -> dict:
    """New Node: Generates the LaTeX skeleton."""
    print("\n[Step 2] Building Skeleton...")
    txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    
    chapters = []
    if state["doc_type"] == "book":
        matches = list(re.finditer(r'^#\s+(.+)$', txt, re.MULTILINE))
        lines = txt.splitlines()
        for i, m in enumerate(matches):
            start = txt[:m.start()].count('\n') + 1
            end = txt[:matches[i+1].start()].count('\n') if i+1 < len(matches) else len(lines)
            chapters.append({"index": i+1, "title": m.group(1).strip(), "line_start": start, "line_end": end})
    
    if not chapters:
        chapters = [{"index": 1, "title": "Full Content", "line_start": 1, "line_end": len(txt.splitlines())}]

    skel = create_skeleton({**state, "chapters": chapters})
    return {"skeleton": skel, "chapters": chapters}

def dispatch_chapters(state: PipelineState):
    return [Send("chapter_writer", {**state, "chapter": ch}) for ch in state["chapters"]]

def chapter_writer_node(state: WriterInput) -> dict:
    import time
    start_time = time.time()
    ch = state["chapter"]
    print(f"  [Writer] Starting {ch['title']}...")
    
    lines = Path(state["markdown_path"]).read_text(encoding="utf-8").splitlines()
    content = "\n".join(lines[ch["line_start"]-1 : ch["line_end"]])
    
    # Analyze images (this can be a bottleneck)
    visual_context = _analyze_images(content, state["content_list_path"], state["pdf_path"])
    
    tpl = TEMPLATES[state["template_name"]]
    prompt_vars = {
        "template_name": state["template_name"],
        "style_hint": tpl["style_hint"],
        "style_prompt": get_style_prompt(state.get("mode", "original")),
        "visual_context": visual_context if visual_context else "No images."
    }
    
    system = load_prompt("chapter_system", prompt_vars)
    
    print(f"  [Writer] Calling LLM for {ch['title']} (Content size: {len(content)} chars)...")
    res = _clean_res(call_llm(state["model_name"], system, content))
    
    elapsed = time.time() - start_time
    print(f"  [Writer] Finished {ch['title']} in {elapsed:.1f}s")
    
    return {"chapter_outputs": [{
        "index": ch["index"], 
        "title": ch["title"], 
        "latex_body": res
    }]}


def assembler_node(state: PipelineState) -> dict:
    print("\n[Step 4] Final Assembly (Surgical Injection)")
    final = state["skeleton"]
    
    # Sort by index to be safe
    outputs = sorted(state["chapter_outputs"], key=lambda x: x["index"])
    for out in outputs:
        placeholder = f"CONTENT_PLACEHOLDER_{out['index']}"
        final = inject_content(final, placeholder, out["latex_body"])
        
    p = Path(state["output_dir"]) / "main.tex"
    p.write_text(final, encoding="utf-8")
    return {"final_latex": str(p)}

def compiler_node(state: PipelineState) -> dict:
    print(f"\n[Step 6] Compiler")
    p = Path(state["final_latex"])
    xelatex_cmd = ["xelatex", "-interaction=nonstopmode", p.name]
    
    print(f"  Compiling...")
    result = subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True, text=True)
    
    # Check for BibTeX
    aux = p.with_suffix(".aux")
    if aux.exists() and "\\citation" in aux.read_text(encoding="utf-8", errors="ignore"):
        print("  - Running BibTeX...")
        subprocess.run(["bibtex", p.stem], cwd=p.parent, capture_output=True)
        result = subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  ❌ xelatex failed (RC {result.returncode})")
        log = p.with_suffix(".log")
        if log.exists():
            errors = [l for l in log.read_text(errors="ignore").splitlines() if l.startswith("!")]
            for err in errors[:5]: print(f"    {err}")
    
    pdf = p.with_suffix(".pdf")
    if pdf.exists(): print(f"  ✅ PDF generated: {pdf.name}")
    return {}
