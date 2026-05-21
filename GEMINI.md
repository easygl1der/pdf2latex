# Project Instructions: pdf2latex

## Core Mandates
- **Language:** All code, comments, docstrings, and LLM prompts MUST be written in English.
- **Conversion Engine:** Use `MinerUConverter` from `scripts/mineru_convert.py` for all PDF-to-Markdown conversions.
- **Architecture:** Maintain the LangGraph-based pipeline for document structure analysis, chapter-wise LaTeX conversion, and final assembly.
- **LLM Integration:** Use Ollama (Nemotron-3-Super) via the OpenAI-compatible interface for all reasoning tasks.
- **Execution Rule:** Do NOT run `python main.py` directly inside the Gemini CLI. The user will run it externally.

## Workflows
1. **PDF Conversion:** Convert PDF to Markdown using MinerU cloud API. Handles large PDFs by splitting/merging.
2. **Structure Analysis:** Use a supervisor node with thinking mode enabled to partition the document into chapters.
3. **Parallel Processing:** Convert each chapter to LaTeX in parallel using specialized writer agents.
4. **Validation:** Each LaTeX snippet must be reviewed by a retriever node for formatting correctness.
5. **Assembly:** Final assembly into both single-file and modular LaTeX documents.
