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
    base_sections = ["MATH_NOTATION", "FORMATTING_RULES", "LABELS", "THEOREMS"]
    
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
            "2. EXCEPTION: You MUST optimize mathematical formulas to be COMPACT (remove all unnecessary spaces between symbols, commas, and operators) even if the original Markdown has spaces.\n"
            "Do NOT add, remove, or rephrase any prose text. Only apply technical LaTeX formatting."
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
    print("\n[Step 1] Classifier & Metadata Extraction")
    full_text = Path(state["markdown_path"]).read_text(encoding="utf-8")
    # Reduced metadata sample to 50k - more than enough for headers, much faster pre-fill
    sample = full_text[:50000] 
    
    print(f"  [Analyzing] Document structure and metadata (50k context)...")
    system = (
        "Analyze the following Markdown document. Provide two pieces of information:\n"
        "1. TYPE: Is this a 'book' or a 'paper'?\n"
        "2. METADATA: Extract TITLE, AUTHOR, and writing DATE (use 'unknown' if not found).\n"
        "Format exactly as: TYPE: ... | TITLE: ... | AUTHOR: ... | DATE: ..."
    )
    res = call_llm(state["model_name"], system, sample, temperature=0, show_thinking=False)
    
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
    tpl = TEMPLATES[state["template_name"]]
    style_prompt = get_style_prompt(state.get("mode", "original"))
    system = f"Convert this Markdown to LaTeX snippet for {state['template_name']} style. {tpl['style_hint']}\n\n{style_prompt}"
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
    tpl = TEMPLATES[state["template_name"]]
    
    template_structure = tpl["preamble"].replace("__TITLE__", state["doc_title"])\
                                        .replace("__AUTHOR__", state.get("doc_author", "Anonymous"))\
                                        .replace("__DATE__", state.get("doc_date", "unknown")) + \
                         tpl["body_wrapper"].replace("__BODY__", "% Your content here")
    
    style_prompt = get_style_prompt(state.get("mode", "original"))
    system = (
        f"Convert this Markdown to a FULL and COMPLETE LaTeX document for the {state['template_name']} style.\n"
        f"You MUST generate the entire document from \\documentclass to \\end{{document}}.\n"
        f"Use the following template structure as your exact base:\n\n"
        f"```latex\n{template_structure}\n```\n\n"
        f"{tpl['style_hint']}\n\n"
        f"{style_prompt}"
    )
    
    print(f"  [Generating] LaTeX document (Processing {len(txt)} chars context)...")
    res = _clean_res(call_llm(state["model_name"], system, txt))
    
    p = Path(state["output_dir"]) / "main.tex"
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

from .cite_tool import extract_citations, search_crossref, search_arxiv, format_bibitem

def assembler_node(state: PipelineState) -> dict:
    print("\n[Step 5] Assembler")
    tpl = TEMPLATES[state["template_name"]]
    output_dir = Path(state["output_dir"])
    sorted_ch = sorted(state["chapter_outputs"], key=lambda x: x["index"])
    
    # 1. Combine body
    body = "\n".join(c["latex_body"] for c in sorted_ch)
    
    # 2. Extract and resolve citations for refs.bib
    all_keys = extract_citations(body)
    bib_entries = []
    
    if all_keys:
        print(f"  - Resolving {len(all_keys)} citations for refs.bib...")
        # Since we don't have full metadata for all keys, we try to find them
        # This is a simplified version. In a real scenario, we'd need more data.
        for key in all_keys:
            # We'll use the key as a query if it looks like a title/author
            # Otherwise, we might need a more sophisticated lookup
            # For now, we'll generate a dummy entry if not found to prevent BibTeX errors
            item = search_crossref(key) or search_arxiv(key)
            if item:
                # Get standard BibTeX if possible
                doi = item.get("DOI")
                from .cite_tool import get_crossref_bibtex
                bib_text = get_crossref_bibtex(doi) if doi else None
                if bib_text:
                    bib_entries.append(bib_text)
                else:
                    # Fallback to manual formatting (simplified BibTeX entry)
                    title = item.get("title", [key])[0]
                    bib_entries.append(f"@article{{{key},\n  title={{{title}}},\n  year={{2024}}\n}}")
            else:
                bib_entries.append(f"@misc{{{key},\n  title={{{key}}},\n  note={{Automatically resolved}}\n}}")
        
        bib_path = output_dir / "refs.bib"
        bib_path.write_text("\n\n".join(bib_entries), encoding="utf-8")
        print(f"  ✓ Generated {bib_path.name}")

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
    """Extract errors with line numbers and find lines for citations."""
    if not log_path.exists(): return []
    log_content = log_path.read_text(encoding="utf-8", errors="ignore")
    lines = source_text.splitlines()
    issues = []
    for m in re.finditer(r'(?:\./)?\S+\.tex:(\d+):\s*(.+)', log_content):
        issues.append({"line": int(m.group(1)), "msg": m.group(2).strip()})
    return issues[:5]

def compiler_node(state: PipelineState) -> dict:
    print(f"\n[Step 6] Compiler (Line-Focused Surgical Repair)")
    p = Path(state["final_latex"])
    model = state["model_name"]
    xelatex_cmd = ["xelatex", "-interaction=nonstopmode", "-synctex=1", p.name]
    
    for r in range(1, 4):
        print(f"  [Round {r}] Compiling...")
        subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True)
        
        # Check for BibTeX
        aux = p.with_suffix(".aux")
        if r == 1 and aux.exists() and "\\citation" in aux.read_text(encoding="utf-8", errors="ignore"):
            print("  - Running BibTeX...")
            subprocess.run(["bibtex", p.stem], cwd=p.parent, capture_output=True)
            subprocess.run(xelatex_cmd, cwd=p.parent, capture_output=True)
        
        source_text = p.read_text(encoding="utf-8")
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
    
    pdf_path = p.with_suffix(".pdf")
    if pdf_path.exists():
        print(f"  ✅ PDF generated: {pdf_path.name}")
    else:
        print(f"  ❌ Failed to generate PDF.")
        
    return {}
