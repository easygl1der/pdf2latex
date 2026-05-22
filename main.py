"""
pdf2latex — PDF to LaTeX Automatic Conversion Tool (Ollama + MinerU + LangGraph)
Usage: python main.py input.pdf --template amsart --model ollama --mode notes
"""

import argparse
import os
import sys
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from scripts.config import TEMPLATES, MODELS, MINERU_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY
from scripts.mineru_convert_wrapper import mineru_convert_to_md
from scripts.pipeline import build_graph
from scripts.llm import call_llm
from scripts.prompts import load_prompt

def check_keys(selected_model: str):
    """Check if mandatory API Keys are configured based on the selected model."""
    missing = []
    if not MINERU_API_KEY:
        missing.append("MINERU_API_KEY")
    
    if selected_model == "openai" and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    
    if selected_model == "deepseek" and not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    
    if missing:
        print(f"❌ Missing mandatory environment variables: {', '.join(missing)}")
        print("Please run in your terminal:")
        for k in missing:
            print(f"  export {k}='your_key_here'")
        sys.exit(1)

def split_markdown(text: str, max_chunk_size: int = 5000) -> list:
    """Split markdown into logical chunks by headers or size."""
    # Try splitting by major headers first
    chunks = []
    # Find positions of H1 or H2 headers
    header_matches = list(re.finditer(r'^#{1,2}\s+', text, re.MULTILINE))
    
    if not header_matches:
        # Fallback to simple size split if no headers found
        for i in range(0, len(text), max_chunk_size):
            chunks.append(text[i:i+max_chunk_size])
        return chunks

    last_pos = 0
    current_chunk = ""
    
    for match in header_matches:
        start = match.start()
        # If current chunk is getting too big, push it
        if len(current_chunk) + (start - last_pos) > max_chunk_size and current_chunk:
            chunks.append(current_chunk)
            current_chunk = ""
        
        current_chunk += text[last_pos:start]
        last_pos = start
        
    current_chunk += text[last_pos:]
    chunks.append(current_chunk)
    return [c for c in chunks if c.strip()]

def main():
    parser = argparse.ArgumentParser(description="pdf2latex — PDF to LaTeX Conversion")
    parser.add_argument("pdf", help="Path to input PDF file")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()), 
                        default="amsart", help="LaTeX template (default: amsart)")
    parser.add_argument("--model", choices=list(MODELS.keys()), 
                        default="ollama", help=f"LLM selection (default: ollama). Available: {', '.join(MODELS.keys())}")
    parser.add_argument("--custom-model", help="Specify a custom model name for the selected provider (e.g. --model openai --custom-model gpt-4-turbo)")
    parser.add_argument("--mode", choices=["habit", "original"],
                        default="original", help="Conversion mode: habit (Your Writing Habits/Stein Style) | original (Strict Reproduction, Default)")
    parser.add_argument("--list-templates", action="store_true", help="List all available templates")
    parser.add_argument("--force-clean", action="store_true", help="Force re-run of Markdown cleaning even if cache exists")
    parser.add_argument("--clean-model", default="deepseek-v4", help="Model to use for Markdown cleaning (default: deepseek-v4)")
    
    args = parser.parse_args()

    if args.list_templates:
        print("\nAvailable Templates:")
        for k, v in TEMPLATES.items():
            print(f"  - {k}: {v['desc']}")
        sys.exit(0)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ File not found: {args.pdf}")
        sys.exit(1)

    check_keys(args.model)

    # Allow overriding the model string in the selected provider
    if args.custom_model:
        MODELS[args.model]["model"] = args.custom_model
        print(f"  [Config] Overriding {args.model} provider with custom model: {args.custom_model}")

    print("=" * 60)
    print(f"  pdf2latex (Model: {args.model})")
    print(f"  PDF:    {pdf_path.name}")
    print(f"  Template: {args.template} — {TEMPLATES[args.template]['desc']}")
    print(f"  Mode:     {args.mode}")
    print("=" * 60)

    # Output management
    cache_dir = Path("output") / pdf_path.stem
    cache_file = cache_dir / f"{pdf_path.stem}.md"
    
    # Step 0: Transcription
    print(f"\n[Step 0] MinerU Transcription")
    if cache_file.exists():
        print(f"  [Cache Hit] Skipping API call, reading {cache_file}")
        markdown_path = str(cache_file)
    else:
        try:
            markdown_path = mineru_convert_to_md(str(pdf_path), cache_dir)
            print(f"  ✓ Transcription complete: {markdown_path}")
        except Exception as e:
            print(f"❌ MinerU conversion failed: {e}")
            sys.exit(1)

    # Step 1: Markdown Cleaning (Parallelized)
    print(f"\n[Step 1] Markdown Cleaning & Math Standardizing ({args.clean_model})")
    cleaned_path = Path(markdown_path).with_suffix(".cleaned.md")
    
    if cleaned_path.exists() and not args.force_clean:
        print(f"  [Cache Hit] Using existing cleaned Markdown: {cleaned_path.name}")
        markdown_path = str(cleaned_path)
    else:
        if args.force_clean:
            print(f"  [Force] Re-cleaning Markdown as requested...")
        
        raw_text = Path(markdown_path).read_text(encoding="utf-8")
        chunks = split_markdown(raw_text)
        print(f"  [Parallel] Document split into {len(chunks)} chunks for cleaning.")
        
        clean_system = load_prompt("cleaning_system")
        
        def clean_chunk_task(idx_data):
            idx, text = idx_data
            try:
                print(f"    - Cleaning chunk {idx+1}/{len(chunks)}...")
                return call_llm(args.clean_model, clean_system, text, temperature=0.0)
            except Exception as e:
                print(f"    [Error] Chunk {idx+1} failed: {e}")
                return text # Fallback to original text for this chunk
        
        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                cleaned_chunks = list(executor.map(clean_chunk_task, enumerate(chunks)))
            
            cleaned_md = "\n\n".join(cleaned_chunks)
            cleaned_path.write_text(cleaned_md, encoding="utf-8")
            markdown_path = str(cleaned_path)
            print(f"  ✓ Markdown cleaned and saved: {cleaned_path.name}")
        except Exception as e:
            print(f"  [Warning] Parallel cleaning failed: {e}")

    # Step 2: Run LangGraph Pipeline
    content_list_path = str(cache_dir / f"{pdf_path.stem}_content_list.json")
    if not os.path.exists(content_list_path):
        found = list(cache_dir.glob("*content_list*.json"))
        if found:
            content_list_path = str(found[0])
            print(f"  [Config] Found content list: {Path(content_list_path).name}")
        else:
            print(f"  [Warning] Content list JSON not found in {cache_dir}. Image analysis will be limited.")
            content_list_path = ""

    graph = build_graph()
    initial_state = {
        "pdf_path":        str(pdf_path),
        "markdown_path":   markdown_path,
        "content_list_path": content_list_path,
        "template_name":   args.template,
        "model_name":      args.model,
        "mode":            args.mode,
        "doc_title":       "",
        "doc_author":      "",
        "doc_date":        "",
        "output_dir":      "",
        "skeleton":        "",
        "chapters":        [],
        "chapter_outputs": [],
        "final_latex":     "",
    }

    print("\n[Pipeline] Starting LangGraph orchestration...")
    try:
        result = graph.invoke(initial_state)
        print("\n" + "=" * 60)
        print("  ✅  Task Complete!")
        print(f"  Output Dir:  {result.get('output_dir')}")
        print(f"  Main File:   {result.get('final_latex')}")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Pipeline execution error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
