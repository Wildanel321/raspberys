"""
Configuration management and storage directory validation for RaspiMedia.
"""

from __future__ import annotations
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class DirectoryStatus:
    path: str
    exists: bool
    is_directory: bool
    readable: bool
    status_label: str  # "Ready", "Missing", "Permission Error", "Not a Directory"
    warning: Optional[str] = None


@dataclass
class MediaConfig:
    directories: List[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class DatabaseConfig:
    path: str = ""


@dataclass
class MPVConfig:
    ipc_socket: str = "/tmp/mpvsocket" if sys.platform != "win32" else r"\\.\pipe\mpvsocket"
    executable: str = "mpv"
    default_args: List[str] = field(
        default_factory=lambda: [
            "--no-terminal",
            "--force-window=immediate",
            "--hwdec=auto-safe"
        ]
    )


@dataclass
class CacheConfig:
    thumbnail_dir: str = ""


@dataclass
class AppConfig:
    media: MediaConfig = field(default_factory=MediaConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    mpv: MPVConfig = field(default_factory=MPVConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    config_file_path: Optional[str] = None

    def get_database_path(self) -> Path:
        """Resolve database path with fallback hierarchy."""
        if self.database.path:
            p = Path(self.database.path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

        # Priority 1: User home data dir (~/.local/share/raspimedia/ or Windows AppData)
        if sys.platform != "win32":
            system_dir = Path("/var/lib/raspimedia")
            try:
                if system_dir.exists() and os.access(system_dir, os.W_OK):
                    return system_dir / "raspimedia.db"
            except Exception:
                pass

        user_data = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "raspimedia"
        try:
            user_data.mkdir(parents=True, exist_ok=True)
            return user_data / "raspimedia.db"
        except Exception:
            pass

        # Fallback: Current working directory
        cwd_db = Path.cwd() / "raspimedia.db"
        return cwd_db

    def get_thumbnail_dir(self) -> Path:
        """Resolve thumbnail cache directory with fallback hierarchy."""
        if self.cache.thumbnail_dir:
            p = Path(self.cache.thumbnail_dir).expanduser().resolve()
            try:
                p.mkdir(parents=True, exist_ok=True)
                return p
            except Exception:
                pass

        if sys.platform != "win32":
            system_cache = Path("/var/cache/raspimedia/thumbnails")
            try:
                if system_cache.parent.exists() and os.access(system_cache.parent, os.W_OK):
                    system_cache.mkdir(parents=True, exist_ok=True)
                    return system_cache
            except Exception:
                pass

        user_cache = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "raspimedia" / "thumbnails"
        try:
            user_cache.mkdir(parents=True, exist_ok=True)
            return user_cache
        except Exception:
            pass

        cwd_cache = Path.cwd() / ".cache" / "thumbnails"
        cwd_cache.mkdir(parents=True, exist_ok=True)
        return cwd_cache

    def validate_directories(self) -> List[DirectoryStatus]:
        """
        Validate all configured media directories non-destructively.
        Does not attempt to mount, format, or alter directories.
        """
        statuses = []
        for dir_path in self.media.directories:
            p = Path(dir_path).expanduser()
            exists = p.exists()
            is_dir = p.is_dir() if exists else False
            readable = False
            label = "Ready"
            warning = None

            if not exists:
                label = "Missing"
                warning = f"WARNING: Media directory unavailable: {dir_path}"
            elif not is_dir:
                label = "Not a Directory"
                warning = f"WARNING: Path is not a directory: {dir_path}"
            else:
                try:
                    # Test read access non-destructively
                    readable = os.access(p, os.R_OK)
                    if not readable:
                        label = "Permission Error"
                        warning = f"WARNING: Media directory is not readable (Permission Denied): {dir_path}"
                except Exception as e:
                    label = "Permission Error"
                    warning = f"WARNING: Cannot access {dir_path}: {e}"

            statuses.append(
                DirectoryStatus(
                    path=dir_path,
                    exists=exists,
                    is_directory=is_dir,
                    readable=readable,
                    status_label=label,
                    warning=warning,
                )
            )
        return statuses


def find_config_file(explicit_path: Optional[str] = None) -> Optional[Path]:
    """Find configuration file following standard locations."""
    if explicit_path:
        p = Path(explicit_path).expanduser().resolve()
        if p.exists():
            return p
        return p  # Return path even if not existing so we know where it was specified

    # Check environment variable
    if env_path := os.getenv("RASPIMEDIA_CONFIG"):
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return p

    # Standard locations
    candidates = [
        Path.cwd() / "config.toml",
        Path.home() / ".config" / "raspimedia" / "config.toml",
        Path("/etc/raspimedia/config.toml"),
    ]

    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return c.resolve()
        except Exception:
            continue

    return None


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from TOML file or return defaults."""
    found_path = find_config_file(config_path)

    if not found_path or not found_path.exists():
        cfg = AppConfig()
        cfg.config_file_path = str(found_path) if found_path else None
        return cfg

    try:
        with open(found_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        print(f"Error loading config file {found_path}: {e}", file=sys.stderr)
        cfg = AppConfig()
        cfg.config_file_path = str(found_path)
        return cfg

    media_data = data.get("media", {})
    server_data = data.get("server", {})
    db_data = data.get("database", {})
    mpv_data = data.get("mpv", {})
    cache_data = data.get("cache", {})

    cfg = AppConfig(
        media=MediaConfig(
            directories=list(media_data.get("directories", []))
        ),
        server=ServerConfig(
            host=server_data.get("host", "0.0.0.0"),
            port=int(server_data.get("port", 8080)),
        ),
        database=DatabaseConfig(
            path=str(db_data.get("path", "")),
        ),
        mpv=MPVConfig(
            ipc_socket=str(mpv_data.get("ipc_socket", "/tmp/mpvsocket" if sys.platform != "win32" else r"\\.\pipe\mpvsocket")),
            executable=str(mpv_data.get("executable", "mpv")),
            default_args=list(mpv_data.get("default_args", [
                "--no-terminal",
                "--force-window=immediate",
                "--hwdec=auto-safe"
            ])),
        ),
        cache=CacheConfig(
            thumbnail_dir=str(cache_data.get("thumbnail_dir", "")),
        ),
        config_file_path=str(found_path.resolve()),
    )
    return cfg


def save_config(config: AppConfig, target_path: Optional[str] = None) -> Path:
    """
    Save current configuration to a TOML file.
    Does not touch user media directories.
    """
    out_path = Path(target_path or config.config_file_path or (Path.cwd() / "config.toml")).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# RaspiMedia Configuration File",
        "",
        "[media]",
        "directories = [",
    ]
    for d in config.media.directories:
        escaped = d.replace("\\", "/")
        lines.append(f'    "{escaped}",')
    lines.extend([
        "]",
        "",
        "[server]",
        f'host = "{config.server.host}"',
        f"port = {config.server.port}",
        "",
        "[database]",
        f'path = "{config.database.path.replace(chr(92), "/")}"',
        "",
        "[mpv]",
        f'ipc_socket = "{config.mpv.ipc_socket.replace(chr(92), "/")}"',
        f'executable = "{config.mpv.executable}"',
        "default_args = [",
    ])
    for arg in config.mpv.default_args:
        lines.append(f'    "{arg}",')
    lines.extend([
        "]",
        "",
        "[cache]",
        f'thumbnail_dir = "{config.cache.thumbnail_dir.replace(chr(92), "/")}"',
        "",
    ])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    config.config_file_path = str(out_path)
    return out_path
