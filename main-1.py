#!/usr/bin/env python3
"""
main-1.py — PDF to LaTeX Segmented & Hierarchical Conversion Pipeline
Incorporates:
1. Hierarchy & Atomic Persistence (Book -> Chapter -> Block, Breakpoint Resumption)
2. Two-Pass Generation (Outline Pass + Fill Pass)
3. Context & Bridging (Bridge Text & Previous Ending Injection)
4. Async Queue & Real-Time Lego-Style State Management
"""

import argparse
import os
import sys
import re
import json
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any

# Ensure project root is in path
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.config import TEMPLATES, MODELS, MINERU_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, OUTPUT_ROOT
from scripts.mineru_convert_wrapper import mineru_convert_to_md
from scripts.llm import call_llm
from scripts.error_memory import build_memory_prompt
from scripts.nodes import get_style_prompt

# Ensure output root exists
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# 1. Physical Level Task Splitting & Hierarchy
# ═══════════════════════════════════════════════════════════════

def parse_markdown_to_hierarchy(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Parses Markdown text into a structured hierarchy:
    Book -> Chapters -> Blocks
    Splits by H1 headers (#) first, then by H2 headers (##), 
    and subdivides large paragraphs if they exceed length limits.
    """
    # Split by H1 headers (# )
    chapters_raw = re.split(r'^#\s+', markdown_text, flags=re.MULTILINE)
    
    chapters = []
    ch_idx = 1
    
    # If there is content before the first H1, treat it as Chapter 0 / Introduction
    first_part = chapters_raw[0].strip()
    if first_part:
        # Check if there is actual content
        lines = first_part.splitlines()
        title = "Preamble / Introduction"
        chapters.append({
            "index": 0,
            "title": title,
            "blocks": split_chapter_to_blocks(first_part)
        })
        
    for raw_ch in chapters_raw[1:]:
        if not raw_ch.strip():
            continue
        
        lines = raw_ch.splitlines()
        title = lines[0].strip()
        ch_body = "\n".join(lines[1:])
        
        chapters.append({
            "index": ch_idx,
            "title": title,
            "blocks": split_chapter_to_blocks(ch_body)
        })
        ch_idx += 1
        
    return chapters


def split_chapter_to_blocks(ch_body: str) -> List[Dict[str, Any]]:
    """Splits chapter body into logical blocks based on H2 headers and paragraph lengths."""
    blocks = []
    subsections_raw = re.split(r'^##\s+', ch_body, flags=re.MULTILINE)
    
    blk_idx = 1
    
    # Text before the first H2 header
    intro_part = subsections_raw[0].strip()
    if intro_part:
        blocks.extend(split_text_by_length(intro_part, "Introduction", blk_idx))
        blk_idx = len(blocks) + 1
        
    for sub_raw in subsections_raw[1:]:
        if not sub_raw.strip():
            continue
        
        sub_lines = sub_raw.splitlines()
        sub_title = sub_lines[0].strip()
        sub_body = "\n".join(sub_lines[1:])
        
        header_prefix = f"## {sub_title}\n\n"
        sub_blocks = split_text_by_length(sub_body, sub_title, blk_idx, header_prefix)
        blocks.extend(sub_blocks)
        blk_idx = len(blocks) + 1
        
    return blocks


def split_text_by_length(text: str, name_base: str, start_idx: int, prefix: str = "") -> List[Dict[str, Any]]:
    """Splits a body of text into smaller blocks if it exceeds length limits (e.g. 3000 chars)."""
    blocks = []
    
    # If the text is short enough, keep it as a single block
    if len(text) <= 3000:
        blocks.append({
            "index": start_idx,
            "title": name_base,
            "content": prefix + text
        })
        return blocks
        
    # Otherwise split by paragraphs
    paragraphs = text.split("\n\n")
    curr_block_paragraphs = []
    curr_len = 0
    sub_idx = 1
    
    for p in paragraphs:
        if not p.strip():
            continue
        curr_block_paragraphs.append(p)
        curr_len += len(p)
        
        if curr_len > 2500:
            header_prefix = prefix if sub_idx == 1 else ""
            blocks.append({
                "index": start_idx + sub_idx - 1,
                "title": f"{name_base} (Part {sub_idx})",
                "content": header_prefix + "\n\n".join(curr_block_paragraphs)
            })
            sub_idx += 1
            curr_block_paragraphs = []
            curr_len = 0
            
    if curr_block_paragraphs:
        header_prefix = prefix if sub_idx == 1 else ""
        blocks.append({
            "index": start_idx + sub_idx - 1,
            "title": f"{name_base} (Part {sub_idx})",
            "content": header_prefix + "\n\n".join(curr_block_paragraphs)
        })
        
    return blocks


# ═══════════════════════════════════════════════════════════════
# 2. Atomic Persistence & Breakpoint Resumption
# ═══════════════════════════════════════════════════════════════

class BookStateManager:
    """Manages persistence of the translation state to disk (atomic updates)."""
    def __init__(self, doc_name: str):
        self.doc_name = doc_name
        self.output_dir = OUTPUT_ROOT / doc_name
        self.chunks_dir = self.output_dir / "chunks"
        self.state_file = self.output_dir / "pipeline_state.json"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        
        self.state = {
            "doc_name": doc_name,
            "doc_title": doc_name.replace("_", " ").title(),
            "doc_author": "Anonymous",
            "doc_date": "unknown",
            "chapters": []
        }
        
    def load_or_init(self, hierarchy: List[Dict[str, Any]]):
        """Loads state from disk if it exists, otherwise initializes it from hierarchy."""
        if self.state_file.exists():
            try:
                disk_state = json.loads(self.state_file.read_text(encoding="utf-8"))
                # Merge logic: Verify if structure matches roughly
                if disk_state.get("doc_name") == self.doc_name and disk_state.get("chapters"):
                    self.state = disk_state
                    print(f"  [State] Loaded existing breakpoint state from {self.state_file.name}")
                    return
            except Exception as e:
                print(f"  [Warning] Failed to parse state file, reinitializing: {e}")
                
        # Initialize standard state
        print("  [State] Initializing new pipeline state file...")
        self.state["chapters"] = []
        for ch in hierarchy:
            ch_entry = {
                "index": ch["index"],
                "title": ch["title"],
                "blocks": []
            }
            for blk in ch["blocks"]:
                ch_entry["blocks"].append({
                    "index": blk["index"],
                    "title": blk["title"],
                    "state": "PENDING",
                    "latex_file": None,
                    "error_msg": None
                })
            self.state["chapters"].append(ch_entry)
        self.save()
        
    def save(self):
        """Atomically saves the state to disk."""
        temp_file = self.state_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.state_file.exists():
            self.state_file.unlink()
        temp_file.rename(self.state_file)
        
    def update_block_state(self, ch_idx: int, blk_idx: int, status: str, latex_file: str = None, error_msg: str = None):
        """Updates the state of a block and saves atomically."""
        for ch in self.state["chapters"]:
            if ch["index"] == ch_idx:
                for blk in ch["blocks"]:
                    if blk["index"] == blk_idx:
                        blk["state"] = status
                        if latex_file:
                            blk["latex_file"] = latex_file
                        if error_msg:
                            blk["error_msg"] = error_msg
                        break
        self.save()

    def get_block_status(self, ch_idx: int, blk_idx: int) -> Dict[str, Any]:
        """Gets status of a block."""
        for ch in self.state["chapters"]:
            if ch["index"] == ch_idx:
                for blk in ch["blocks"]:
                    if blk["index"] == blk_idx:
                        return blk
        return {"state": "PENDING", "latex_file": None, "error_msg": None}


# ═══════════════════════════════════════════════════════════════
# 3. Two-Pass Generation Mode (Outline + Fill) & Context Bridging
# ═══════════════════════════════════════════════════════════════

def run_outline_pass(model_name: str, text: str) -> Dict[str, Any]:
    """Pass 1: Generates a JSON outline for long text blocks."""
    system = (
        "### ROLE: SCIENTIFIC DOCUMENT ANALYSER\n"
        "Your task is to analyze the provided Markdown text and split it into a structured outline "
        "for LaTeX conversion to prevent generation limits.\n\n"
        "### OUTPUT FORMAT (MANDATORY):\n"
        "You MUST output ONLY a valid JSON object matching the schema below. Do NOT wrap in ```json or add any explanation!\n"
        "{\n"
        "  \"intro\": \"Short summary of introduction / key context.\",\n"
        "  \"subsections\": [\n"
        "    {\n"
        "      \"heading\": \"Subsection Title\",\n"
        "      \"key_concept\": \"Specific math formulas or text concepts to focus on.\",\n"
        "      \"estimated_chars\": 500\n"
        "    }\n"
        "  ],\n"
        "  \"takeaway\": \"Concluding summary or transition note.\"\n"
        "}"
    )
    user = f"Please outline this content:\n\n{text}"
    
    try:
        raw_res = call_llm(model_name, system, user, temperature=0.0)
        # Parse JSON
        match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw_res.strip())
    except Exception as e:
        print(f"      [Warning] Outline Pass JSON parse failed: {e}. Falling back to default outline.")
        # Fallback outline
        return {
            "intro": "General introduction and context.",
            "subsections": [{"heading": "Content Analysis", "key_concept": "Full text translation", "estimated_chars": len(text)}],
            "takeaway": "Transition to the next segment."
        }


def run_fill_pass(model_name: str, template_name: str, outline: Dict[str, Any], sub_idx: int, 
                  sub_info: Dict[str, Any], full_raw_text: str, prev_markdown_context: str) -> str:
    """Pass 2: Fills in LaTeX for a specific outline subsection."""
    tpl = TEMPLATES[template_name]
    style_prompt = get_style_prompt("original")
    error_memory = build_memory_prompt()
    
    system = (
        f"### ROLE: SENIOR LATEX TYPESETTING EXPERT\n"
        f"You are typesetting a scientific document subsection into the {template_name} style.\n\n"
        f"### CONTEXT SUMMARY:\n"
        f"- Section Intro: {outline.get('intro')}\n"
        f"- Target Heading: {sub_info['heading']}\n"
        f"- Key Concept/Math: {sub_info['key_concept']}\n"
        f"- Ending of previous Markdown text (for smooth transition): {prev_markdown_context if prev_markdown_context else 'None'}\n\n"
        f"### GUIDELINES & STYLE:\n{tpl['style_hint']}\n{style_prompt}\n\n"
        f"### LEARNED ERROR PREVENTION:\n{error_memory if error_memory else 'No previous errors.'}\n\n"
        f"### CRITICAL CONSTRAINTS:\n"
        f"1. MATHEMATICAL FORMULAS MUST BE COMPACT: Remove ALL unnecessary spaces between symbols, operators, and indices (e.g. $a+b=c$, NOT $a + b = c$).\n"
        f"2. CONTINUITY: Write a natural transition paragraph bridging from the previous block if necessary. Do NOT wrap citations in math.\n"
        f"3. OUTPUT FORMAT: Return ONLY the raw LaTeX code inside a single block. Do not add \\begin{{document}} or preamble."
    )
    
    user = (
        f"Source Context Snippet:\n{full_raw_text[:2000]}...\n\n"
        f"Please translate the subsection '{sub_info['heading']}' focusing on the concept: {sub_info['key_concept']}.\n"
        f"Output ONLY LaTeX."
    )
    
    res = call_llm(model_name, system, user, temperature=0.0)
    return clean_latex_block(res)


def run_single_pass(model_name: str, template_name: str, text: str, prev_markdown_context: str) -> str:
    """Performs single-pass direct translation for smaller blocks."""
    tpl = TEMPLATES[template_name]
    style_prompt = get_style_prompt("original")
    error_memory = build_memory_prompt()
    
    system = (
        f"### ROLE: SENIOR LATEX TYPESETTING EXPERT\n"
        f"Convert this markdown block into beautiful, clean LaTeX for {template_name} style.\n\n"
        f"### CONTEXT BRIDGE:\n"
        f"- Ending of previous Markdown text (bridge naturally from this): {prev_markdown_context if prev_markdown_context else 'None'}\n\n"
        f"### GUIDELINES & STYLE:\n{tpl['style_hint']}\n{style_prompt}\n\n"
        f"### LEARNED ERROR PREVENTION:\n{error_memory if error_memory else 'No previous errors.'}\n\n"
        f"### CRITICAL CONSTRAINTS:\n"
        f"1. COMPACT MATH: All math formulas MUST have ZERO SPACES (e.g., $a+b=c$).\n"
        f"2. ENVIRONMENT RULES: Use aligned/cases instead of array for standard equations.\n"
        f"3. OUTPUT: Return ONLY raw LaTeX content. Do not output \\begin{{document}} or package imports."
    )
    user = f"Please convert this Markdown text:\n\n{text}"
    
    res = call_llm(model_name, system, user, temperature=0.0)
    return clean_latex_block(res)


def clean_latex_block(res: str) -> str:
    """Extracts raw LaTeX content from code block delimiters."""
    match = re.search(r'```(?:latex)?\n?(.*?)\n?```', res, re.DOTALL)
    if match:
        return match.group(1).strip()
    res = re.sub(r'```(?:latex)?\n?', '', res)
    res = re.sub(r'\n?```', '', res)
    return res.strip()


# ═══════════════════════════════════════════════════════════════
# 4. Async Parallel Generation & State Management
# ═══════════════════════════════════════════════════════════════

class LegoVisualizer:
    """Prints a beautiful real-time dashboard of block generation statuses."""
    def __init__(self, chapters: List[Dict[str, Any]]):
        self.chapters = chapters
        self.block_status = {}
        for ch in chapters:
            for blk in ch["blocks"]:
                self.block_status[(ch["index"], blk["index"])] = "PENDING"
                
    def update(self, ch_idx: int, blk_idx: int, status: str):
        self.block_status[(ch_idx, blk_idx)] = status
        self.render()
        
    def render(self):
        # Clear screen/jump cursor option omitted for terminal logging safety, just print elegant lines
        print("\n=== 🧱 BLOCK TRANSLATION DASHBOARD ===")
        for ch in self.chapters:
            line_parts = []
            for blk in ch["blocks"]:
                stat = self.block_status[(ch["index"], blk["index"])]
                if stat == "READY":
                    icon = "✅"
                elif stat == "GENERATING":
                    icon = "🚀"
                elif stat == "ERROR":
                    icon = "❌"
                else:
                    icon = "⏳"
                line_parts.append(f"{icon} Blk {ch['index']}.{blk['index']}")
            print(f"📖 Ch {ch['index']}: {ch['title'][:25]:25s} | " + "  ".join(line_parts))
        print("======================================\n", flush=True)


async def translate_block_task(
    ch_idx: int, blk_idx: int, block_content: str, prev_markdown_context: str,
    model_name: str, template_name: str, state_mgr: BookStateManager, 
    executor: ThreadPoolExecutor, visualizer: LegoVisualizer
):
    """Executes a block translation task (Outline + Fill or Direct) in the background thread pool."""
    loop = asyncio.get_running_loop()
    
    # 1. Update status to Generating
    visualizer.update(ch_idx, blk_idx, "GENERATING")
    state_mgr.update_block_state(ch_idx, blk_idx, "GENERATING")
    
    try:
        # Determine if we should use Two-Pass or Single-Pass
        use_two_pass = len(block_content) > 2000
        
        if use_two_pass:
            print(f"    [Block {ch_idx}.{blk_idx}] Content > 2000 chars. Running Two-Pass Outline+Fill...")
            
            # Step A: Outline Pass
            outline = await loop.run_in_executor(
                executor, run_outline_pass, model_name, block_content
            )
            
            # Step B: Fill Pass for subsections
            filled_sections = []
            current_prev_context = prev_markdown_context
            
            for i, sub in enumerate(outline.get("subsections", [])):
                print(f"      [Fill] Subsection {i+1}/{len(outline['subsections'])}: {sub['heading']}...")
                sub_latex = await loop.run_in_executor(
                    executor, run_fill_pass, model_name, template_name,
                    outline, i+1, sub, block_content, current_prev_context
                )
                filled_sections.append(sub_latex)
                current_prev_context = sub_latex[-300:] if len(sub_latex) > 300 else sub_latex
                
            latex_res = "\n\n".join(filled_sections)
        else:
            # Single Pass
            latex_res = await loop.run_in_executor(
                executor, run_single_pass, model_name, template_name, block_content, prev_markdown_context
            )
            
        # Write chunk output file
        chunk_file_name = f"chunks/chapter_{ch_idx}_block_{blk_idx}.tex"
        chunk_file_path = state_mgr.output_dir / chunk_file_name
        chunk_file_path.write_text(latex_res, encoding="utf-8")
        
        # Save to state and complete
        state_mgr.update_block_state(ch_idx, blk_idx, "READY", latex_file=chunk_file_name)
        visualizer.update(ch_idx, blk_idx, "READY")
        
    except Exception as e:
        print(f"    ❌ [Error] Block {ch_idx}.{blk_idx} failed: {e}")
        state_mgr.update_block_state(ch_idx, blk_idx, "ERROR", error_msg=str(e))
        visualizer.update(ch_idx, blk_idx, "ERROR")
        raise e


async def run_async_pipeline(
    hierarchy: List[Dict[str, Any]], model_name: str, template_name: str, state_mgr: BookStateManager
):
    """Schedules and executes block translations fully in parallel simultaneously."""
    visualizer = LegoVisualizer(hierarchy)
    
    # Check what's already completed in the state
    for ch in hierarchy:
        for blk in ch["blocks"]:
            stat = state_mgr.get_block_status(ch["index"], blk["index"])
            visualizer.update(ch["index"], blk["index"], stat["state"])
            
    # Gather pending/failed blocks
    pending_tasks = []
    for ch in hierarchy:
        for blk in ch["blocks"]:
            stat = state_mgr.get_block_status(ch["index"], blk["index"])
            if stat["state"] != "READY":
                pending_tasks.append((ch["index"], blk["index"], blk["content"]))
                
    if not pending_tasks:
        print("  🎉 All blocks are already completed! Skipping translation.")
        return
        
    print(f"  [Parallel] Launching {len(pending_tasks)} translations simultaneously in parallel!")
    
    # Setup Thread Pool Executor with large thread pool for complete parallel execution
    executor = ThreadPoolExecutor(max_workers=max(len(pending_tasks), 10))
    
    # Static lookup for previous markdown block content to feed context (enables true parallel execution)
    def get_prev_block_markdown(ch_idx: int, blk_idx: int) -> str:
        flat_list = []
        for c in hierarchy:
            for b in c["blocks"]:
                flat_list.append((c["index"], b["index"], b["content"]))
        
        try:
            # Map index positions
            pos_list = [(x[0], x[1]) for x in flat_list]
            curr_pos = pos_list.index((ch_idx, blk_idx))
            if curr_pos > 0:
                _, _, prev_content = flat_list[curr_pos - 1]
                return prev_content[-300:] if len(prev_content) > 300 else prev_content
        except ValueError:
            pass
        return ""

    async def translate_single_block(ch_idx: int, blk_idx: int, content: str):
        prev_ctx = get_prev_block_markdown(ch_idx, blk_idx)
        try:
            await translate_block_task(
                ch_idx, blk_idx, content, prev_ctx,
                model_name, template_name, state_mgr, executor, visualizer
            )
        except Exception:
            pass

    # Launch all tasks concurrently in parallel!
    tasks = [
        asyncio.create_task(translate_single_block(ch_idx, blk_idx, content))
        for ch_idx, blk_idx, content in pending_tasks
    ]
    
    await asyncio.gather(*tasks)
    executor.shutdown()


# ═══════════════════════════════════════════════════════════════
# 5. Final Assembly & Compilation
# ═══════════════════════════════════════════════════════════════

def assemble_book(state_mgr: BookStateManager, template_name: str) -> Path:
    """Assembles all READY blocks in order into the final main.tex."""
    print("\n[Step 5] Final Assembly")
    tpl = TEMPLATES[template_name]
    
    # Read metadata
    title = state_mgr.state.get("doc_title", "Compiled Document")
    author = state_mgr.state.get("doc_author", "Anonymous")
    date_val = state_mgr.state.get("doc_date", "unknown")
    
    body_parts = []
    
    # Sort and iterate
    for ch in sorted(state_mgr.state["chapters"], key=lambda x: x["index"]):
        ch_latex_blocks = []
        
        # Heading for Chapter if H1 is not Preamble
        if ch["index"] > 0:
            ch_latex_blocks.append(f"\n\\section{{{ch['title']}}}\\label{{section:ch_{ch['index']}}}\n")
            
        for blk in sorted(ch["blocks"], key=lambda x: x["index"]):
            if blk["state"] == "READY" and blk["latex_file"]:
                file_path = state_mgr.output_dir / blk["latex_file"]
                if file_path.exists():
                    ch_latex_blocks.append(file_path.read_text(encoding="utf-8"))
            else:
                ch_latex_blocks.append(f"\n% [Missing Block {ch['index']}.{blk['index']}: {blk['title']}]\n")
                
        body_parts.append("\n".join(ch_latex_blocks))
        
    full_body = "\n\n".join(body_parts)
    
    # Compile template
    final_latex = tpl["preamble"].replace("__TITLE__", title)\
                                 .replace("__AUTHOR__", author)\
                                 .replace("__DATE__", date_val) + \
                  tpl["body_wrapper"].replace("__BODY__", full_body)
                  
    out_file = state_mgr.output_dir / "main.tex"
    out_file.write_text(final_latex, encoding="utf-8")
    print(f"  ✓ Successfully assembled all blocks into {out_file.name}")
    return out_file


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="pdf2latex main-1.py — Segmented Conversion with Breakpoints")
    parser.add_argument("input_path", help="Path to input PDF or Markdown (.md) file")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()), 
                        default="amsart", help="LaTeX template (default: amsart)")
    parser.add_argument("--model", choices=list(MODELS.keys()), 
                        default="deepseek-v4", help=f"LLM selection (default: deepseek-v4). Available: {', '.join(MODELS.keys())}")
    parser.add_argument("--custom-model", help="Specify a custom model name for the selected provider")
    parser.add_argument("--force-reparse", action="store_true", help="Force rebuilding the state hierarchy from scratch")
    args = parser.parse_args()

    # Determine input type
    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)
        
    doc_name = input_path.stem
    output_dir = OUTPUT_ROOT / doc_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    markdown_path = None
    
    # If input is a PDF, convert it to MD first (Step 0)
    if input_path.suffix.lower() == ".pdf":
        print(f"\n[Step 0] PDF to Markdown Transcription")
        md_cache_file = output_dir / f"{doc_name}.md"
        if md_cache_file.exists():
            print(f"  [Cache Hit] Using existing transcript: {md_cache_file.name}")
            markdown_path = md_cache_file
        else:
            try:
                markdown_path = Path(mineru_convert_to_md(str(input_path), output_dir))
                print(f"  ✓ Transcription complete: {markdown_path.name}")
            except Exception as e:
                print(f"❌ PDF Transcription failed: {e}")
                sys.exit(1)
    else:
        markdown_path = input_path
        
    # Read Markdown content
    print(f"\n[Step 1] Loading and Parsing Markdown Hierarchy")
    raw_md = markdown_path.read_text(encoding="utf-8")
    
    # Parse Markdown
    hierarchy = parse_markdown_to_hierarchy(raw_md)
    print(f"  ✓ Document parsed: {len(hierarchy)} chapters extracted.")
    for ch in hierarchy:
        print(f"    - Ch {ch['index']}: '{ch['title']}' containing {len(ch['blocks'])} blocks.")
        
    # Initialize State Manager
    state_mgr = BookStateManager(doc_name)
    if args.force_reparse:
        print("  [Force] Resetting state hierarchy from scratch...")
        if state_mgr.state_file.exists():
            state_mgr.state_file.unlink()
            
    state_mgr.load_or_init(hierarchy)
    
    # Configure model override if provided
    if args.custom_model:
        MODELS[args.model]["model"] = args.custom_model
        print(f"  [Config] Overriding model provider '{args.model}' with custom model: {args.custom_model}")
        
    # Step 3: Run Segmented Async Pipeline
    print(f"\n[Step 2] Executing Segmented LaTeX Conversion Pipeline (Model: {args.model})")
    asyncio.run(run_async_pipeline(hierarchy, args.model, args.template, state_mgr))
    
    # Step 4: Final Assembly
    assembled_file = assemble_book(state_mgr, args.template)
    
    # Show summary
    print("\n" + "=" * 60)
    print("  🎉 Segmented Translation & Assembly Complete!")
    print(f"  Project Location: {state_mgr.output_dir}")
    print(f"  Assembled LaTeX:  {assembled_file}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
