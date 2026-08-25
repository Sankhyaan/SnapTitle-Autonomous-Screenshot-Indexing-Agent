"""SnapTitle Web Demo Server: Lightweight local HTTP server bridging the web visualizer to SQLite FTS5."""

import os
import sys
import time
import json
import sqlite3
import logging
import argparse
import webbrowser
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Project Root
PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DEMO_DIR = PROJECT_ROOT / "web_demo"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("snaptitle.demo_server")


class SnapTitleDemoHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving web_demo static files and SnapTitle REST API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DEMO_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # REST API Routes
        if path == "/api/status":
            self._handle_api_status()
        elif path == "/api/search":
            query_params = parse_qs(parsed.query)
            query = query_params.get("q", [""])[0]
            self._handle_api_search(query)
        elif path == "/api/records":
            self._handle_api_records()
        elif path == "/favicon.ico":
            self._handle_static_file("favicon.ico", "image/x-icon")
        elif path == "/favicon.svg":
            self._handle_static_file("favicon.svg", "image/svg+xml")
        else:
            # Fallback to serving static files from web_demo/
            super().do_GET()

    def _handle_static_file(self, filename: str, content_type: str):
        """Explicitly serve static assets like favicons with correct headers."""
        target = WEB_DEMO_DIR / filename
        if target.exists():
            with open(target, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404, "File not found")

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/analyze":
            self._handle_api_analyze()
        else:
            self.send_error(404, "Endpoint not found")

    def _handle_api_analyze(self):
        """Receive image_path or base64 image and return live Gemini analysis."""
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)
        try:
            req_data = json.loads(post_body.decode("utf-8"))
            image_path_str = req_data.get("image_path", "")
            image_b64 = req_data.get("image_base64", "")
            
            if not image_path_str and not image_b64:
                self._send_json_response({"error": "No image or path provided"}, 400)
                return

            import base64
            import tempfile
            from src.gemini import generate_title_and_caption_with_gemini
            from config.config import load_config

            cfg = load_config()
            target_path = None
            temp_path = None

            if image_path_str:
                p = Path(image_path_str)
                if not p.is_absolute():
                    p = WEB_DEMO_DIR / p
                if p.exists():
                    target_path = p

            if not target_path and image_b64:
                if "," in image_b64:
                    image_b64 = image_b64.split(",")[1]
                temp_path = Path(tempfile.gettempdir()) / f"snaptitle_web_{int(time.time()*1000)}.png"
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(image_b64))
                target_path = temp_path

            if not target_path or not target_path.exists():
                self._send_json_response({"success": False, "error": "Image file could not be resolved"}, 400)
                return

            start_t = time.time()
            res = generate_title_and_caption_with_gemini(
                image_path=target_path,
                api_key=cfg.gemini_api_key,
                model=cfg.gemini_model,
                timeout=8.0,    # short timeout so cascade falls through quickly
                max_retries=1   # one attempt per model before trying next
            )
            elapsed_ms = int((time.time() - start_t) * 1000)

            if temp_path and temp_path.exists():
                temp_path.unlink()

            if res:
                title, content = res
                today_str = datetime.now().strftime('%d-%m-%Y')
                self._send_json_response({
                    "success": True,
                    "title": title,
                    "content": content,
                    "final_filename": f"{title}_{today_str}.png",
                    "date_stamp": today_str,
                    "latency_ms": elapsed_ms
                })
            else:
                self._send_json_response({"success": False, "error": "Gemini inference returned empty response"}, 500)
        except Exception as e:
            logger.error(f"Error in /api/analyze: {e}")
            self._send_json_response({"success": False, "error": str(e)}, 500)

    def _send_json_response(self, data: dict, status_code: int = 200):
        """Send JSON HTTP response with CORS headers."""
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _handle_api_status(self):
        """Return system health and database statistics."""
        db_path = PROJECT_ROOT / "data" / "snaptitle.db"
        db_exists = db_path.exists()
        record_count = 0

        if db_exists:
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM screenshots")
                    record_count = cursor.fetchone()[0]
            except Exception as e:
                logger.warning(f"Error querying SQLite database: {e}")

        payload = {
            "status": "online",
            "service": "SnapTitle Autonomous Indexing Engine",
            "database": {
                "exists": db_exists,
                "path": str(db_path),
                "indexed_records": record_count
            },
            "features": {
                "watchdog_observer": True,
                "tesseract_ocr": True,
                "moondream_vlm": True,
                "llama_titling": True,
                "sqlite_fts5": True
            }
        }
        self._send_json_response(payload)

    def _handle_api_search(self, query: str):
        """Perform SQLite FTS5 search on local database."""
        db_path = PROJECT_ROOT / "data" / "snaptitle.db"
        results = []

        if db_path.exists():
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    if query.strip():
                        # FTS5 search query
                        clean_query = query.replace("'", "''").strip()
                        cursor.execute("""
                            SELECT s.id, s.original_filename, s.final_filename, s.title, 
                                   s.extracted_content, s.capture_date, s.is_reverted
                            FROM screenshots s
                            JOIN screenshots_fts fts ON s.id = fts.rowid
                            WHERE screenshots_fts MATCH ?
                            ORDER BY s.id DESC
                            LIMIT 50
                        """, (f'"{clean_query}"*',))
                    else:
                        cursor.execute("""
                            SELECT id, original_filename, final_filename, title, 
                                   extracted_content, capture_date, is_reverted
                            FROM screenshots
                            ORDER BY id DESC
                            LIMIT 50
                        """)
                    
                    for row in cursor.fetchall():
                        results.append(dict(row))
            except Exception as e:
                logger.warning(f"Search query error: {e}")

        self._send_json_response({"query": query, "total": len(results), "results": results})

    def _handle_api_records(self):
        """Return all historical records."""
        self._handle_api_search("")


def run_server(port: int = 8080, open_browser: bool = True):
    """Start HTTP server. Binds to 0.0.0.0 for cloud deployment compatibility."""
    host = "0.0.0.0"  # bind to all interfaces so cloud platforms can route traffic
    server_address = (host, port)
    
    try:
        httpd = HTTPServer(server_address, SnapTitleDemoHandler)
    except OSError:
        logger.warning(f"Port {port} in use, trying next available port...")
        port += 1
        server_address = (host, port)
        httpd = HTTPServer(server_address, SnapTitleDemoHandler)

    display_url = f"http://127.0.0.1:{port}" if host == "0.0.0.0" else f"http://{host}:{port}"
    logger.info("=" * 60)
    logger.info(f"\U0001f680 SnapTitle Visual Pipeline Demo is LIVE at: {display_url}")
    logger.info(f"\U0001f4c2 Serving directory: {WEB_DEMO_DIR}")
    logger.info("=" * 60)

    if open_browser:
        webbrowser.open(display_url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down demo server.")
        httpd.server_close()


if __name__ == "__main__":
    # Cloud platforms (Render, Railway, Fly.io) inject PORT as an env variable
    default_port = int(os.environ.get("PORT", 8080))
    is_cloud = os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("FLY_APP_NAME")

    parser = argparse.ArgumentParser(description="SnapTitle Interactive Visual Demo Server")
    parser.add_argument("--port", type=int, default=default_port, help="Port to bind server (default: $PORT or 8080)")
    parser.add_argument("--no-browser", action="store_true", default=bool(is_cloud), help="Do not automatically open browser")
    args = parser.parse_args()

    run_server(port=args.port, open_browser=not args.no_browser)
