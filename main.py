import subprocess
import sys
from pathlib import Path

from core.pdf_fix import fix_all


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout)

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


def fix_markdown(md_path):
    if not md_path.is_file():
        raise SystemExit(f"找不到 Markdown 文件: {md_path}")

    raw_md = md_path.read_text(encoding="utf-8")
    fixed_md = fix_all(raw_md)
    md_path.write_text(fixed_md, encoding="utf-8")

    print(f"Markdown 已修复: {md_path}")


def main():
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
    else:
        pdf_path = Path(input("请输入 PDF 路径: ").strip())

    if not pdf_path.is_file():
        raise SystemExit(f"找不到 PDF 文件: {pdf_path}")

    name = pdf_path.stem
    md_path = Path("output") / name / f"{name}.md"
    tex_path = Path("output") / name / f"{name}.tex"

    if md_path.is_file() and md_path.stat().st_size > 0:
        print(f"已找到 MinerU 转录结果，跳过转录: {md_path}")
    else:
        run_command(["bash", "./run_mineru.sh", str(pdf_path)])

    fix_markdown(md_path)

if __name__ == "__main__":
    main()
