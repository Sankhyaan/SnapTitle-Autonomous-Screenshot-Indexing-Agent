"""SnapTitle Search CLI: Fast full-text search across historical screenshots and OCR/VLM content."""

import os
import sys
import json
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager
from config.config import load_config

# Safe ANSI Color Helpers
USE_COLOR = sys.stdout.isatty() and (os.environ.get("TERM") != "dumb")
CYAN = "\033[96m" if USE_COLOR else ""
GREEN = "\033[92m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
MAGENTA = "\033[95m" if USE_COLOR else ""
DIM = "\033[90m" if USE_COLOR else ""
BOLD = "\033[1m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""


def main():
    parser = argparse.ArgumentParser(
        description="SnapTitle Full-Text Screenshot Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python search.py "error 404"
  python search.py "invoice"
  python search.py "kubernetes crashloop" --limit 10
  python search.py --date 2026-08-15
  python search.py "docker" --json
  python search.py --stats
  python search.py --undo
        """
    )
    parser.add_argument("query", nargs="*", help="Search keywords or phrase")
    parser.add_argument("--limit", type=int, default=15, help="Maximum number of results to display (default: 15)")
    parser.add_argument("--date", type=str, default=None, help="Filter screenshots by capture date (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--stats", action="store_true", help="Show total count of indexed screenshots")
    parser.add_argument("--undo", action="store_true", help="Undo the most recent screenshot rename")

    args = parser.parse_args()
    config = load_config()
    db = DatabaseManager(config.database_path)

    if args.stats:
        total_count = db.get_screenshot_count()
        if args.json:
            print(json.dumps({"total_screenshots": total_count, "database_path": str(config.database_path)}, indent=2))
        else:
            print("=" * 60)
            print(f"  {BOLD}SnapTitle Database Statistics{RESET}")
            print("=" * 60)
            print(f"  Database Path      : {config.database_path}")
            print(f"  Indexed Screenshots: {GREEN}{BOLD}{total_count}{RESET}")
            print("=" * 60)
        return

    if args.undo:
        success, msg, current_p, restored_p = db.undo_last_rename()
        if args.json:
            print(json.dumps({
                "success": success,
                "message": msg,
                "current_path": str(current_p) if current_p else None,
                "restored_path": str(restored_p) if restored_p else None
            }, indent=2))
            return

        if success:
            print(f"\n{GREEN}{BOLD}[SUCCESS]{RESET} {msg}")
            if restored_p:
                print(f"  Restored Path: {restored_p}")
        else:
            print(f"\n{YELLOW}[INFO]{RESET} {msg}")
        return

    # Date-only search
    if args.date and not args.query:
        results = db.get_screenshots_by_date(args.date, limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
            return

        print("=" * 70)
        print(f"  {BOLD}SnapTitle Screenshots for Date:{RESET} '{CYAN}{args.date}{RESET}'")
        print("=" * 70)
        if not results:
            print(f"No screenshots found for date '{args.date}'.")
            return

        print(f"Found {GREEN}{BOLD}{len(results)}{RESET} screenshot(s):\n")
        for i, r in enumerate(results, 1):
            file_path = Path(r["file_path"])
            exists_tag = f" {GREEN}[EXISTS]{RESET}" if file_path.exists() else f" {YELLOW}[MOVED/DELETED]{RESET}"
            print(f"[{BOLD}{i}{RESET}] {CYAN}{BOLD}{r['final_filename']}{RESET}{exists_tag}")
            print(f"    {BOLD}Title   :{RESET} {r['title']}")
            print(f"    {BOLD}Date    :{RESET} {GREEN}{r['capture_date']}{RESET} {DIM}| Original: {r['original_filename']}{RESET}")
            print(f"    {BOLD}Path    :{RESET} {DIM}{r['file_path']}{RESET}")
            print(f"{DIM}{'-' * 70}{RESET}")
        return

    query_str = " ".join(args.query).strip()
    if not query_str:
        if args.json:
            print(json.dumps([]))
        else:
            print(f"{YELLOW}Usage:{RESET} python search.py <search terms>")
            print("Try: python search.py \"npm error\", python search.py --date 2026-08-15, or python search.py --undo")
        return

    results = db.search(query_str, limit=args.limit)

    # Optional filter by date if combined with keyword search
    if args.date:
        results = [r for r in results if r.get("capture_date") == args.date.strip()]

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("=" * 70)
    print(f"  {BOLD}SnapTitle Search:{RESET} '{CYAN}{query_str}{RESET}'")
    print("=" * 70)

    if not results:
        print(f"No screenshots found matching '{query_str}'.")
        print(f"{DIM}Tip: Try searching for a partial keyword, error code, or subject.{RESET}")
        return

    print(f"Found {GREEN}{BOLD}{len(results)}{RESET} matching screenshot(s):\n")
    for i, r in enumerate(results, 1):
        file_path = Path(r["file_path"])
        exists_tag = f" {GREEN}[EXISTS]{RESET}" if file_path.exists() else f" {YELLOW}[MOVED/DELETED]{RESET}"
        print(f"[{BOLD}{i}{RESET}] {CYAN}{BOLD}{r['final_filename']}{RESET}{exists_tag}")
        print(f"    {BOLD}Title   :{RESET} {r['title']}")
        print(f"    {BOLD}Date    :{RESET} {GREEN}{r['capture_date']}{RESET} {DIM}| Original: {r['original_filename']}{RESET}")
        print(f"    {BOLD}Path    :{RESET} {DIM}{r['file_path']}{RESET}")
        
        snippet = r.get("snippet") or r.get("extracted_content")
        if snippet:
            cleaned_snippet = " ".join(snippet.split())
            if len(cleaned_snippet) > 120:
                cleaned_snippet = cleaned_snippet[:120] + "..."
            print(f"    {BOLD}Snippet :{RESET} {YELLOW}\"{cleaned_snippet}\"{RESET}")
        print(f"{DIM}{'-' * 70}{RESET}")


if __name__ == "__main__":
    main()
