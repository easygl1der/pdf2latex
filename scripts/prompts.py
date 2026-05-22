"""
Prompt Loader Utility: Loads prompts from the prompts/ directory and handles templating.
"""

from pathlib import Path
from typing import Dict

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(name: str, variables: Dict[str, str] = None) -> str:
    """Load a prompt file and replace {{variable}} placeholders."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    
    text = path.read_text(encoding="utf-8")
    
    if variables:
        for k, v in variables.items():
            placeholder = "{{" + k + "}}"
            text = text.replace(placeholder, str(v))
            
    return text
