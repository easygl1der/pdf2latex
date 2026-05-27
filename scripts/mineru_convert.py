"""MinerU PDF to Markdown Converter.

This script implements MinerUConverter as defined in the project core instructions.
It leverages `extract_pdf_markdown` from `core.mineru_client` to perform the transcription,
and automatically applies the `pdf_fix` post-processing rules.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
from core.mineru_client import extract_pdf_markdown


class MinerUConverter:
    """A wrapper converter class that handles reading PDF files, uploading them
    to MinerU Agent API, polling for results, and returning the fixed markdown.
    """

    def __init__(self) -> None:
        pass

    async def convert_async(self, pdf_path: str | Path) -> str:
        """Convert a PDF file to Markdown asynchronously.

        Args:
            pdf_path: Path to the target PDF file.

        Returns:
            The fixed markdown string.
        """
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        pdf_bytes = path.read_bytes()
        last_error: list[str] = []

        async def progress_cb(step: str, msg: str) -> None:
            print(f"[{step}] {msg}")

        markdown = await extract_pdf_markdown(
            pdf_bytes,
            filename=path.name,
            progress=progress_cb,
            last_error=last_error,
        )

        if markdown is None:
            error_details = "; ".join(last_error) if last_error else "Unknown error"
            raise RuntimeError(f"MinerU conversion failed: {error_details}")

        return markdown

    def convert(self, pdf_path: str | Path) -> str:
        """Convert a PDF file to Markdown synchronously.

        Args:
            pdf_path: Path to the target PDF file.

        Returns:
            The fixed markdown string.
        """
        return asyncio.run(self.convert_async(pdf_path))


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe PDF to Markdown using MinerU")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Path to the output Markdown file (default: same as input with .md extension)")

    args = parser.parse_args()

    input_path = Path(args.pdf_path)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".md")

    print(f"Transcribing {input_path} using MinerU...")
    converter = MinerUConverter()
    try:
        md_content = converter.convert(input_path)
        output_path.write_text(md_content, encoding="utf-8")
        print(f"Successfully saved transcribed markdown to {output_path}")
    except Exception as e:
        print(f"Error during transcription: {e}", file=sys.stderr)
        sys.exit(1)
