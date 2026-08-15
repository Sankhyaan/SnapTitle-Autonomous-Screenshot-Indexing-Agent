"""SnapTitle Undo CLI: Revert the most recent screenshot rename."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseManager
from config.config import load_config


def main():
    config = load_config()
    db = DatabaseManager(config.database_path)

    print("=" * 60)
    print("  SnapTitle - Undo Last Screenshot Rename")
    print("=" * 60)

    success, message, current_path, restored_path = db.undo_last_rename()
    if success:
        print(f"\n[SUCCESS] {message}")
        if restored_path:
            print(f"  Current Path  : {current_path}")
            print(f"  Restored Path : {restored_path}\n")
    else:
        print(f"\n[INFO] {message}\n")


if __name__ == "__main__":
    main()
