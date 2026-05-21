"""
pdf2latex — PDF to LaTeX Automatic Conversion Tool (Ollama + MinerU + LangGraph)
Usage: python main.py input.pdf --template amsart --model ollama --mode notes
"""

import argparse
import os
import sys
from pathlib import Path

from scripts.config import TEMPLATES, MINERU_API_KEY, OPENAI_API_KEY
from scripts.mineru_convert_wrapper import mineru_convert_to_md
from scripts.pipeline import build_graph

def check_keys(selected_model: str):
    """Check if mandatory API Keys are configured based on the selected model."""
    missing = []
    if not MINERU_API_KEY:
        missing.append("MINERU_API_KEY")
    
    if selected_model == "openai" and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    
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
    parser.add_argument("--model", choices=["openai", "ollama"],
                        default="ollama", help="LLM selection (default: ollama)")
    parser.add_argument("--mode", choices=["notes", "original"],
                        default="notes", help="Conversion mode: notes (Learning Notes) | original (Fidelity)")
    parser.add_argument("--list-templates", action="store_true", help="List all available templates")
    args = parser.parse_args()

    if args.list_templates:
        print("\nAvailable Templates:")
        for k, v in TEMPLATES.items():
            print(f"  {k:12s} — {v['desc']}")
        return

    check_keys(args.model)

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
    cache_file = cache_dir / "mineru_output" / f"{pdf_path.stem}.md"

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

    # Step 2: Run LangGraph Pipeline
    graph = build_graph()
    initial_state = {
        "pdf_path":        str(pdf_path),
        "markdown_path":   markdown_path,
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
