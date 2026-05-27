"""
MinerU PDF → Markdown Transcription (with Cache)
"""

import shutil
from pathlib import Path


def mineru_convert(pdf_path: str) -> str:
    """Returns the Markdown file path, same PDF reads cache directly on second call.

    Transcription results are saved under transcript/<stem>/:
      <stem>.md        — Main Markdown
      images/          — All images (preserved)
      *.json           — MinerU metadata (preserved)
    """
    print(f"\n[Step 1] MinerU Transcription: {pdf_path}")

    pdf_stem = Path(pdf_path).stem
    project_root = Path(__file__).parent.parent
    transcript_dir = project_root / "transcript" / pdf_stem
    transcript_dir.mkdir(parents=True, exist_ok=True)

    md_path = transcript_dir / f"{pdf_stem}.md"
    if md_path.exists():
        print(f"  [Cache] Using existing transcription result: {md_path}")
        images_dir = transcript_dir / "images"
        if images_dir.exists():
            img_count = len(list(images_dir.iterdir()))
            print(f"  [Cache] images/ directory: {img_count} files")
        return str(md_path)

    token_file = Path(__file__).parent.parent / ".mineru_token"
    if not token_file.exists():
        raise FileNotFoundError(
            f"MinerU Token file not found: {token_file}\n"
            "Please copy the token from ~/.claude/skills/mineru-pdf-converter/references/mineru-token.md"
        )

    from .mineru_convert import MinerUConverter, load_token
    token = load_token(str(token_file))
    converter = MinerUConverter(token)

    print(f"  Uploading file: {pdf_path}")
    batch_id = converter.upload_file(
        pdf_path,
        model="vlm",
        language="en",
        enable_formula=True,
        enable_table=True,
    )
    print(f"  batch_id={batch_id}, waiting for completion...")

    result = converter.poll_batch_result(batch_id, max_wait=600)
    result_url = result["full_zip_url"]

    # Download and extract to transcript_dir (preserves images/ etc.)
    print(f"  Downloading and extracting result...")
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
            raise FileNotFoundError(f"No .md file found in transcription result: {transcript_dir}")

    char_count = len(md_path.read_text(encoding="utf-8"))
    print(f"  Completed: {char_count} characters → {md_path}")

    images_dir = transcript_dir / "images"
    if images_dir.exists():
        img_count = len(list(images_dir.iterdir()))
        print(f"  images/ directory: {img_count} image files")

    return str(md_path)
