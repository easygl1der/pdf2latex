"""
pdf2latex — PDF → LaTeX 自动转换工具
用法: python main.py input.pdf --template amsart --model minimax
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from scripts.config import TEMPLATES, MODELS, OUTPUT_ROOT
from scripts.transcribe import mineru_convert
from scripts.pipeline import build_graph


def main():
    parser = argparse.ArgumentParser(description="PDF → LaTeX 自动转换")
    parser.add_argument("pdf",       help="输入 PDF 路径")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()),
                        default="amsart", help="LaTeX 模板（默认 amsart）")
    parser.add_argument("--model",    choices=list(MODELS.keys()),
                        default="minimax", help="LLM 模型（默认 minimax）")
    parser.add_argument("--list-templates", action="store_true",
                        help="列出所有可用模板")
    args = parser.parse_args()

    if args.list_templates:
        print("\n可用模板：")
        for k, v in TEMPLATES.items():
            print(f"  {k:12s} — {v['desc']}")
        return

    print("=" * 60)
    print(f"  pdf2latex")
    print(f"  PDF:      {args.pdf}")
    print(f"  模板:     {args.template} — {TEMPLATES[args.template]['desc']}")
    print(f"  模型:     {args.model} ({MODELS[args.model]['model']})")
    print("=" * 60)

    markdown_path = mineru_convert(args.pdf)

    pdf_stem = Path(args.pdf).stem
    output_dir = str(OUTPUT_ROOT / pdf_stem)

    graph = build_graph()
    graph.invoke({
        "pdf_path":        args.pdf,
        "markdown_path":   markdown_path,
        "template_name":   args.template,
        "model_name":      args.model,
        "doc_title":       "",
        "doc_type":        "",
        "output_dir":      output_dir,
        "chapters":        [],
        "chapter_outputs": [],
        "reviewed_outputs": [],
        "final_latex":     "",
    })

    print("\n" + "=" * 60)
    print(f"  完成！")
    print(f"  输出目录: output/{pdf_stem}/")
    print(f"  主文件:   output/{pdf_stem}/main.tex")
    print(f"  各章节:   output/{pdf_stem}/chapter-*.tex")
    print("=" * 60)


if __name__ == "__main__":
    main()
