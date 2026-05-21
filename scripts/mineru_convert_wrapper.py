from .mineru_convert import MinerUConverter
from .config import MINERU_API_KEY
import os
from pathlib import Path

def mineru_convert_to_md(pdf_path: str, output_dir: Path) -> str:
    """Wrapper to use MinerUConverter in main.py"""
    converter = MinerUConverter(MINERU_API_KEY)
    result = converter.convert(
        input_path=pdf_path,
        output_dir=str(output_dir / "mineru_output"),
        verbose=True
    )
    if result["success"]:
        return result["output_file"]
    else:
        raise RuntimeError(f"MinerU conversion failed: {result.get('error', 'Unknown error')}")
