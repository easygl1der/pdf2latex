"""
pdf2latex — PDF to LaTeX Automatic Conversion Tool (Ollama + MinerU + LangGraph)
Usage: python main.py input.pdf --template amsart --model ollama --mode notes
"""

import argparse
import os
import sys
from pathlib import Path

from scripts.config import TEMPLATES, MODELS, MINERU_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY
from scripts.mineru_convert_wrapper import mineru_convert_to_md
from scripts.pipeline import build_graph
from scripts.llm import call_llm

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
        for m in missing:
            print(f"  export {m}='your_key_here'")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="PDF to LaTeX Automatic Conversion Tool")
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()),
                        default="amsart", help="LaTeX template (default: amsart)")
    parser.add_argument("--model", choices=list(MODELS.keys()),
                        default="ollama", help=f"LLM selection (default: ollama). Available: {', '.join(MODELS.keys())}")
    parser.add_argument("--custom-model", help="Specify a custom model name for the selected provider (e.g. --model ollama --custom-model deepseek-v3)")
    parser.add_argument("--mode", choices=["habit", "original"],
                        default="original", help="Conversion mode: habit (Your Writing Habits/Stein Style) | original (Strict Reproduction, Default)")
    parser.add_argument("--list-templates", action="store_true", help="List all available templates")
    parser.add_argument("--force-clean", action="store_true", help="Force re-run of Markdown cleaning even if cache exists")
    parser.add_argument("--clean-model", default="deepseek-v4", help="Model to use for Markdown cleaning (default: deepseek-v4)")
    args = parser.parse_args()

    if args.list_templates:
        print("\nAvailable Templates:")
        for k, v in TEMPLATES.items():
            print(f"  {k:12s} — {v['desc']}")
        return

    check_keys(args.model)

    # Allow overriding the model string in the selected provider
    if args.custom_model:
        MODELS[args.model]["model"] = args.custom_model
        print(f"  [Config] Overriding {args.model} provider with custom model: {args.custom_model}")

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ File not found: {args.pdf}")
        sys.exit(1)

    print("=" * 60)
    print(f"  pdf2latex (Model: {args.model})")
    print(f"  PDF:    {pdf_path.name}")
    print(f"  Template: {args.template} — {TEMPLATES[args.template]['desc']}")
    print(f"  Mode:     {args.mode}")
    print("=" * 60)

    # Step 1: MinerU PDF to Markdown
    print(f"\n[Step 0] MinerU Transcription")
    output_root = Path("output")
    cache_dir = output_root / pdf_path.stem
    cache_file = cache_dir / f"{pdf_path.stem}.md"

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

    # Step 1: Markdown Cleaning (DeepSeek or Other)
    print(f"\n[Step 1] Markdown Cleaning & Math Standardizing ({args.clean_model})")
    cleaned_path = Path(markdown_path).with_suffix(".cleaned.md")
    
    if cleaned_path.exists() and not args.force_clean:
        print(f"  [Cache Hit] Using existing cleaned Markdown: {cleaned_path.name}")
        markdown_path = str(cleaned_path)
    else:
        if args.force_clean:
            print(f"  [Force] Re-cleaning Markdown as requested...")
        raw_md = Path(markdown_path).read_text(encoding="utf-8")
        
        clean_system = (
            "### ROLE: PRECISION MARKDOWN CLEANER\n"
            "Your task is to sanitize Markdown while PROTECTING ALL IMAGES.\n\n"
            "### [TOP PRIORITY] ABSOLUTE IMAGE PRESERVATION:\n"
            "1. NEVER delete, skip, or modify any Markdown image syntax: ![](images/...)\n"
            "2. If an image tag is inside an HTML container (like <details> or <table>) that you are removing, you MUST RESCUE the image tag and place it in the output exactly where it was contextually.\n\n"
            "### CLEANING RULES:\n"
            "1. REMOVE all CSS code, <style> tags, or inline style='...' attributes.\n"
            "2. STRIP HTML TAGS: Remove tags like <details>, <summary>, <div>, <span>. KEEP the meaningful text, code blocks, AND images inside them.\n"
            "3. COMPACT MATH: Ensure ZERO SPACES inside math formulas. Example: $a+b=c$ (NOT $a + b = c$).\n"
            "5. UNICODE TO LATEX: Convert Unicode symbols (σ, α, β, Δ, ≈, ≠, ≤) to LaTeX commands ($\\sigma$, $\\alpha$, etc.) wrapped in $.\n"
            "6. CITATION PROTECTION: DO NOT wrap numeric citations like [18], [1-5], or [10, 12] in math delimiters. Keep them as plain text.\n"
            "7. AGGRESSIVE WRAPPING: Wrap all plain-text variables like 'y=0' into '$y=0$'.\n"

            "6. PROOF QED: Ensure every 'Proof.' section ends with a '□' symbol.\n\n"
            "### OUTPUT:\n"
            "Output ONLY the cleaned Markdown text. If you delete an image tag, you have FAILED the mission."
        )
        
        try:
            # Use specified model for cleaning
            cleaned_md = call_llm(args.clean_model, clean_system, raw_md, temperature=0.0)
            
            # Save cleaned version
            cleaned_path.write_text(cleaned_md, encoding="utf-8")
            markdown_path = str(cleaned_path)
            print(f"  ✓ Markdown cleaned and saved: {cleaned_path.name}")
        except Exception as e:
            print(f"  [Warning] Markdown cleaning failed, proceeding with raw output: {e}")

    # Step 2: Run LangGraph Pipeline
    content_list_path = str(cache_dir / f"{pdf_path.stem}_content_list.json")
    if not os.path.exists(content_list_path):
        # Fallback to search if name differs or has version suffix
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
        "doc_type":        "",
        "output_dir":      "",
        "chapters":        [],
        "chapter_outputs": [],
        "final_latex":     "",
    }

    print("\n[Pipeline] Starting LangGraph orchestration...")
    try:
        result = graph.invoke(initial_state)
        print("\n" + "=" * 60)
        print("  ✅  Task Complete!")
        print(f"  Output Dir:  {result['output_dir']}")
        print(f"  Main File:   {result['final_latex']}")
        print(f"  Modular:     {Path(result['output_dir']) / 'main_modular.tex'}")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Pipeline execution error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
