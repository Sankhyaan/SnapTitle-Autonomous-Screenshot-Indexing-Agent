"""SnapTitle Search CLI: Fast full-text search across historical screenshots and OCR/VLM content."""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager
from config.config import load_config


def main():
    parser = argparse.ArgumentParser(
        description="SnapTitle Full-Text Screenshot Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python search.py "error 404"
  python search.py "invoice"
  python search.py "kubernetes crashloop" --limit 10
  python search.py --undo
        """
    )
    parser.add_argument("query", nargs="*", help="Search keywords or phrase")
    parser.add_argument("--limit", type=int, default=15, help="Maximum number of results to display (default: 15)")
    parser.add_argument("--undo", action="store_true", help="Undo the most recent screenshot rename")

    args = parser.parse_args()
    config = load_config()
    db = DatabaseManager(config.database_path)

    if args.undo:
        success, msg, current_p, restored_p = db.undo_last_rename()
        if success:
            print(f"\n[SUCCESS] {msg}")
            if restored_p:
                print(f"  Restored Path: {restored_p}")
        else:
            print(f"\n[INFO] {msg}")
        return

    query_str = " ".join(args.query).strip()
    if not query_str:
        print("Usage: python search.py <search terms>")
        print("Try: python search.py \"npm error\" or python search.py --undo")
        return

    print("=" * 70)
    print(f"  SnapTitle Search: '{query_str}'")
    print("=" * 70)

    results = db.search(query_str, limit=args.limit)

    if not results:
        print(f"No screenshots found matching '{query_str}'.")
        print("Tip: Try searching for a partial keyword, error code, or subject.")
        return

    print(f"Found {len(results)} matching screenshot(s):\n")
    for i, r in enumerate(results, 1):
        file_path = Path(r["file_path"])
        exists_tag = " [EXISTS]" if file_path.exists() else " [MOVED/DELETED]"
        print(f"[{i}] {r['final_filename']}{exists_tag}")
        print(f"    Title   : {r['title']}")
        print(f"    Date    : {r['capture_date']} | Original: {r['original_filename']}")
        print(f"    Path    : {r['file_path']}")
        
        snippet = r.get("snippet") or r.get("extracted_content")
        if snippet:
            cleaned_snippet = " ".join(snippet.split())
            if len(cleaned_snippet) > 120:
                cleaned_snippet = cleaned_snippet[:120] + "..."
            print(f"    Snippet : \"{cleaned_snippet}\"")
        print("-" * 70)


if __name__ == "__main__":
    main()
