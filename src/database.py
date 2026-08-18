"""SQLite database storage and FTS5 full-text search index for screenshot history and undo."""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union

from .renamer import safe_rename

logger = logging.getLogger("snaptitle.database")


class DatabaseManager:
    """Manages SQLite database storage, FTS5 full-text indexing, and rename undo history."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema with screenshots table and FTS5 full-text search index."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Main screenshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_filename TEXT NOT NULL,
                    final_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    extracted_content TEXT,
                    capture_date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_reverted INTEGER DEFAULT 0
                );
            """)

            # Optimization indices on frequently filtered columns
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_date ON screenshots(capture_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_reverted ON screenshots(is_reverted);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_created ON screenshots(created_at);")

            # FTS5 Virtual Table for full-text search across title, content, and filename
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts USING fts5(
                        title,
                        extracted_content,
                        final_filename,
                        content='screenshots',
                        content_rowid='id'
                    );
                """)

                # Triggers to keep FTS5 table automatically in sync with screenshots table
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS screenshots_ai AFTER INSERT ON screenshots BEGIN
                        INSERT INTO screenshots_fts(rowid, title, extracted_content, final_filename)
                        VALUES (new.id, new.title, new.extracted_content, new.final_filename);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS screenshots_ad AFTER DELETE ON screenshots BEGIN
                        INSERT INTO screenshots_fts(screenshots_fts, rowid, title, extracted_content, final_filename)
                        VALUES('delete', old.id, old.title, old.extracted_content, old.final_filename);
                    END;
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS screenshots_au AFTER UPDATE ON screenshots BEGIN
                        INSERT INTO screenshots_fts(screenshots_fts, rowid, title, extracted_content, final_filename)
                        VALUES('delete', old.id, old.title, old.extracted_content, old.final_filename);
                        INSERT INTO screenshots_fts(rowid, title, extracted_content, final_filename)
                        VALUES (new.id, new.title, new.extracted_content, new.final_filename);
                    END;
                """)
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 virtual table initialization issue: {e}. Falling back to standard queries.")

            conn.commit()

    def log_screenshot(
        self,
        original_filename: str,
        final_filename: str,
        file_path: Path,
        title: str,
        extracted_content: Optional[str] = None,
        capture_date: Optional[str] = None
    ) -> int:
        """Insert a newly processed screenshot into the database index.

        Args:
            original_filename: Original file name before renaming.
            final_filename: Renamed destination file name.
            file_path: Full path to the renamed file.
            title: AI-generated or user-edited title.
            extracted_content: Extracted OCR text or VLM caption.
            capture_date: Capture date formatted as YYYY-MM-DD.

        Returns:
            int: Primary key ID of the inserted record.
        """
        date_str = capture_date or datetime.now().strftime("%Y-%m-%d")
        content_str = (extracted_content or "").strip()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO screenshots (
                    original_filename,
                    final_filename,
                    file_path,
                    title,
                    extracted_content,
                    capture_date
                ) VALUES (?, ?, ?, ?, ?, ?);
            """, (
                original_filename,
                final_filename,
                str(file_path.resolve()),
                title,
                content_str,
                date_str
            ))
            conn.commit()
            record_id = cursor.lastrowid or 0
            logger.info(f"Logged screenshot to database [ID={record_id}]: '{final_filename}'")
            return record_id

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search screenshot database for matching query text using FTS5 (or LIKE fallback).

        Args:
            query: Search query terms (e.g. 'npm error', 'invoice', 'kubernetes').
            limit: Maximum number of results to return (clamped >= 1).

        Returns:
            List[Dict[str, Any]]: List of matching records.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        limit = max(1, int(limit))
        results: List[Dict[str, Any]] = []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Try SQLite FTS5 MATCH query (AND match first, then OR match)
            tokens = [t.replace('"', '').strip() for t in cleaned_query.split() if t.replace('"', '').strip()]
            if tokens:
                try:
                    # 1a. AND match across all tokens
                    and_query = " ".join([f'"{token}"*' for token in tokens])
                    cursor.execute("""
                        SELECT s.id, s.original_filename, s.final_filename, s.file_path,
                               s.title, s.extracted_content, s.capture_date, s.created_at, s.is_reverted,
                               snippet(screenshots_fts, 1, '[MATCH]', '[/MATCH]', '...', 12) AS snippet
                        FROM screenshots_fts f
                        JOIN screenshots s ON f.rowid = s.id
                        WHERE screenshots_fts MATCH ? AND s.is_reverted = 0
                        ORDER BY rank
                        LIMIT ?;
                    """, (and_query, limit))
                    results = [dict(r) for r in cursor.fetchall()]

                    # 1b. If no strict AND matches, try OR match across tokens
                    if not results and len(tokens) > 1:
                        or_query = " OR ".join([f'"{token}"*' for token in tokens])
                        cursor.execute("""
                            SELECT s.id, s.original_filename, s.final_filename, s.file_path,
                                   s.title, s.extracted_content, s.capture_date, s.created_at, s.is_reverted,
                                   snippet(screenshots_fts, 1, '[MATCH]', '[/MATCH]', '...', 12) AS snippet
                            FROM screenshots_fts f
                            JOIN screenshots s ON f.rowid = s.id
                            WHERE screenshots_fts MATCH ? AND s.is_reverted = 0
                            ORDER BY rank
                            LIMIT ?;
                        """, (or_query, limit))
                        results = [dict(r) for r in cursor.fetchall()]

                    if results:
                        return results

                except Exception as e:
                    logger.debug(f"FTS5 query failed, falling back to LIKE: {e}")

            # 2. Fallback to LIKE query across title, filename, and extracted content
            like_clauses = []
            params = []
            for token in tokens:
                like_term = f"%{token}%"
                like_clauses.append("(title LIKE ? OR extracted_content LIKE ? OR final_filename LIKE ?)")
                params.extend([like_term, like_term, like_term])

            where_sql = " OR ".join(like_clauses) if like_clauses else "1=1"
            params.append(limit)

            cursor.execute(f"""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted,
                       extracted_content AS snippet
                FROM screenshots
                WHERE is_reverted = 0 AND ({where_sql})
                ORDER BY id DESC
                LIMIT ?;
            """, tuple(params))

            for r in cursor.fetchall():
                results.append(dict(r))

        return results

    def get_recent_renames(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent renames from the database.

        Args:
            limit: Number of records to return (clamped >= 1).

        Returns:
            List[Dict[str, Any]]: List of recent screenshot records.
        """
        limit = max(1, int(limit))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted
                FROM screenshots
                ORDER BY id DESC
                LIMIT ?;
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def undo_last_rename(self) -> Tuple[bool, str, Optional[Path], Optional[Path]]:
        """Revert the most recent non-reverted screenshot rename back to its original name.

        Returns:
            Tuple[bool, str, Optional[Path], Optional[Path]]:
                - Success boolean
                - Status message
                - Current path before revert
                - Restored path after revert
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path
                FROM screenshots
                WHERE is_reverted = 0
                ORDER BY id DESC
                LIMIT 1;
            """)
            record = cursor.fetchone()

            if not record:
                return False, "No recent renames found to undo.", None, None

            record_id = record["id"]
            orig_name = record["original_filename"]
            current_path = Path(record["file_path"])

            if not current_path.exists():
                return False, f"Renamed file not found at '{current_path}'. It may have been moved or deleted.", current_path, None

            try:
                # Revert file back to original_filename
                restored_path = safe_rename(
                    source_path=current_path,
                    target_filename=orig_name,
                    target_folder=current_path.parent
                )

                # Update database record as reverted
                cursor.execute("""
                    UPDATE screenshots
                    SET is_reverted = 1, file_path = ?
                    WHERE id = ?;
                """, (str(restored_path.resolve()), record_id))
                conn.commit()

                logger.info(f"Reverted rename [ID={record_id}]: '{current_path.name}' -> '{restored_path.name}'")
                return True, f"Successfully reverted '{current_path.name}' back to '{orig_name}'", current_path, restored_path

            except Exception as e:
                logger.error(f"Failed to undo rename for '{current_path}': {e}", exc_info=True)
                return False, f"Failed to undo rename: {e}", current_path, None

    def get_screenshot_count(self) -> int:
        """Get the total count of active (non-reverted) indexed screenshots.

        Returns:
            int: Number of active screenshot records in the database.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM screenshots WHERE is_reverted = 0;")
            row = cursor.fetchone()
            return row["total"] if row else 0

    def get_database_stats(self) -> Dict[str, int]:
        """Retrieve total, active, and reverted screenshot counts.

        Returns:
            Dict[str, int]: Dictionary containing total, active, and reverted counts.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_reverted = 0 THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN is_reverted = 1 THEN 1 ELSE 0 END) AS reverted
                FROM screenshots;
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "total": row["total"] or 0,
                    "active": row["active"] or 0,
                    "reverted": row["reverted"] or 0
                }
            return {"total": 0, "active": 0, "reverted": 0}

    def get_screenshot_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a single screenshot record by its primary key ID.

        Args:
            record_id: Database record ID.

        Returns:
            Optional[Dict[str, Any]]: Record dictionary if found, else None.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted
                FROM screenshots
                WHERE id = ?;
            """, (record_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_screenshots_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """Retrieve screenshot records matching a final or original filename.

        Args:
            filename: Target filename string.

        Returns:
            List[Dict[str, Any]]: Matching screenshot records.
        """
        target = (filename or "").strip()
        if not target:
            return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted
                FROM screenshots
                WHERE final_filename = ? OR original_filename = ?
                ORDER BY id DESC;
            """, (target, target))
            return [dict(r) for r in cursor.fetchall()]

    def get_screenshots_by_date(self, capture_date: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve screenshots matching a specific capture date (YYYY-MM-DD).

        Args:
            capture_date: Target date string in YYYY-MM-DD format.
            limit: Maximum records to return (clamped >= 1).

        Returns:
            List[Dict[str, Any]]: List of matching screenshot records.
        """
        limit = max(1, int(limit))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted
                FROM screenshots
                WHERE capture_date = ? AND is_reverted = 0
                ORDER BY id DESC
                LIMIT ?;
            """, (capture_date.strip(), limit))
            return [dict(r) for r in cursor.fetchall()]

    def backup_database(self, backup_destination: Union[str, Path]) -> Path:
        """Create a backup copy of the SQLite database at backup_destination.

        Args:
            backup_destination: Target backup file path.

        Returns:
            Path: Path to the created backup database file.
        """
        dest = Path(backup_destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            with sqlite3.connect(str(dest)) as backup_conn:
                conn.backup(backup_conn)
        logger.info(f"Database backed up to '{dest}'")
        return dest

    def purge_reverted_records(self) -> int:
        """Purge soft-deleted (is_reverted = 1) records from database to optimize storage.

        Returns:
            int: Count of purged records.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM screenshots WHERE is_reverted = 1;")
            deleted_count = cursor.rowcount or 0
            conn.commit()
            logger.info(f"Purged {deleted_count} reverted screenshot records.")
            return deleted_count

    def get_screenshots_by_date_range(
        self,
        start_date: str,
        end_date: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve screenshots captured within a specific date range [start_date, end_date].

        Args:
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).
            limit: Maximum records to return (clamped >= 1).

        Returns:
            List[Dict[str, Any]]: Matching screenshot records.
        """
        limit = max(1, int(limit))
        s_date = start_date.strip()
        e_date = end_date.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, original_filename, final_filename, file_path,
                       title, extracted_content, capture_date, created_at, is_reverted
                FROM screenshots
                WHERE capture_date >= ? AND capture_date <= ? AND is_reverted = 0
                ORDER BY capture_date DESC, id DESC
                LIMIT ?;
            """, (s_date, e_date, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_duplicate_titles_summary(self) -> List[Dict[str, Any]]:
        """Get summary of screenshot titles shared across multiple entries.

        Returns:
            List[Dict[str, Any]]: Titles with occurrence count > 1.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, COUNT(*) AS count
                FROM screenshots
                WHERE is_reverted = 0
                GROUP BY title
                HAVING COUNT(*) > 1
                ORDER BY count DESC;
            """)
            return [dict(r) for r in cursor.fetchall()]
