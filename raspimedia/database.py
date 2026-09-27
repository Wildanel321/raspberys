"""
SQLite Database storage layer for RaspiMedia.
Represents real user media files only.
"""

from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    media_type TEXT NOT NULL,       -- 'audio' or 'video'
    category TEXT NOT NULL,         -- 'music', 'movie', 'series', 'other_video'
    title TEXT,
    artist TEXT,
    album TEXT,
    album_artist TEXT,
    genre TEXT,
    year INTEGER,
    track_number INTEGER,
    disc_number INTEGER,
    series_name TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    duration REAL DEFAULT 0,        -- in seconds
    resolution TEXT,                -- e.g. "1920x1080"
    codec TEXT,                     -- e.g. "h264", "flac", "mp3"
    size INTEGER NOT NULL,          -- size in bytes
    mtime REAL NOT NULL,            -- file modification timestamp
    thumbnail_path TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_played TIMESTAMP,
    play_count INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0      -- 0 or 1
);

CREATE INDEX IF NOT EXISTS idx_media_path ON media(path);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type);
CREATE INDEX IF NOT EXISTS idx_media_category ON media(category);
CREATE INDEX IF NOT EXISTS idx_media_artist ON media(artist);
CREATE INDEX IF NOT EXISTS idx_media_album ON media(album);
CREATE INDEX IF NOT EXISTS idx_media_title ON media(title);
CREATE INDEX IF NOT EXISTS idx_media_favorite ON media(favorite);
CREATE INDEX IF NOT EXISTS idx_media_series ON media(series_name, season_number, episode_number);

CREATE TABLE IF NOT EXISTS scan_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_sec REAL NOT NULL,
    directories_scanned INTEGER NOT NULL,
    audio_found INTEGER NOT NULL,
    video_found INTEGER NOT NULL,
    added_count INTEGER NOT NULL,
    updated_count INTEGER NOT NULL,
    removed_count INTEGER NOT NULL,
    unchanged_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    position INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual database connection with row_factory set."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize tables and indexes."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def get_existing_paths_map(self) -> Dict[str, Tuple[int, int, float]]:
        """
        Returns {path: (id, size, mtime)} for blazing-fast incremental scan comparisons.
        """
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id, path, size, mtime FROM media")
            result = {}
            for row in cursor.fetchall():
                result[row["path"]] = (row["id"], row["size"], row["mtime"])
            return result

    def get_media_by_id(self, media_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve single media record by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_media_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve single media record by real filesystem path."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM media WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def insert_media(self, data: Dict[str, Any]) -> int:
        """Insert a newly detected real media file."""
        columns = [
            "path", "filename", "extension", "media_type", "category",
            "title", "artist", "album", "album_artist", "genre", "year",
            "track_number", "disc_number", "series_name", "season_number",
            "episode_number", "duration", "resolution", "codec", "size",
            "mtime", "thumbnail_path"
        ]
        values = [data.get(col) for col in columns]
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        query = f"INSERT INTO media ({col_names}) VALUES ({placeholders})"
        with self.get_connection() as conn:
            cursor = conn.execute(query, values)
            return cursor.lastrowid

    def update_media(self, media_id: int, data: Dict[str, Any]) -> None:
        """Update metadata, size, mtime, or duration of an existing media file."""
        updatable = [
            "filename", "extension", "media_type", "category",
            "title", "artist", "album", "album_artist", "genre", "year",
            "track_number", "disc_number", "series_name", "season_number",
            "episode_number", "duration", "resolution", "codec", "size",
            "mtime", "thumbnail_path"
        ]
        set_clauses = []
        values = []
        for col in updatable:
            if col in data:
                set_clauses.append(f"{col} = ?")
                values.append(data[col])

        if not set_clauses:
            return

        values.append(media_id)
        query = f"UPDATE media SET {', '.join(set_clauses)} WHERE id = ?"
        with self.get_connection() as conn:
            conn.execute(query, values)

    def update_media_path(self, old_path: str, new_path: str, new_filename: str) -> None:
        """Safely update media path when a file move is detected."""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE media SET path = ?, filename = ? WHERE path = ?",
                (new_path, new_filename, old_path)
            )

    def remove_media_by_paths(self, paths: List[str]) -> int:
        """Remove media records whose files have been deleted from disk."""
        if not paths:
            return 0
        removed = 0
        with self.get_connection() as conn:
            # Batch delete in chunks of 500
            for i in range(0, len(paths), 500):
                chunk = paths[i:i + 500]
                placeholders = ", ".join(["?"] * len(chunk))
                cursor = conn.execute(f"DELETE FROM media WHERE path IN ({placeholders})", chunk)
                removed += cursor.rowcount
        return removed

    def toggle_favorite(self, media_id: int) -> bool:
        """Toggle favorite state of a media item."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT favorite FROM media WHERE id = ?", (media_id,))
            row = cursor.fetchone()
            if not row:
                return False
            new_fav = 0 if row["favorite"] else 1
            conn.execute("UPDATE media SET favorite = ? WHERE id = ?", (new_fav, media_id))
            return bool(new_fav)

    def record_playback(self, media_id: int) -> None:
        """Increment play count and record last played timestamp."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE media
                SET play_count = play_count + 1,
                    last_played = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (media_id,)
            )

    def list_media(
        self,
        media_type: Optional[str] = None,
        category: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        series_name: Optional[str] = None,
        favorite_only: bool = False,
        search_query: Optional[str] = None,
        order_by: str = "title",
        desc: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List media with rich filtering, search, and pagination.
        Returns (list_of_media_dicts, total_matching_count).
        """
        conditions = []
        params: List[Any] = []

        if media_type:
            conditions.append("media_type = ?")
            params.append(media_type)

        if category:
            conditions.append("category = ?")
            params.append(category)

        if artist:
            conditions.append("(artist = ? OR album_artist = ?)")
            params.extend([artist, artist])

        if album:
            conditions.append("album = ?")
            params.append(album)

        if series_name:
            conditions.append("series_name = ?")
            params.append(series_name)

        if favorite_only:
            conditions.append("favorite = 1")

        if search_query:
            term = f"%{search_query.strip()}%"
            conditions.append(
                "(title LIKE ? OR artist LIKE ? OR album LIKE ? OR series_name LIKE ? OR filename LIKE ?)"
            )
            params.extend([term, term, term, term, term])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Safe ordering
        allowed_orders = {
            "title": "title COLLATE NOCASE",
            "artist": "artist COLLATE NOCASE, album COLLATE NOCASE, track_number",
            "album": "album COLLATE NOCASE, track_number",
            "added_at": "added_at",
            "last_played": "last_played",
            "play_count": "play_count",
            "duration": "duration",
            "size": "size",
            "series": "series_name COLLATE NOCASE, season_number, episode_number",
        }
        order_col = allowed_orders.get(order_by, "title COLLATE NOCASE")
        direction = "DESC" if desc else "ASC"

        count_query = f"SELECT COUNT(*) as cnt FROM media {where_clause}"
        select_query = f"""
            SELECT * FROM media
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT ? OFFSET ?
        """

        with self.get_connection() as conn:
            cnt_cursor = conn.execute(count_query, params)
            total = cnt_cursor.fetchone()["cnt"]

            query_params = list(params)
            query_params.extend([limit, offset])
            rows = conn.execute(select_query, query_params).fetchall()
            return [dict(r) for r in rows], total

    def get_stats(self) -> Dict[str, Any]:
        """
        Return exact, real counts and aggregates from the database.
        Zero fake or dummy numbers.
        """
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) AS total_media,
                    SUM(CASE WHEN media_type = 'audio' THEN 1 ELSE 0 END) AS audio_count,
                    SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) AS video_count,
                    SUM(CASE WHEN category = 'movie' THEN 1 ELSE 0 END) AS movies_count,
                    SUM(CASE WHEN category = 'series' THEN 1 ELSE 0 END) AS series_count,
                    SUM(CASE WHEN category = 'other_video' THEN 1 ELSE 0 END) AS other_videos_count,
                    SUM(CASE WHEN favorite = 1 THEN 1 ELSE 0 END) AS favorite_count,
                    COUNT(DISTINCT CASE WHEN artist IS NOT NULL AND artist != '' THEN artist END) AS artists_count,
                    COUNT(DISTINCT CASE WHEN album IS NOT NULL AND album != '' THEN album END) AS albums_count,
                    COUNT(DISTINCT CASE WHEN series_name IS NOT NULL AND series_name != '' THEN series_name END) AS series_names_count,
                    COALESCE(SUM(size), 0) AS total_size_bytes,
                    COALESCE(SUM(duration), 0) AS total_duration_sec
                FROM media
            """).fetchone()

            stats = dict(row) if row else {}
            # Ensure proper ints and defaults
            return {
                "total_media": stats.get("total_media") or 0,
                "audio_count": stats.get("audio_count") or 0,
                "video_count": stats.get("video_count") or 0,
                "movies_count": stats.get("movies_count") or 0,
                "series_count": stats.get("series_count") or 0,
                "other_videos_count": stats.get("other_videos_count") or 0,
                "favorite_count": stats.get("favorite_count") or 0,
                "artists_count": stats.get("artists_count") or 0,
                "albums_count": stats.get("albums_count") or 0,
                "series_names_count": stats.get("series_names_count") or 0,
                "total_size_bytes": stats.get("total_size_bytes") or 0,
                "total_duration_sec": stats.get("total_duration_sec") or 0.0,
            }

    def get_artists(self) -> List[Dict[str, Any]]:
        """Get list of distinct artists with track and album counts."""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    COALESCE(NULLIF(artist, ''), 'Unknown Artist') AS artist,
                    COUNT(*) AS track_count,
                    COUNT(DISTINCT album) AS album_count
                FROM media
                WHERE media_type = 'audio'
                GROUP BY artist
                ORDER BY artist COLLATE NOCASE ASC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_albums(self, artist: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of distinct albums with artist, track counts, and year."""
        params = []
        where = "WHERE media_type = 'audio'"
        if artist:
            where += " AND (artist = ? OR album_artist = ?)"
            params.extend([artist, artist])

        query = f"""
            SELECT
                COALESCE(NULLIF(album, ''), 'Unknown Album') AS album,
                COALESCE(NULLIF(album_artist, ''), NULLIF(artist, ''), 'Unknown Artist') AS artist,
                COALESCE(MAX(year), 0) AS year,
                COUNT(*) AS track_count,
                SUM(duration) AS total_duration,
                MIN(thumbnail_path) AS thumbnail_path
            FROM media
            {where}
            GROUP BY album, artist
            ORDER BY album COLLATE NOCASE ASC
        """
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_series(self) -> List[Dict[str, Any]]:
        """Get list of distinct TV series with season and episode counts."""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    series_name,
                    COUNT(DISTINCT season_number) AS season_count,
                    COUNT(*) AS episode_count,
                    SUM(duration) AS total_duration,
                    MIN(thumbnail_path) AS thumbnail_path
                FROM media
                WHERE category = 'series' AND series_name IS NOT NULL AND series_name != ''
                GROUP BY series_name
                ORDER BY series_name COLLATE NOCASE ASC
            """).fetchall()
            return [dict(r) for r in rows]

    def log_scan(
        self,
        duration_sec: float,
        directories_scanned: int,
        audio_found: int,
        video_found: int,
        added: int,
        updated: int,
        removed: int,
        unchanged: int,
    ) -> None:
        """Record scan statistics for history and audit."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO scan_history (
                    duration_sec, directories_scanned, audio_found, video_found,
                    added_count, updated_count, removed_count, unchanged_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (duration_sec, directories_scanned, audio_found, video_found, added, updated, removed, unchanged)
            )
