from pathlib import Path
from raspimedia.database import Database


def test_database_crud(tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(db_file)

    media_data = {
        "path": "/mnt/media/Music/Pink Floyd/The Dark Side of the Moon/01 - Speak to Me.flac",
        "filename": "01 - Speak to Me.flac",
        "extension": ".flac",
        "media_type": "audio",
        "category": "music",
        "title": "Speak to Me",
        "artist": "Pink Floyd",
        "album": "The Dark Side of the Moon",
        "album_artist": "Pink Floyd",
        "genre": "Progressive Rock",
        "year": 1973,
        "track_number": 1,
        "duration": 65.0,
        "size": 1234567,
        "mtime": 1700000000.0,
    }

    # Insert
    mid = db.insert_media(media_data)
    assert mid > 0

    # Retrieve by ID
    item = db.get_media_by_id(mid)
    assert item is not None
    assert item["title"] == "Speak to Me"
    assert item["artist"] == "Pink Floyd"
    assert item["play_count"] == 0
    assert item["favorite"] == 0

    # Retrieve by Path
    item_path = db.get_media_by_path(media_data["path"])
    assert item_path is not None
    assert item_path["id"] == mid

    # Update
    db.update_media(mid, {"title": "Speak to Me (Remastered)"})
    updated = db.get_media_by_id(mid)
    assert updated["title"] == "Speak to Me (Remastered)"

    # Toggle favorite
    is_fav = db.toggle_favorite(mid)
    assert is_fav is True
    assert db.get_media_by_id(mid)["favorite"] == 1

    # Record playback
    db.record_playback(mid)
    assert db.get_media_by_id(mid)["play_count"] == 1
    assert db.get_media_by_id(mid)["last_played"] is not None

    # Stats
    stats = db.get_stats()
    assert stats["total_media"] == 1
    assert stats["audio_count"] == 1
    assert stats["video_count"] == 0
    assert stats["artists_count"] == 1
    assert stats["albums_count"] == 1
    assert stats["favorite_count"] == 1

    # Remove
    removed = db.remove_media_by_paths([media_data["path"]])
    assert removed == 1
    assert db.get_media_by_id(mid) is None
