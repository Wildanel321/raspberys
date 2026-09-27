"""
Recursive and incremental media scanner with file change detection for RaspiMedia.
Operates in strict READ-ONLY mode on user files.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from raspimedia.config import AppConfig
from raspimedia.database import Database
from raspimedia.metadata import extract_media_metadata, is_media_file, get_media_type
from raspimedia.thumbnail import ThumbnailManager


@dataclass
class ScanResult:
    directories_scanned: List[str] = field(default_factory=list)
    audio_found: int = 0
    video_found: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    duration_sec: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def total_found(self) -> int:
        return self.audio_found + self.video_found


class MediaScanner:
    def __init__(self, db: Database, config: AppConfig, thumbnail_manager: Optional[ThumbnailManager] = None):
        self.db = db
        self.config = config
        self.thumbnail_manager = thumbnail_manager or ThumbnailManager(config.get_thumbnail_dir())

    def scan(
        self,
        force: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> ScanResult:
        """
        Perform recursive media scan.
        Supports first-time scan, fast incremental rescan, and forced full rescan.
        Never touches, moves, renames, copies, or deletes user media files.
        """
        start_time = time.time()
        result = ScanResult()

        existing_db_map = self.db.get_existing_paths_map()  # {path: (id, size, mtime)}
        scanned_paths_on_disk: Set[str] = set()

        # Build index of existing items by (size, int(mtime)) for safe file move detection
        existing_fingerprints: Dict[Tuple[int, int], str] = {}
        for path_str, (mid, sz, mt) in existing_db_map.items():
            existing_fingerprints[(sz, int(mt))] = path_str

        # Validate directories
        dir_statuses = self.config.validate_directories()
        valid_dirs: List[Path] = []

        for ds in dir_statuses:
            if not ds.exists or not ds.readable:
                if ds.warning:
                    result.warnings.append(ds.warning)
                continue
            valid_dirs.append(Path(ds.path).resolve())
            result.directories_scanned.append(ds.path)

        if not valid_dirs:
            if not self.config.media.directories:
                result.warnings.append("No media directories configured in config.toml.")
            result.duration_sec = round(time.time() - start_time, 2)
            return result

        # Pass 1: Discover all media files on disk across configured directories
        discovered_files: List[Path] = []
        for vdir in valid_dirs:
            try:
                for root, _, files in os.walk(vdir, followlinks=True):
                    for file in files:
                        p = Path(root) / file
                        if is_media_file(p):
                            discovered_files.append(p)
            except Exception as e:
                result.warnings.append(f"Error scanning directory {vdir}: {e}")

        total_files = len(discovered_files)

        # Pass 2: Process files with change detection
        for idx, file_path in enumerate(discovered_files, start=1):
            abs_path_str = str(file_path.resolve())
            scanned_paths_on_disk.add(abs_path_str)

            mtype = get_media_type(file_path)
            if mtype == "audio":
                result.audio_found += 1
            elif mtype == "video":
                result.video_found += 1

            if progress_callback:
                progress_callback(file_path.name, idx, total_files)

            try:
                stat = file_path.stat()
                file_size = stat.st_size
                file_mtime = stat.st_mtime
            except Exception as e:
                result.warnings.append(f"Cannot stat {abs_path_str}: {e}")
                continue

            # Check if file exists in DB
            if abs_path_str in existing_db_map:
                media_id, old_size, old_mtime = existing_db_map[abs_path_str]
                # Compare size and modification time
                if not force and old_size == file_size and abs(old_mtime - file_mtime) < 0.01:
                    result.unchanged += 1
                else:
                    # File changed or force rescan requested
                    meta = extract_media_metadata(file_path)
                    # Extract thumbnail if available
                    thumb = self.thumbnail_manager.generate_thumbnail(abs_path_str, meta["media_type"])
                    if thumb:
                        meta["thumbnail_path"] = str(thumb)
                    self.db.update_media(media_id, meta)
                    result.updated += 1
            else:
                # Check if this file was moved/renamed from an old location
                fingerprint = (file_size, int(file_mtime))
                candidate_old_path = existing_fingerprints.get(fingerprint)

                if candidate_old_path and not Path(candidate_old_path).exists() and candidate_old_path not in scanned_paths_on_disk:
                    # Safe move detected! Update path in DB to retain playback stats and favorites
                    self.db.update_media_path(candidate_old_path, abs_path_str, file_path.name)
                    # Refresh existing map
                    mid, _, _ = existing_db_map.pop(candidate_old_path)
                    existing_db_map[abs_path_str] = (mid, file_size, file_mtime)
                    result.updated += 1
                else:
                    # New file
                    meta = extract_media_metadata(file_path)
                    thumb = self.thumbnail_manager.generate_thumbnail(abs_path_str, meta["media_type"])
                    if thumb:
                        meta["thumbnail_path"] = str(thumb)
                    self.db.insert_media(meta)
                    result.added += 1

        # Pass 3: Identify deleted files from scanned directories
        # Only clean up files that belong to currently valid, mounted, and scanned directories!
        # If a USB drive is not mounted, its directory was skipped above and files will NOT be purged.
        paths_to_remove: List[str] = []
        for db_path in existing_db_map.keys():
            # Check if this DB path falls inside one of the scanned valid directories
            db_p = Path(db_path)
            is_under_scanned_dir = any(
                str(db_p).startswith(str(vdir)) for vdir in valid_dirs
            )
            if is_under_scanned_dir and db_path not in scanned_paths_on_disk:
                if not db_p.exists():
                    paths_to_remove.append(db_path)

        if paths_to_remove:
            removed_count = self.db.remove_media_by_paths(paths_to_remove)
            result.removed = removed_count

        result.duration_sec = round(time.time() - start_time, 2)

        # Record scan stats in DB
        self.db.log_scan(
            duration_sec=result.duration_sec,
            directories_scanned=len(result.directories_scanned),
            audio_found=result.audio_found,
            video_found=result.video_found,
            added=result.added,
            updated=result.updated,
            removed=result.removed,
            unchanged=result.unchanged,
        )

        return result
