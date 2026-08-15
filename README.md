# SnapTitle
### An OCR, LLM & VLM-Driven Automation Engine for Intelligent Screenshot Indexing

Real-time screenshot understanding, powered by local OCR, LLM & VLM inference.

---

## 📌 Project Overview

**SnapTitle** is a fully local desktop automation engine designed to watch your operating system's screenshot directory and instantly transform raw, obscurely named screenshots into organized, meaningful, and searchable captures.

### 🔒 Core Principles
- **100% Local & Private:** All processing runs entirely on your local machine using local OCR and local AI models via Ollama. No cloud APIs, no external telemetry, and no data ever leaves your computer.
- **Cheap-First, Vision-Fallback Pipeline:** Fast text extraction via OCR for documents/chats/receipts, with lightweight local Vision-Language Model (VLM) fallback for textless diagrams, photos, and icon-only interfaces.
- **Safe & Deterministic Renaming:** Native OS collision prevention, length limits, character sanitization, and timestamp preservation.

---

## 📂 Project Structure (Current Milestone: Phase 0)

```text
SnapTitle/
├── config/
│   ├── __init__.py
│   ├── config.py              # Configuration manager & OS screenshot folder auto-detection
│   └── default_config.yaml    # Application settings (models, timeouts, paths)
├── data/                      # Local data directory
├── src/                       # Source modules (detection, AI pipelines, UI, database)
├── tests/
│   ├── __init__.py
│   └── test_env.py            # Environment & dependency verification test suite
├── .gitignore                 # Git ignore rules for virtualenvs, databases, and artifacts
├── requirements.txt           # Python dependency definitions
└── README.md                  # Project documentation
```

---

## 🚀 Setup & Environment Verification (Phase 0)

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

### 3. Verify Environment
Run the Phase 0 environment verification suite:
```bash
python tests/test_env.py
```

---

## 🗺️ Roadmap & Upcoming Releases

- [x] **Phase 0 — Setup & Environment:** Configuration auto-detection, Tesseract integration, and Ollama connectivity verification.
- [ ] **Phase 1 — Core Detection & Renaming:** Real-time watchdog filesystem observer, cross-platform filename sanitizer, atomic moving, and collision detection. *(Coming Next)*
- [ ] **Phase 2 — OCR + LLM Titling:** Text thresholding, PII credential redaction, and deterministic LLM titling prompt.
- [ ] **Phase 3 — Vision (VLM) Fallback:** Visual captioning for textless screenshots (diagrams, photos, UI icons) with unified LLM formatting.
- [ ] **Phase 4 — Non-Blocking Popup UI:** Floating corner card with thumbnail preview, live edit capability, and auto-dismiss countdown timer.
- [ ] **Phase 5 — Smart Duplicate Resolution:** AI-powered disambiguation to distinguish same-day collisions without plain numeric suffixes.
- [ ] **Phase 6 — Full-Text Search Index & Polish:** SQLite FTS5 database indexer, search CLI, and instant rename undo utility.
