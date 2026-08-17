# SnapTitle
### An OCR, LLM & VLM-Driven Automation Engine for Intelligent Screenshot Indexing

Real-time screenshot understanding, powered by local OCR, LLM & VLM inference.

---

## 📌 Project Overview

**SnapTitle** is a fully local desktop automation engine designed to watch your operating system's screenshot directory and instantly transform raw, obscurely named screenshots into organized, meaningful, and searchable captures.

### 🔒 Core Principles
- **100% Local & Private:** All processing runs entirely on your local machine using local OCR and local AI models via Ollama. No cloud APIs, no external telemetry, and no data ever leaves your computer.
- **Cheap-First, Vision-Fallback Pipeline:** Fast text extraction via OCR for documents, chats, and receipts, with a lightweight local Vision-Language Model (VLM) fallback for textless diagrams, photos, and icon-only interfaces.
- **Safe & Deterministic Renaming:** Native OS collision prevention, length limits, character sanitization, and timestamp preservation.
- **Interactive Popup Notification:** Floating on-screen card with live preview, editable title, and auto-dismiss timer.
- **Full-Text SQLite Search Index:** Historical logging and keyword search across past screenshots and extracted text.

---

## 📂 Project Structure

```text
SnapTitle/
├── config/
│   ├── __init__.py
│   ├── config.py              # Configuration manager & OS screenshot folder auto-detection
│   └── default_config.yaml    # Application settings (models, timeouts, paths)
├── data/                      # Local SQLite database directory
├── src/
│   ├── __init__.py            # Package exports
│   ├── core.py                # Main orchestrator pipeline
│   ├── database.py            # SQLite storage & FTS5 full-text search index
│   ├── llm.py                 # Local LLM prompt engineering & title cleaning
│   ├── naming.py              # Filename sanitization & collision resolution
│   ├── ocr.py                 # Tesseract OCR text extraction
│   ├── popup.py               # Floating on-screen notification & editor UI
│   ├── renamer.py             # Atomic file moving & lock handling
│   ├── vlm.py                 # Vision model image captioning
│   └── watcher.py             # Watchdog filesystem observer
├── tests/
│   ├── __init__.py
│   ├── test_env.py
│   ├── test_detection_and_renaming.py
│   ├── test_ocr_llm_titling.py
│   ├── test_vlm_fallback.py
│   ├── test_popup_ui.py
│   ├── test_smart_duplicate_resolution.py
│   └── test_search_and_database.py
├── .gitignore
├── requirements.txt
├── main.py                    # Application entry point
├── search.py                  # CLI search tool
├── undo.py                    # Rename undo utility
└── README.md
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.11 & 3.13)
- **Tesseract OCR:** 
  - Windows: Installed to standard path or added to `PATH` (e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe`)
  - macOS: `brew install tesseract`
  - Linux: `sudo apt-get install tesseract-ocr`
- **Ollama:**
  - Local AI daemon running locally at `http://127.0.0.1:11434`
  - Required local models:
    ```bash
    ollama pull llama3.2:3b
    ollama pull moondream:latest
    ```

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Sankhyaan/SnapTitle-Autonomous-Screenshot-Indexing-Agent.git
cd SnapTitle-Autonomous-Screenshot-Indexing-Agent

# Install Python dependencies
pip install -r requirements.txt
```

---

## 💻 Usage

### 1. Run Background Automation
```bash
python main.py
```
Take any screenshot using your standard OS shortcut (`Win + PrtScn`, `Win + Shift + S`, or `Cmd + Shift + 4`). SnapTitle will automatically display the preview card, generate the title, and rename the file.

### 2. Search Past Screenshots
Search through historical screenshots by keywords, error codes, invoice IDs, topics, or dates:
```bash
python search.py "kubernetes crashloop"
python search.py "billing invoice"
python search.py --date 2026-08-15
python search.py "docker" --json
python search.py "database" --csv
python search.py --stats
```

### 3. Undo Last Rename
Revert the most recent rename back to its original filename:
```bash
python undo.py
# or
python search.py --undo
```

---

## ⚙️ Configuration & Environment Variables

SnapTitle can be configured via `config/default_config.yaml` or environment variables:

| Variable | Description | Default |
|---|---|---|
| `SNAPTITLE_SCREENSHOTS_DIR` | Custom screenshot directory path | OS Auto-detected |
| `SNAPTITLE_DATABASE_PATH` | SQLite database file location | `data/snaptitle.db` |
| `SNAPTITLE_LLM_MODEL` | Ollama model identifier for text titling | `llama3.2:3b` |
| `SNAPTITLE_VLM_MODEL` | Ollama model identifier for vision captioning | `moondream:latest` |
| `SNAPTITLE_OLLAMA_HOST` | Ollama daemon host URL | `http://127.0.0.1:11434` |
| `SNAPTITLE_SHOW_POPUP` | Enable/disable desktop popup UI (`1`/`0`) | `1` (Enabled) |
| `SNAPTITLE_POPUP_DURATION` | Popup countdown timer in seconds | `5` |
| `SNAPTITLE_TESSERACT_CMD` | Explicit path to Tesseract binary | Auto-detected |

Supported Image Formats: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`, `.tif` (case-insensitive).

---

## 🧪 Running Tests

Run the automated test runner script to verify all 7 project test modules:
```bash
python run_tests.py
```

Or run individual test modules directly:
```bash
python -m unittest tests.test_env
python -m unittest tests.test_detection_and_renaming
python -m unittest tests.test_ocr_llm_titling
python -m unittest tests.test_vlm_fallback
python -m unittest tests.test_popup_ui
python -m unittest tests.test_smart_duplicate_resolution
python -m unittest tests.test_search_and_database
```
