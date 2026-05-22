# pdf2latex-lite

A simplified, high-performance PDF to LaTeX conversion pipeline using **LangGraph**, **MinerU**, and **Ollama**.

This is the `lite` branch, designed for speed and reliability by focusing on a direct conversion path without complex repair loops.

## ✨ Key Features (Lite Version)
- **Direct Pipeline:** Streamlined LangGraph orchestration: Classify → Split → Convert → Assemble → Compile.
- **MinerU Integration:** High-quality PDF parsing into Markdown.
- **Ollama Powered:** optimized for `nemotron-3-super` and other local LLMs via OpenAI-compatible API.
- **Surgical Simplicity:** Removed redundant nodes and complex error-correction loops for easier debugging and faster execution.

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **Ollama** (Running with `nemotron-3-super` or similar)
- **XeLaTeX** (For PDF compilation)
- **MinerU API Key** (Get it from [Open-MinerU](https://mineru.org/))

### 2. Installation
```bash
# Clone the repository (if you haven't already)
git clone https://github.com/easygl1der/pdf2latex.git
cd pdf2latex
git checkout lite

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Setup
Set your API keys:
```bash
export MINERU_API_KEY='your_mineru_key'
# Optional: if using OpenAI instead of Ollama
# export OPENAI_API_KEY='your_openai_key'
```

### 4. Usage
Run the conversion directly:
```bash
python main.py input.pdf --template amsart --model ollama
```

**Options:**
- `--template`: `amsart` (default), `article`, `ctexart`, `beamer`.
- `--model`: `ollama` (default), `openai`.
- `--mode`: `notes` (summary style), `original` (faithful conversion).

## 🛠 Architecture
The `lite` branch uses a simplified LangGraph:
1. **Classifier**: Determines if the doc is a 'book' or 'paper'.
2. **Supervisor**: Splits the Markdown into manageable chapters.
3. **Writer**: Converts each chapter to LaTeX in parallel.
4. **Assembler**: Combines snippets into a valid LaTeX document.
5. **Compiler**: Runs `xelatex` for a final PDF check.

## 📄 License
MIT
