import argparse
import sys
import subprocess
from pathlib import Path

from core.config import TEMPLATES, MINERU_API_KEY, OUTPUT_ROOT
from core.llm import get_provider
from core.converter import NextGenConverter
from scripts.mineru_convert_wrapper import mineru_convert_to_md

def main():
    parser = argparse.ArgumentParser(description="pdf2latex (Next-Gen) - Fast PDF to LaTeX")
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()), default="article")
    parser.add_argument("--model", choices=["ollama", "codex"], default="ollama")
    parser.add_argument("--mode", choices=["notes", "original"], default="notes")
    args = parser.parse_args()

    # 1. Setup paths
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ File not found: {args.pdf}")
        sys.exit(1)

    output_dir = OUTPUT_ROOT / pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"  pdf2latex (Next-Gen) | Model: {args.model}")
    print(f"  PDF: {pdf_path.name} | Mode: {args.mode}")
    print("=" * 60)

    # 2. Transcription (Step 0)
    print(f"\n[Step 0] MinerU Transcription")
    cache_file = output_dir / f"{pdf_path.stem}.md"
    if cache_file.exists():
        print(f"  [Cache Hit] Using existing Markdown: {cache_file}")
        markdown_path = str(cache_file)
    else:
        try:
            markdown_path = mineru_convert_to_md(str(pdf_path), output_dir)
            print(f"  ✓ Transcription complete: {markdown_path}")
        except Exception as e:
            print(f"❌ MinerU failed: {e}")
            sys.exit(1)

    # 3. Conversion
    try:
        import time
        start_conv = time.time()
        provider = get_provider(args.model)
        converter = NextGenConverter(provider, args.template, args.mode)
        main_tex = converter.convert(markdown_path, output_dir)
        conv_duration = time.time() - start_conv
        
        # 4. Final Verification (Step 4)
        print(f"\n[Step 4] Compilation Check")
        start_comp = time.time()
        cmd = ["xelatex", "-interaction=nonstopmode", "-halt-on-error", main_tex.name]
        print(f"  Running: {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True)
        comp_duration = time.time() - start_comp
        
        if proc.returncode == 0:
            print(f"\n✅  SUCCESS!")
            print(f"    Conversion: {conv_duration:.2f}s | Compilation: {comp_duration:.2f}s")
            print(f"    Output: {output_dir / 'main.pdf'}")
        else:
            print(f"\n⚠️  Compilation Warning (Code {proc.returncode})")
            print(f"    Check logs in: {output_dir / 'main.log'}")
            # Optional: Add surgical repair here in next iteration

    except Exception as e:
        print(f"\n❌ Execution Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
