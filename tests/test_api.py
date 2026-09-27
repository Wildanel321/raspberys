from pathlib import Path
from fastapi.testclient import TestClient
from raspimedia.config import AppConfig, MediaConfig, DatabaseConfig, CacheConfig
from raspimedia.server import create_app


def test_api_endpoints(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    song = media_dir / "Test Track.mp3"
    song.write_bytes(b"\x00" * 1024)

    cfg = AppConfig(
        media=MediaConfig(directories=[str(media_dir)]),
        database=DatabaseConfig(path=str(tmp_path / "test.db")),
        cache=CacheConfig(thumbnail_dir=str(tmp_path / "thumbs"))
    )

    app = create_app(cfg)
    client = TestClient(app)

    # 1. Check Status
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "directories" in data
    assert len(data["directories"]) == 1
    assert data["directories"][0]["exists"] is True

    # 2. Check Stats (populated on initial startup scan)
    stats_res = client.get("/api/stats")
    assert stats_res.status_code == 200
    st_data = stats_res.json()
    assert st_data["total_media"] == 1
    assert st_data["audio_count"] == 1

    # 3. Trigger Force Scan
    scan_res = client.post("/api/scan", json={"force": True})
    assert scan_res.status_code == 200
    s_data = scan_res.json()
    assert s_data["audio_found"] == 1
    assert s_data["updated"] == 1

    # 4. List Media
    media_res = client.get("/api/media")
    assert media_res.status_code == 200
    m_data = media_res.json()
    assert m_data["total"] == 1
    item = m_data["items"][0]
    assert item["filename"] == "Test Track.mp3"

    # 5. Toggle Favorite
    fav_res = client.post(f"/api/media/{item['id']}/favorite")
    assert fav_res.status_code == 200
    assert fav_res.json()["favorite"] is True

    # 6. Add Directory
    new_dir = tmp_path / "extra_videos"
    new_dir.mkdir()
    add_res = client.post("/api/config/directories", json={"directory": str(new_dir), "action": "add"})
    assert add_res.status_code == 200
    assert len(add_res.json()["directories"]) == 2

    # 7. Remove Directory
    rem_res = client.post("/api/config/directories", json={"directory": str(new_dir), "action": "remove"})
    assert rem_res.status_code == 200
    assert len(rem_res.json()["directories"]) == 1
