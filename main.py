import argparse
import sys
import os
from pathlib import Path
from scripts.pipeline import build_graph

def main():
    parser = argparse.ArgumentParser(description="PDF to LaTeX Converter (LangGraph Edition)")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--model", default="nemotron-3-super:cloud", help="LLM model to use")
    parser.add_argument("--mode", default="original", choices=["original", "notes"], help="Conversion mode")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"Error: PDF file not found at {args.pdf_path}")
        sys.exit(1)

    # Initial State
    initial_state = {
        "pdf_path": str(Path(args.pdf_path).absolute()),
        "model_name": args.model,
        "mode": args.mode,
        "chapter_outputs": [],
        "chapters": []
    }

    print("🚀 Starting PDF to LaTeX Pipeline...")
    graph = build_graph()
    
    # Run the graph
    # Note: Using stream() or invoke() depending on preference.
    # invoke() is simpler for a final script.
    graph.invoke(initial_state)

    print("\n✅ Pipeline execution complete.")

if __name__ == "__main__":
    main()
