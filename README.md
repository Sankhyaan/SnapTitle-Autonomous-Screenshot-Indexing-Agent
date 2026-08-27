# SnapTitle 📸
### Autonomous Multimodal Screenshot Indexing & Semantic Renaming Agent

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AI Provider](https://img.shields.io/badge/AI%20Provider-Gemini%20%7C%20Ollama-orange.svg)](https://ai.google.dev/)
[![Search](https://img.shields.io/badge/Search-SQLite%20FTS5-green.svg)](https://www.sqlite.org/fts5.html)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

**SnapTitle** is an autonomous desktop background agent that intercepts screenshot creation events in real time, extracts visual and OCR context using **Google Gemini Multimodal Vision** or **Local Ollama Models**, intelligently generates clean semantic filenames, and indexes all visual text into a local **SQLite FTS5 Full-Text Search** database.

---

## ✨ Key Features

- ⚡ **Autonomous Watchdog Interception:** Attaches seamlessly to your OS screenshot folder (`Win + PrtScn`, `Win + Shift + S`, Snipping Tool, macOS `Cmd + Shift + 4`).
- 🧠 **Dual AI Provider Architecture:**
  - **Cloud Multimodal (Google Gemini 2.5 Flash / Flash Lite):** Instant visual layout, OCR, and semantic naming with automated multi-model rate-limit failover.
  - **100% Local & Private (Tesseract + Ollama):** Runs completely offline using Llama 3.2 and Moondream / LLaVA with zero external telemetry.
- 🔀 **Dual-Path Routing:** Automatically evaluates text density to choose between high-speed OCR-LLM extraction and zero-shot Vision-Language scene understanding.
- 🎨 **Floating Tkinter HUD Notification:** Displays real-time thumbnail preview, countdown timer, editable title field, and auto-dismiss confirm.
- 🔍 **SQLite FTS5 Deep Retrieval Engine:** Search through historical screenshots by keywords, invoice numbers, error codes, chat dialogue, or dates.
- 🌐 **Interactive Web Simulator & Visualizer:** Built-in localhost UI for drag-and-drop live testing, stage-by-stage node inspection, and retrieval exploring.
- ⏪ **Non-Destructive Reversals:** One-click instant undo to restore any file back to its original OS timestamp filename.

---

## 📂 Project Architecture

```text
SnapTitle/
├── config/
│   ├── config.py              # Configuration loader & OS screenshot folder auto-detection
│   └── default_config.yaml    # Application settings (AI provider, models, timeouts, paths)
├── data/                      # Local SQLite database directory
│   └── snaptitle.db           # SQLite database with FTS5 virtual tables
├── src/
│   ├── core.py                # Main orchestrator service & background daemon
│   ├── gemini.py              # Google Gemini 2.5 Flash Multimodal Vision engine
│   ├── ocr.py                 # Tesseract OCR text extraction
│   ├── llm.py                 # Local LLM titling & sanitization
│   ├── vlm.py                 # Local Vision-Language Model captioning
│   ├── watcher.py             # Watchdog filesystem observer
│   ├── naming.py              # Snake_case sanitization & duplicate disambiguation
│   ├── renamer.py             # Atomic file moving & lock handling
│   ├── popup.py               # Desktop Tkinter HUD notification
│   └── database.py            # SQLite storage & FTS5 full-text search index
├── web_demo/                  # Interactive visual simulation workspace
│   ├── index.html             # Web visualizer markup
│   ├── styles.css             # Glassmorphism dark-mode UI
│   ├── app.js                 # Real-time WebSocket/REST orchestrator
│   └── images/                # Scenario presets
├── tests/                     # 7 comprehensive test suites
├── demo_server.py             # Local HTTP REST server for web visualizer
├── main.py                    # Autonomous background daemon entrypoint
├── search.py                  # CLI search and database management tool
├── undo.py                    # CLI undo utility
├── run_tests.py               # Test runner script
└── requirements.txt           # Python dependencies
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.11 & 3.13)
- *(Optional for Cloud Mode)*: [Google AI Studio Gemini API Key](https://aistudio.google.com/)
- *(Optional for 100% Local Mode)*: [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and [Ollama](https://ollama.com/)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Sankhyaan/SnapTitle-Autonomous-Screenshot-Indexing-Agent.git
cd SnapTitle-Autonomous-Screenshot-Indexing-Agent

# Install Python dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### 3. Configuration & Screenshot Folder Setup
SnapTitle is designed to work seamlessly out-of-the-box on any computer:

- 🌟 **Automatic OS Detection (Zero-Config):** By default, SnapTitle automatically detects the current user's default screenshot folder across **Windows** (`Pictures/Screenshots` or active OneDrive registry path), **macOS** (`Desktop` or `Pictures/Screenshots`), and **Linux** (`$XDG_PICTURES_DIR/Screenshots`).
- 📁 **Custom Folder per User (`.env`):** To watch a specific custom folder on your machine without affecting other teammates or Git commits, edit your local `.env`:
  ```env
  SNAPTITLE_SCREENSHOTS_DIR="C:/Users/YourName/Pictures/Screenshots"
  ```
- ⚡ **CLI Runtime Flag:** You can also pass a custom directory directly when launching:
  ```powershell
  python main.py --watch-dir "D:/MyCustomScreenshots"
  ```

---

## 💻 Terminal Commands & Walkthrough

### 1. Run the Autonomous Background Daemon
Runs in the background and watches your desktop screenshot folder continuously:
```powershell
python main.py
```
*Take any screenshot (`Win + PrtScn` or `Win + Shift + S`). SnapTitle will automatically detect it, run Gemini vision analysis, pop up the desktop HUD, rename the file, and index the content!*

---

### 2. Run the Interactive Web Visualizer
Launch the interactive web-based testing studio:
```powershell
python demo_server.py --port 8080
```
Open **`http://127.0.0.1:8080`** in your browser to test preset scenarios, upload custom screenshots, and inspect the real-time node flow.

---

### 3. Retrieve Screenshots from Terminal (`search.py`)

`search.py` queries the SQLite FTS5 index across full OCR text, VLM scene descriptions, and filenames:

#### 🔹 Basic Keyword & Content Search:
```powershell
python search.py "invoice"
python search.py "kubernetes crashloop"
python search.py "bgp"
python search.py "142.50"
python search.py "exit code 137"
```

#### 🔹 Date & Date Range Filtering:
```powershell
# Search by exact date
python search.py --date 2026-08-24

# Search within a date range
python search.py --start-date 2026-08-01 --end-date 2026-08-24
```

#### 🔹 View Recent Captures:
```powershell
# View last 10 processed screenshots
python search.py --recent

# View last 5 processed screenshots
python search.py --recent 5
```

#### 🔹 Export Results (JSON / CSV):
```powershell
python search.py "docker" --json
python search.py "database" --csv
```

#### 🔹 Database Stats & Health Checks:
```powershell
# View total count of indexed screenshots
python search.py --stats

# Run full system dependency check
python search.py --check

# Backup SQLite database
python search.py --backup "data/snaptitle_backup.db"
```

---

### 4. Undo the Last Rename
To instantly revert the most recent rename back to its original OS filename:
```powershell
python undo.py
# or
python search.py --undo
```

---

## ⚙️ Configuration

Configure via `config/default_config.yaml` or environment variables:

| Variable | Description | Default |
|---|---|---|
| `SNAPTITLE_AI_PROVIDER` | AI Provider: `gemini` (Cloud) or `ollama` (Local) | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API Key | Set in config or env |
| `SNAPTITLE_GEMINI_MODEL` | Primary Gemini model identifier | `gemini-2.5-flash` |
| `SNAPTITLE_SCREENSHOTS_DIR` | Custom screenshot folder path | OS Auto-detected |
| `SNAPTITLE_DATABASE_PATH` | SQLite database file destination | `data/snaptitle.db` |
| `SNAPTITLE_SHOW_POPUP` | Enable/disable desktop HUD popup (`1`/`0`) | `1` (Enabled) |
| `SNAPTITLE_POPUP_DURATION` | HUD auto-save countdown in seconds | `5` |
| `SNAPTITLE_LLM_MODEL` | Ollama model for local text titling | `llama3.2:3b` |
| `SNAPTITLE_VLM_MODEL` | Ollama model for local vision captioning | `moondream:latest` |

---

## 🧪 Running Automated Tests

Run the full automated test suite covering all 7 modules:
```powershell
python run_tests.py
```

Or execute specific unit tests:
```powershell
python -m unittest tests.test_search_and_database
python -m unittest tests.test_detection_and_renaming
python -m unittest tests.test_smart_duplicate_resolution
```

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for details.
