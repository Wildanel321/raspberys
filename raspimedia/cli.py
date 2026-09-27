"""
Command Line Interface for RaspiMedia.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional

from raspimedia import __version__
from raspimedia.config import AppConfig, load_config
from raspimedia.database import Database
from raspimedia.player import MPVController
from raspimedia.scanner import MediaScanner
from raspimedia.thumbnail import ThumbnailManager


def cmd_scan(args: argparse.Namespace, config: AppConfig) -> int:
    """Execute recursive / incremental media scan."""
    db = Database(config.get_database_path())
    thumb_mgr = ThumbnailManager(config.get_thumbnail_dir())
    scanner = MediaScanner(db, config, thumb_mgr)

    print("Scanning media...\n")

    result = scanner.scan(force=args.force)

    print("Directory:")
    if result.directories_scanned:
        for d in result.directories_scanned:
            print(f"  {d}")
    else:
        print("  (None available or configured)")

    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  {w}")

    print(f"\nFound:")
    print(f"  Audio: {result.audio_found}")
    print(f"  Video: {result.video_found}")

    print(f"\nAdded:")
    print(f"  {result.added}")

    print(f"\nUpdated:")
    print(f"  {result.updated}")

    print(f"\nRemoved:")
    print(f"  {result.removed}")

    print(f"\nUnchanged:")
    print(f"  {result.unchanged}")

    print(f"\nScan completed in {result.duration_sec}s.")
    return 0


def cmd_status(args: argparse.Namespace, config: AppConfig) -> int:
    """Show system and library status."""
    db = Database(config.get_database_path())
    player = MPVController(config, db)
    stats = db.get_stats()

    print(f"=== RaspiMedia v{__version__} Status ===")
    print(f"Database: {config.get_database_path()}")
    print(f"MPV Installed: {'Yes' if player.is_mpv_installed() else 'No'}")
    print(f"MPV IPC Socket: {config.mpv.ipc_socket}")

    print("\nConfigured Media Directories:")
    statuses = config.validate_directories()
    if not statuses:
        print("  (No directories configured in config.toml)")
    for ds in statuses:
        icon = "✓" if ds.exists and ds.readable else "✗"
        print(f"  {icon} {ds.path} [{ds.status_label}]")
        if ds.warning:
            print(f"      {ds.warning}")

    print("\nLibrary Statistics:")
    print(f"  Videos: {stats['video_count']} (Movies: {stats['movies_count']}, Series: {stats['series_count']})")
    print(f"  Music:  {stats['audio_count']} (Artists: {stats['artists_count']}, Albums: {stats['albums_count']})")
    print(f"  Total:  {stats['total_media']} files")
    print(f"  Favorites: {stats['favorite_count']}")
    return 0


def cmd_play(args: argparse.Namespace, config: AppConfig) -> int:
    """Play real media file on MPV."""
    db = Database(config.get_database_path())
    player = MPVController(config, db)

    target = args.target
    if target.isdigit():
        media_id = int(target)
        print(f"Playing media ID #{media_id} on MPV...")
        ok = player.play_media_id(media_id)
    else:
        p = Path(target).resolve()
        if not p.exists():
            print(f"Error: File does not exist: {target}", file=sys.stderr)
            return 1
        print(f"Playing file '{p}' on MPV...")
        ok = player.play_file(str(p))

    if ok:
        print("Playback initiated successfully via MPV IPC.")
        return 0
    else:
        print("Error: Could not launch or connect to MPV player.", file=sys.stderr)
        return 1


def cmd_server(args: argparse.Namespace, config: AppConfig) -> int:
    """Start RaspiMedia web server."""
    import uvicorn
    from raspimedia.server import create_app

    host = args.host or config.server.host
    port = args.port or config.server.port

    print(f"Starting RaspiMedia Web Server on http://{host}:{port}")
    app = create_app(config)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="raspimedia",
        description="RaspiMedia - Read-only media library and hardware player controller for Raspberry Pi",
    )
    parser.add_argument("--config", "-c", help="Path to config.toml configuration file")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan configured media directories")
    scan_parser.add_argument("--force", "-f", action="store_true", help="Force re-reading metadata for all files")

    # Status command
    subparsers.add_parser("status", help="Show media directories and library statistics")

    # Play command
    play_parser = subparsers.add_parser("play", help="Play media by ID or file path on MPV")
    play_parser.add_argument("target", help="Media ID (number) or real filesystem file path")

    # Server command
    server_parser = subparsers.add_parser("server", help="Start the web UI and REST API server")
    server_parser.add_argument("--host", default=None, help="Host address to bind")
    server_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    args = parser.parse_args(argv)

    config = load_config(args.config)

    if args.command == "scan":
        return cmd_scan(args, config)
    elif args.command == "status":
        return cmd_status(args, config)
    elif args.command == "play":
        return cmd_play(args, config)
    elif args.command == "server":
        return cmd_server(args, config)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
