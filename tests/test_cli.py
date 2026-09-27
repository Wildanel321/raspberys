from pathlib import Path
from raspimedia.cli import main
from raspimedia.config import AppConfig, MediaConfig, DatabaseConfig, CacheConfig, save_config


def test_cli_scan_output(tmp_path, capsys):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    track = media_dir / "Song.mp3"
    track.write_bytes(b"\x00" * 1024)

    cfg_file = tmp_path / "config.toml"
    cfg = AppConfig(
        media=MediaConfig(directories=[str(media_dir.resolve())]),
        database=DatabaseConfig(path=str(tmp_path / "test.db")),
        cache=CacheConfig(thumbnail_dir=str(tmp_path / "thumbs")),
        config_file_path=str(cfg_file)
    )
    save_config(cfg, str(cfg_file))

    exit_code = main(["--config", str(cfg_file), "scan"])
    assert exit_code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "Scanning media..." in out
    assert "Directory:" in out
    assert "Found:" in out
    assert "Audio: 1" in out
    assert "Video: 0" in out
    assert "Added:" in out
    assert "1" in out
    assert "Scan completed" in out


def test_cli_status_output(tmp_path, capsys):
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    cfg_file = tmp_path / "config.toml"
    cfg = AppConfig(
        media=MediaConfig(directories=[str(media_dir.resolve())]),
        database=DatabaseConfig(path=str(tmp_path / "test.db")),
        cache=CacheConfig(thumbnail_dir=str(tmp_path / "thumbs")),
        config_file_path=str(cfg_file)
    )
    save_config(cfg, str(cfg_file))

    exit_code = main(["--config", str(cfg_file), "status"])
    assert exit_code == 0

    captured = capsys.readouterr()
    out = captured.out

    assert "RaspiMedia v" in out
    assert "Configured Media Directories:" in out
    assert "Library Statistics:" in out
