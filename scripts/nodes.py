"""
Minimal LangGraph Nodes for pdf2latex with Surgical Repair Loop
"""
import json
import re
import subprocess
import base64
import fitz
from pathlib import Path
from langgraph.types import Send
from .config import TEMPLATES, OUTPUT_ROOT, PipelineState, WriterInput
from .llm import call_llm

def _get_pdf_page_image(pdf_path: str, page_idx: int) -> str:
    """Capture a specific page of PDF as a base64 encoded JPEG."""
    try:
        doc = fitz.open(pdf_path)
        if page_idx >= len(doc):
            return ""
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("jpg", jpg_quality=75)
        doc.close()
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        print(f"    [Error] Failed to capture page {page_idx}: {e}")
        return ""

def _analyze_images(markdown_text: str, content_list_path: str, pdf_path: str) -> str:
    """Identify images in Markdown, look them up in content_list, and get vision descriptions."""
    if not content_list_path or not Path(content_list_path).exists():
        return ""
    
    try:
        with open(content_list_path, 'r', encoding='utf-8') as f:
            content_list = json.load(f)
    except Exception:
        return ""

    # Find all image tags like ![](images/abc.png)
    img_matches = re.findall(r'!\[.*?\]\((images/.*?)\)', markdown_text)
    if not img_matches:
        return ""

    descriptions = []
    seen_images = set()

    print(f"\n  [Vision] 👁️  Analyzing {len(img_matches)} images in this section...")
    
    for img_rel_path in img_matches:
        if img_rel_path in seen_images:
            continue
        seen_images.add(img_rel_path)

        # Find metadata in content_list
        meta = next((item for item in content_list if item.get("img_path") == img_rel_path), None)
        if not meta:
            img_name = Path(img_rel_path).name
            meta = next((item for item in content_list if item.get("img_path") and Path(item["img_path"]).name == img_name), None)

        if meta and "page_idx" in meta:
            page_idx = meta["page_idx"]
            print(f"\n    ┌─── 📸 [Vision Subagent: gemma-vision] ───")
            print(f"    │ Source: {img_rel_path}")
            print(f"    │ Page:   {page_idx+1}")
            print(f"    └───────────────────────────────────────")
            
            img_b64 = _get_pdf_page_image(pdf_path, page_idx)
            
            if img_b64:
                system = (
                    "You are a professional vision assistant for a LaTeX document converter.\n"
                    "Analyze the provided PDF page image and focus on the specific figure mentioned.\n\n"
                    "TASKS:\n"
                    "1. IMAGE CONTENT: Describe the visual content (e.g., line chart, flow diagram, photo).\n"
                    "2. LAYOUT & ARRANGEMENT: Is this a single image or a compound figure?\n"
                    "   - Check for subfigures (e.g., labeled as (a), (b), (c)).\n"
                    "   - Describe the spatial relationship: Are they side-by-side (horizontal), stacked (vertical), or in a grid (e.g., 2x2)?\n"
                    "3. CAPTIONING: Extract the main figure caption AND any sub-captions or labels found near the sub-images.\n"
                    "4. PLACEMENT: Describe its position relative to the surrounding text blocks.\n\n"
                    "OUTPUT: Provide a concise report that helps a LaTeX expert decide whether to use a standard 'figure' environment or a complex 'subfigure' (subcaption package) structure."
                )
                user = f"Please analyze the image '{img_rel_path}' and its surrounding layout on this page."
                
                # Use vision model
                desc = call_llm("gemma-vision", system, user, temperature=0, show_thinking=False, image_b64=img_b64)
                
                print(f"    ✅ Vision analysis for {Path(img_rel_path).name} complete.\n")
                descriptions.append(f"### Visual Context for {img_rel_path}:\n{desc}")

    if descriptions:
        print(f"  [Vision] ✓ Image analysis phase finished.\n")
        return "\n\n" + "\n\n".join(descriptions)
    return ""

def _get_pdf_first_page_image(pdf_path: str) -> str:
    """Capture the first page of PDF as a base64 encoded JPEG."""
    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        return ""
    page = doc.load_page(0)
    # 2x scale is good for OCR but might be large. 
    # Using JPEG with quality 75 significantly reduces size.
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img_bytes = pix.tobytes("jpg", jpg_quality=75)
    doc.close()
    
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    print(f"    [Size] Captured image: {len(img_bytes)/1024:.1f} KB (Base64: {len(b64)/1024:.1f} KB)")
    return b64

from .error_memory import build_memory_prompt, summarize_fixes

def _clean_res(res: str) -> str:
    """Extract content from triple backticks if present, else return stripped text."""
    match = re.search(r'```(?:latex)?\n?(.*?)\n?```', res, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback to previous behavior if no backticks
    res = re.sub(r'```(?:latex)?\n?', '', res)
    res = re.sub(r'\n?```', '', res)
    return res.strip()

def _apply_surgical_fixes(original_text: str, llm_output: str) -> str:
    """Parse [SEARCH]/[REPLACE] blocks and apply them. Fallback to code block if no tags."""
    # Pattern: [SEARCH] ... [REPLACE] ... [END]
    fixes = re.findall(r'\[SEARCH\]\n(.*?)\n\[REPLACE\]\n(.*?)\n\[END\]', llm_output, re.DOTALL)
    
    if not fixes:
        # Fallback: If LLM gave a full code block, use it (for extensive changes)
        match = re.search(r'```(?:latex)?\n?(.*?)\n?```', llm_output, re.DOTALL)
        if match:
            return match.group(1).strip()
        return original_text
        
    new_text = original_text
    applied_count = 0
    for search, replace in fixes:
        search = search.strip()
        replace = replace.strip()
        if search in new_text:
            new_text = new_text.replace(search, replace)
            applied_count += 1
        else:
            print(f"  [Warning] Exact match failed for a surgical fix. Skipping this one.")
            
    if applied_count > 0:
        print(f"  ✓ Applied {applied_count} surgical fixes.")
    return new_text

# ═══════════════════════════════════════════════════════════════
# Style Prompt Loader
# ═══════════════════════════════════════════════════════════════

_STYLE_PROMPT_CACHE = {}

def get_style_prompt(mode: str = "original") -> str:
    path = Path(__file__).parent.parent / "docs" / "style-prompt.md"
    if not path.exists():
        return ""
    
    if "full" not in _STYLE_PROMPT_CACHE:
        _STYLE_PROMPT_CACHE["full"] = path.read_text(encoding="utf-8")
    
    full_text = _STYLE_PROMPT_CACHE["full"]
    sections = {}
    current_section = None
    
    for line in full_text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            sections[current_section] = []
        elif current_section:
            sections[current_section].append(line)
            
    # Always include these for technical correctness and requested compactness
    # Moved MATH_NOTATION to the front to ensure high priority
    base_sections = ["MATH_NOTATION", "FORMATTING_RULES", "CITATIONS", "FIGURES_AND_TABLES", "LABELS", "THEOREMS"]
    
    if mode == "habit":
        # Habit Mode: Stylized adaptation using Stein Style guidelines
        mission = (
            "MISSION: Convert Markdown to LaTeX using your preferred 'Habit Mode' (Stein Style).\n"
            "You have permission to rephrase, add motivational context, and restructure content "
            "to make it more pedagogical and narrative as per the guidelines below."
        )
        selected = ["WRITING_STYLE"] + base_sections + ["BODY_APPENDIX"]
    else:
        # Original Mode: Strict reproduction (Default)
        mission = (
            "MISSION: STRICT CONTENT FIDELITY (Origin Mode).\n"
            "1. You MUST preserve all original text, wording, and structure exactly as it appears.\n"
            "2. CRITICAL EXCEPTION: ALL mathematical formulas MUST be COMPACT. Remove all spaces between symbols, commas, operators, and indices.\n"
            "   - BAD: $a + b = c$ | GOOD: $a+b=c$\n"
            "   - BAD: $\sum_ {i=1} ^ {n}$ | GOOD: $\sum_{i=1}^{n}$\n"
            "3. STRICT PROHIBITION: DO NOT use '\\begin{array}' for equations. Use 'aligned' or 'cases'. DO NOT use manual numbering like '(7)'.\n"
            "4. SKIP CSS: Completely ignore all CSS code, <style> tags, or inline styles. DO NOT convert them.\n"
            "5. NEVER GENERATE SPARSE CODE LIKE THIS: '$$ \\begin{array}{l} \\max _ {q} \\dots \\end{array} $$'. All math must be dense and clean."
        )
        selected = base_sections
        
    output = [f"【{mission}】", "", "Strictly follow these LaTeX specifications:"]
    for s in selected:
        if s in sections:
            output.extend(sections[s])
            output.append("") # spacer
            
    return "\n".join(output)

# ═══════════════════════════════════════════════════════════════
# Nodes
# ═══════════════════════════════════════════════════════════════

def classifier_node(state: PipelineState) -> dict:
    print("\n[Step 1] Classifier & Metadata Extraction (Vision Mode)")

    print(f"  [Capturing] First page of {Path(state['pdf_path']).name}...")
    img_b64 = _get_pdf_first_page_image(state["pdf_path"])

    system = (
        "You are a professional document classifier. Look at the provided image of the first page of a document.\n"
        "Analyze the structure and content to extract:\n"
        "1. TYPE: Is this a 'book' or a 'paper'?\n"
        "2. METADATA: Extract TITLE, AUTHOR, and writing DATE (use 'unknown' if not found).\n"
        "Format exactly as: TYPE: ... | TITLE: ... | AUTHOR: ... | DATE: ..."
    )
    user = "Please analyze this document page."

    print(f"  [Analyzing] Document vision features (gemma4:31b-cloud)...")
    # Use the specific vision model for this step. Vision models are often slower, so 120s timeout.
    res = call_llm("gemma-vision", system, user, temperature=0, show_thinking=False, image_b64=img_b64, timeout=120.0)

    # Parse combined response
    doc_type = "paper"
    title, author, date = Path(state["pdf_path"]).stem, "Anonymous", "unknown"

    try:
        parts = res.split("|")
        for p in parts:
            if "TYPE:" in p: doc_type = "paper" if "paper" in p.lower() else "book"
            if "TITLE:" in p: title = p.split("TITLE:")[1].strip()
            if "AUTHOR:" in p: author = p.split("AUTHOR:")[1].strip()
            if "DATE:" in p: date = p.split("DATE:")[1].strip()
    except Exception:
        pass

    tpl = "amsart" if doc_type == "paper" else "article"
    print(f"  - Classified as: {doc_type} -> Template: {tpl}")
    print(f"  - Metadata: {title} | {author} | {date}")

    out_dir = OUTPUT_ROOT / Path(state["pdf_path"]).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "doc_type": doc_type, 
        "output_dir": str(out_dir), 
        "template_name": tpl,
        "doc_title": title,
        "doc_author": author,
        "doc_date": date
    }
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
    return {"chapters": chapters}

def dispatch_chapters(state: PipelineState):
    return [Send("chapter_writer", {**state, "chapter": ch}) for ch in state["chapters"]]

def chapter_writer_node(state: WriterInput) -> dict:
    ch = state["chapter"]
    print(f"  [Writer] {ch['title']}")
    lines = Path(state["markdown_path"]).read_text(encoding="utf-8").splitlines()
    content = "\n".join(lines[ch["line_start"]-1 : ch["line_end"]])
    
    # Vision enhancement for images
    visual_context = _analyze_images(content, state.get("content_list_path", ""), state.get("pdf_path", ""))
    
    tpl = TEMPLATES[state["template_name"]]
    style_prompt = get_style_prompt(state.get("mode", "original"))
    
    # Structured Prompt Engineering
    system = (
        f"### ROLE: SENIOR LATEX TYPESETTING EXPERT\n"
        f"You are converting a scientific document to the {state['template_name']} LaTeX style.\n\n"
        f"### GUIDELINES & STYLE:\n{tpl['style_hint']}\n{style_prompt}\n\n"
        f"### VISUAL CONTEXT (FIGURES & TABLES):\n{visual_context if visual_context else 'No images in this section.'}\n\n"
        f"### CRITICAL CONSTRAINTS (MANDATORY):\n"
        f"1. MATHEMATICAL FORMULAS MUST BE COMPACT: Remove ALL unnecessary spaces between symbols, operators, and indices.\n"
        f"   - EXAMPLE: Use $a+b=c$, NOT $a + b = c$.\n"
        f"   - EXAMPLE: Use $\\max_{{q}}\\mathcal{{L}}$, NOT $\\max _ {{q}} \\mathcal {{L}}$.\n"
        f"   - RULE: Zero spaces after \\sum, \\max, \\int, and around +, -, =, ^, _, {{, }}.\n"
        f"2. EQUATION TAGGING: If a display math block ($$) contains a manual tag like (1), (2.1), etc., DO NOT use \\tag{{}}. Instead, use the \\begin{{equation}} environment with a \\label{{eq:number}}. \n"
        f"   - EXAMPLE: $$ a+b=c \quad (1) $$ -> \\begin{{equation}} a+b=c \\label{{eq:1}} \\end{{equation}}\n"
        f"3. CROSS-REFERENCES: Convert all plain-text references to equations (e.g., 'as seen in (1)') into proper LaTeX \\ref{{eq:1}} commands.\n"
        f"4. NO \\begin{{array}}: Use 'aligned', 'cases', or 'matrix' environments for equations. Manual numbering like (7) is FORBIDDEN except when converted to structural labels.\n"
        f"5. CITATIONS: Convert all plain-text citations like [18], [1, 2], or (Author, 2020) into proper LaTeX \\cite{{...}} commands.\n"
        f"6. DOCUMENT COMPLETENESS: Ensure all text from the source markdown is preserved.\n"
        f"7. OUTPUT FORMAT: Return ONLY the LaTeX code inside a single code block."
        )

    
    res = _clean_res(call_llm(state["model_name"], system, content))
    return {"chapter_outputs": [{
        "index": ch["index"], 
        "title": ch["title"], 
        "markdown_body": content,
        "latex_body": res
    }]}

def paper_writer_node(state: PipelineState) -> dict:
    print("\n[Paper Writer]")
    print(f"  [Reading] Loading full markdown source...")
    txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    
    # Vision enhancement for images
    visual_context = _analyze_images(txt, state.get("content_list_path", ""), state.get("pdf_path", ""))
    
    tpl = TEMPLATES[state["template_name"]]
    
    template_structure = tpl["preamble"].replace("__TITLE__", state["doc_title"])\
                                        .replace("__AUTHOR__", state.get("doc_author", "Anonymous"))\
                                        .replace("__DATE__", state.get("doc_date", "unknown")) + \
                         tpl["body_wrapper"].replace("__BODY__", "% Your content here")
    
    style_prompt = get_style_prompt(state.get("mode", "original"))
    
    # Structured Prompt Engineering
    system = (
        f"### ROLE: SENIOR LATEX TYPESETTING EXPERT\n"
        f"Convert the following Markdown to a FULL and COMPLETE LaTeX document for the {state['template_name']} style.\n\n"
        f"### MANDATORY METADATA (USE EXACTLY THESE):\n"
        f"- TITLE: {state['doc_title']}\n"
        f"- AUTHOR: {state.get('doc_author', 'Anonymous')}\n"
        f"- DATE: {state.get('doc_date', 'unknown')}\n\n"
        f"### TARGET TEMPLATE STRUCTURE:\n```latex\n{template_structure}\n```\n\n"
        f"### STYLE SPECIFICATIONS:\n{tpl['style_hint']}\n{style_prompt}\n\n"
        f"### VISUAL CONTEXT FOR IMAGES:\n{visual_context if visual_context else 'No image data available.'}\n\n"
        f"### CRITICAL CONSTRAINTS (MUST FOLLOW):\n"
        f"1. COMPACT MATH: All math formulas MUST have ZERO SPACES.\n"
        f"   - EXAMPLE: Use $a+b=c$, NOT $a + b = c$.\n"
        f"   - EXAMPLE: Use $\\max_{{q}}\\mathcal{{L}}$, NOT $\\max _ {{q}} \\mathcal {{L}}$.\n"
        f"   - RULE: Zero spaces after \\sum, \\max, \\int, and around +, -, =, ^, _, {{, }}.\n"
        f"2. EQUATION TAGGING: If a display math block ($$) contains a manual tag like (1), (2.1), etc., DO NOT use \\tag{{}}. Instead, use the \\begin{{equation}} environment with a \\label{{eq:number}}.\n"
        f"3. CROSS-REFERENCES: Convert all plain-text references to equations (e.g., 'as seen in (1)') into proper LaTeX \\ref{{eq:1}} commands.\n"
        f"4. ENVIRONMENT RULES: PROHIBITED: \\begin{{array}} for equations. Use aligned/cases instead. PROHIBITED: Manual numbering like (7) except when converted to structural labels.\n"
        f"5. CITATIONS: Convert all plain-text citations like [18], [1, 2], or (Author, 2020) into proper LaTeX \\cite{{...}} commands.\n"
        f"6. FULL DOCUMENT: You must generate everything from \\documentclass to \\end{{document}}.\n"
        f"7. CLEANLINESS: Ignore all CSS, HTML <style> tags, or original PDF page numbers.\n"
        f"8. OUTPUT: Return ONLY the final LaTeX code block."
        )

    
    res = _clean_res(call_llm(state["model_name"], system, txt))
    
    # Vision enhancement for images
    output_dir = Path(state["output_dir"])
    # _resolve_citations(res, output_dir)  # Disabled as requested

    p = output_dir / "main.tex"
    p.write_text(res, encoding="utf-8")
    return {"final_latex": str(p)}

def validator_node(state: PipelineState) -> dict:
    print("\n[Step 4] Content & Format Validation")
    style_prompt = get_style_prompt(state.get("mode", "original"))
    
    for ch in state["chapter_outputs"]:
        print(f"\n  >>> Validating Chapter: {ch['title']} <<<")
        system = (
            "You are a LaTeX expert. Compare the Markdown source with the generated LaTeX.\n"
            "If there are issues (missing content, bad formatting), provide surgical fixes.\n"
            "FORMAT FOR FIXES:\n"
            "[SEARCH]\n(exact few lines from current LaTeX)\n"
            "[REPLACE]\n(corrected lines)\n"
            "[END]\n\n"
            "If the changes are extremely extensive (over 50%), you may instead provide the full corrected chapter inside a ```latex block.\n"
            "If perfect, just say 'No changes needed'.\n\n"
            f"{style_prompt}"
        )
        user = f"### Markdown Source:\n{ch['markdown_body']}\n\n### Current LaTeX:\n{ch['latex_body']}"
        res = call_llm(state["model_name"], system, user)
        ch["latex_body"] = _apply_surgical_fixes(ch["latex_body"], res)
        
    return {"chapter_outputs": state["chapter_outputs"]}

def paper_validator_node(state: PipelineState) -> dict:
    print("\n[Paper Validator] Comparing Full Document...")
    p = Path(state["final_latex"])
    latex_txt = p.read_text(encoding="utf-8")
    md_txt = Path(state["markdown_path"]).read_text(encoding="utf-8")
    style_prompt = get_style_prompt(state.get("mode", "original"))
    
    system = (
        "You are a LaTeX expert. Compare the Markdown source with the generated document.\n"
        "If there are issues (missing content, formatting errors), provide surgical fixes.\n"
        "FORMAT FOR FIXES:\n"
        "[SEARCH]\n(exact block from current LaTeX)\n"
        "[REPLACE]\n(corrected block)\n"
        "[END]\n\n"
        "If the fixes are extremely widespread, you may output the full document in a ```latex block.\n"
        "If perfect, just say 'No changes needed'.\n\n"
        f"{style_prompt}"
    )
    user = f"### Markdown Source:\n{md_txt}\n\n### Generated LaTeX:\n{latex_txt}"
    
    res = call_llm(state["model_name"], system, user)
    fixed_latex = _apply_surgical_fixes(latex_txt, res)
    p.write_text(fixed_latex, encoding="utf-8")
    return {}

from .cite_tool import extract_citations, search_crossref, search_arxiv, format_bibitem, get_crossref_bibtex

def _resolve_citations(latex_body: str, output_dir: Path) -> None:
    """Extract citations from LaTeX, resolve them via APIs, and generate refs.bib."""
    all_keys = extract_citations(latex_body)
    if not all_keys:
        return

    print(f"  - Resolving {len(all_keys)} citations for refs.bib...")
    bib_entries = []
    
    for key in all_keys:
        # We'll use the key as a query if it looks like a title/author
        item = search_crossref(key) or search_arxiv(key)
        if item:
            doi = item.get("DOI")
            # Try to get standard BibTeX from CrossRef
            bib_text = get_crossref_bibtex(doi) if doi else None
            if bib_text:
                bib_entries.append(bib_text)
            else:
                title = item.get("title", [key])[0]
                bib_entries.append(f"@article{{{key},\n  title={{{title}}},\n  year={{2024}}\n}}")
        else:
            bib_entries.append(f"@misc{{{key},\n  title={{{key}}},\n  note={{Automatically resolved}}\n}}")
    
    bib_path = output_dir / "refs.bib"
    bib_path.write_text("\n\n".join(bib_entries), encoding="utf-8")
    print(f"  ✓ Generated {bib_path.name}")

def assembler_node(state: PipelineState) -> dict:
    print("\n[Step 5] Assembler")
    tpl = TEMPLATES[state["template_name"]]
    output_dir = Path(state["output_dir"])
    sorted_ch = sorted(state["chapter_outputs"], key=lambda x: x["index"])
    
    # 1. Combine body
    body = "\n".join(c["latex_body"] for c in sorted_ch)
    
    # 2. Resolve citations
    # _resolve_citations(body, output_dir)  # Disabled as requested

    # 3. Assemble main.tex
    final = tpl["preamble"].replace("__TITLE__", state["doc_title"])\
                          .replace("__AUTHOR__", state.get("doc_author", "Anonymous"))\
                          .replace("__DATE__", state.get("doc_date", "unknown")) + \
            tpl["body_wrapper"].replace("__BODY__", body)
            
    p = output_dir / "main.tex"
    p.write_text(final, encoding="utf-8")
    return {"final_latex": str(p)}

# ═══════════════════════════════════════════════════════════════
# Compiler with Surgical Repair
# ═══════════════════════════════════════════════════════════════

def _parse_latex_log(log_path: Path, source_text: str) -> list[dict]:
    """Extract errors with line numbers from LaTeX log."""
    if not log_path.exists(): return []
    log_content = log_path.read_text(encoding="utf-8", errors="ignore")
    issues = []
    
    # Format 1: file.tex:line: message (Modern style)
    for m in re.finditer(r'(?:\./)?\S+\.tex:(\d+):\s*(.+)', log_content):
        issues.append({"line": int(m.group(1)), "msg": m.group(2).strip()})
        
    # Format 2: ! LaTeX Error: ... followed by l.line_number (Classic style)
    if not issues:
        # Match pattern like: ! LaTeX Error: ... \n ... \n l.64 \begin{algorithm}
        pattern = r'!\s+(.*?)\n.*?\nl\.(\d+)\s'
        for m in re.finditer(pattern, log_content, re.DOTALL):
            issues.append({"line": int(m.group(2)), "msg": m.group(1).strip()})
            
    # Format 3: Generic Emergency Stop or Runaway argument
    if not issues:
        if "! Emergency stop" in log_content or "Runaway argument?" in log_content:
            # If no line found, try to find the last reported line
            line_match = re.search(r'l\.(\d+)', log_content)
            if line_match:
                issues.append({"line": int(line_match.group(1)), "msg": "Structural error or missing closure near this line."})

    # Filter out duplicates and keep top 5
    unique_issues = []
    seen_lines = set()
    for iss in issues:
        if iss["line"] not in seen_lines:
            unique_issues.append(iss)
            seen_lines.add(iss["line"])
            
    return unique_issues[:5]

def compiler_node(state: PipelineState) -> dict:
    print(f"\n[Step 6] Compiler (Line-Focused Surgical Repair)")
    p = Path(state["final_latex"])
    model = state["model_name"]
    xelatex_cmd = ["xelatex", "-interaction=nonstopmode", "-synctex=1", p.name]
    
    for r in range(1, 4):
        print(f"  [Round {r}] Compiling...")
        result = subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True, text=True)
        
        # Check for BibTeX
        aux = p.with_suffix(".aux")
        if r == 1 and aux.exists() and "\\citation" in aux.read_text(encoding="utf-8", errors="ignore"):
            print("  - Running BibTeX...")
            subprocess.run(["bibtex", p.stem], cwd=p.parent, capture_output=True)
            result = subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"  ❌ xelatex failed with return code {result.returncode}")
            # Extract and print actual errors from stdout/stderr or log
            log_path = p.with_suffix(".log")
            if log_path.exists():
                log_content = log_path.read_text(encoding="utf-8", errors="ignore")
                # Find lines starting with '!' which are LaTeX errors
                errors = [line for line in log_content.splitlines() if line.startswith("!")]
                if errors:
                    print("  [LaTeX Errors Found]:")
                    for err in errors[:10]: # Show top 10
                        print(f"    {err}")
            else:
                print("  [Output]:")
                print(result.stdout[-500:]) # Show last 500 chars of stdout
        
        source_text = p.read_text(encoding="utf-8")
        # Automatic repair disabled as requested
        """
        issues = _parse_latex_log(p.with_suffix(".log"), source_text)
        
        if not issues:
            print("  ✓ Success")
            break
            
        print(f"  Fixing {len(issues)} issues surgically...")
        source_lines = source_text.splitlines()
        memory = build_memory_prompt()
        
        issues.sort(key=lambda x: x["line"], reverse=True)
        
        for issue in issues:
            ln = issue["line"]
            if 0 < ln <= len(source_lines):
                idx = ln - 1
                start, end = max(0, idx-2), min(len(source_lines), idx+3)
                context = "\n".join(source_lines[start:end])
                
                system = f"Fix the technical LaTeX error in this snippet. Ignore fonts. Output ONLY fixed code.\n{memory}"
                user = f"Error at line {ln}: {issue['msg']}\nSnippet:\n{context}"
                
                fixed = _clean_res(call_llm(model, system, user))
                source_lines[start:end] = fixed.splitlines()
                summarize_fixes([issue], context, fixed, model)
                
        p.write_text("\n".join(source_lines), encoding="utf-8")
        """
        # Just break after standard compilation (and optional BibTeX)
        break
    
    pdf_path = p.with_suffix(".pdf")
    if pdf_path.exists():
        print(f"  ✅ PDF generated: {pdf_path.name}")
    else:
        print(f"  ❌ Failed to generate PDF.")
        
    return {}
