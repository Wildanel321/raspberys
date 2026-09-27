import os
import tempfile
from pathlib import Path
from raspimedia.config import AppConfig, MediaConfig, load_config, save_config


def test_config_defaults():
    cfg = AppConfig()
    assert cfg.server.port == 8080
    assert cfg.media.directories == []
    statuses = cfg.validate_directories()
    assert len(statuses) == 0


def test_directory_validation(tmp_path):
    valid_dir = tmp_path / "valid_music"
    valid_dir.mkdir()

    missing_dir = tmp_path / "unmounted_usb" / "Movies"

    cfg = AppConfig(
        media=MediaConfig(directories=[str(valid_dir), str(missing_dir)])
    )

    statuses = cfg.validate_directories()
    assert len(statuses) == 2

    # Check valid dir
    s1 = next(s for s in statuses if s.path == str(valid_dir))
    assert s1.exists is True
    assert s1.readable is True
    assert s1.status_label == "Ready"
    assert s1.warning is None

    # Check missing dir
    s2 = next(s for s in statuses if s.path == str(missing_dir))
    assert s2.exists is False
    assert s2.status_label == "Missing"
    assert s2.warning is not None
    assert "WARNING" in s2.warning


def test_save_and_load_config(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg = AppConfig(
        media=MediaConfig(directories=["/mnt/media", "/mnt/music"]),
        config_file_path=str(cfg_file)
    )

    save_config(cfg, str(cfg_file))
    assert cfg_file.exists()

    loaded = load_config(str(cfg_file))
    assert loaded.media.directories == ["/mnt/media", "/mnt/music"]
    assert loaded.server.port == 8080
