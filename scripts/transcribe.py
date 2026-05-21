"""
MinerU PDF → Markdown 转录（带缓存）
"""

import shutil
from pathlib import Path


def mineru_convert(pdf_path: str) -> str:
    """返回 Markdown 文件路径，同一 PDF 第二次调用直接读缓存。

    转录结果保存在 transcript/<stem>/ 下：
      <stem>.md        — 主 Markdown
      images/          — 所有图片（保留）
      *.json           — MinerU 元数据（保留）
    """
    print(f"\n[Step 1] MinerU 转录: {pdf_path}")

    pdf_stem = Path(pdf_path).stem
    project_root = Path(__file__).parent.parent
    transcript_dir = project_root / "transcript" / pdf_stem
    transcript_dir.mkdir(parents=True, exist_ok=True)

    md_path = transcript_dir / f"{pdf_stem}.md"
    if md_path.exists():
        print(f"  [缓存] 使用已有转录结果: {md_path}")
        images_dir = transcript_dir / "images"
        if images_dir.exists():
            img_count = len(list(images_dir.iterdir()))
            print(f"  [缓存] images/ 目录: {img_count} 个文件")
        return str(md_path)

    token_file = Path(__file__).parent.parent / ".mineru_token"
    if not token_file.exists():
        raise FileNotFoundError(
            f"未找到 MinerU Token 文件: {token_file}\n"
            "请从 ~/.claude/skills/mineru-pdf-converter/references/mineru-token.md 复制 token"
        )

    from .mineru_convert import MinerUConverter, load_token
    token = load_token(str(token_file))
    converter = MinerUConverter(token)

    print(f"  上传文件: {pdf_path}")
    batch_id = converter.upload_file(
        pdf_path,
        model="vlm",
        language="en",
        enable_formula=True,
        enable_table=True,
    )
    print(f"  batch_id={batch_id}，等待完成...")

    result = converter.poll_batch_result(batch_id, max_wait=600)
    result_url = result["full_zip_url"]

    # 下载并解压到 transcript_dir（保留 images/ 等所有文件）
    print(f"  下载并解压结果...")
    converter.download_result(result_url, str(transcript_dir))

    # full.md → <stem>.md
    full_md = transcript_dir / "full.md"
    if full_md.exists():
        full_md.rename(md_path)
    else:
        md_files = list(transcript_dir.glob("*.md"))
        if md_files:
            md_files[0].rename(md_path)
        else:
            raise FileNotFoundError(f"转录结果中未找到 .md 文件: {transcript_dir}")

    char_count = len(md_path.read_text(encoding="utf-8"))
    print(f"  完成: {char_count} 字符 → {md_path}")

    images_dir = transcript_dir / "images"
    if images_dir.exists():
        img_count = len(list(images_dir.iterdir()))
        print(f"  images/ 目录: {img_count} 个图片文件")

    return str(md_path)
