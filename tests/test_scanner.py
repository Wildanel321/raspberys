import os
import time
from pathlib import Path
from raspimedia.config import AppConfig, MediaConfig
from raspimedia.database import Database
from raspimedia.scanner import MediaScanner
from raspimedia.thumbnail import ThumbnailManager


def create_dummy_media_structure(root_dir: Path):
    """
    Helper to create mock directory tree for testing scanner change detection.
    """
    music_dir = root_dir / "Music" / "Artist A" / "Album A"
    music_dir.mkdir(parents=True, exist_ok=True)
    t1 = music_dir / "01 - Song 1.mp3"
    t1.write_bytes(b"\x00" * 1024)
    t2 = music_dir / "02 - Song 2.flac"
    t2.write_bytes(b"\x00" * 2048)

    movies_dir = root_dir / "Movies" / "Movie A"
    movies_dir.mkdir(parents=True, exist_ok=True)
    m1 = movies_dir / "Movie A (2022).mkv"
    m1.write_bytes(b"\x00" * 4096)

    series_dir = root_dir / "Series" / "Series A" / "Season 1"
    series_dir.mkdir(parents=True, exist_ok=True)
    s1 = series_dir / "S01E01 - Pilot.mp4"
    s1.write_bytes(b"\x00" * 3072)

    return [t1, t2, m1, s1]


def test_scanner_first_run_and_incremental(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    files = create_dummy_media_structure(media_root)

    db_file = tmp_path / "test.db"
    cache_dir = tmp_path / "thumbnails"
    db = Database(db_file)
    cfg = AppConfig(media=MediaConfig(directories=[str(media_root)]))
    thumb_mgr = ThumbnailManager(cache_dir)
    scanner = MediaScanner(db, cfg, thumb_mgr)

    # 1. First Run Scan
    r1 = scanner.scan()
    assert r1.audio_found == 2
    assert r1.video_found == 2
    assert r1.total_found == 4
    assert r1.added == 4
    assert r1.updated == 0
    assert r1.removed == 0
    assert r1.unchanged == 0

    stats = db.get_stats()
    assert stats["total_media"] == 4
    assert stats["audio_count"] == 2
    assert stats["video_count"] == 2
    assert stats["movies_count"] == 1
    assert stats["series_count"] == 1

    # 2. Incremental Rescan without changes (instant skip)
    r2 = scanner.scan()
    assert r2.audio_found == 2
    assert r2.video_found == 2
    assert r2.added == 0
    assert r2.updated == 0
    assert r2.removed == 0
    assert r2.unchanged == 4

    # 3. Add a new file
    new_track = media_root / "Music" / "Artist A" / "Album A" / "03 - Song 3.mp3"
    new_track.write_bytes(b"\x00" * 1500)

    r3 = scanner.scan()
    assert r3.added == 1
    assert r3.unchanged == 4
    assert db.get_stats()["total_media"] == 5

    # 4. Modify an existing file (size change)
    files[0].write_bytes(b"\x00" * 2000)
    # Ensure mtime updates
    os.utime(str(files[0]), (time.time() + 10, time.time() + 10))

    r4 = scanner.scan()
    assert r4.updated == 1
    assert r4.unchanged == 4

    # 5. Remove a file
    new_track.unlink()

    r5 = scanner.scan()
    assert r5.removed == 1
    assert db.get_stats()["total_media"] == 4
