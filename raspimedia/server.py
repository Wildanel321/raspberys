"""
FastAPI Server and REST API for RaspiMedia.
"""

from __future__ import annotations
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from raspimedia.config import AppConfig, load_config, save_config
from raspimedia.database import Database
from raspimedia.player import MPVController
from raspimedia.scanner import MediaScanner
from raspimedia.thumbnail import ThumbnailManager


class DirectoryActionRequest(BaseModel):
    directory: str
    action: str = "add"  # "add" or "remove"


class PlaybackControlRequest(BaseModel):
    action: str  # "play", "pause", "resume", "toggle", "stop", "seek", "volume"
    value: Optional[float] = None
    mode: Optional[str] = "relative"


class ScanRequest(BaseModel):
    force: bool = False


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    cfg = config or load_config()
    db = Database(cfg.get_database_path())
    thumbnail_mgr = ThumbnailManager(cfg.get_thumbnail_dir())
    scanner = MediaScanner(db, cfg, thumbnail_mgr)
    player = MPVController(cfg, db)

    # First-run check: If DB has 0 records and directories exist, trigger initial scan
    try:
        stats = db.get_stats()
        if stats["total_media"] == 0 and cfg.media.directories:
            scanner.scan()
    except Exception:
        pass

    app = FastAPI(
        title="RaspiMedia API",
        description="Read-only media player and library controller for Raspberry Pi",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/status")
    def get_status() -> Dict[str, Any]:
        """System, storage directory, and MPV player status."""
        dir_statuses = [
            {
                "path": ds.path,
                "exists": ds.exists,
                "is_directory": ds.is_directory,
                "readable": ds.readable,
                "status": ds.status_label,
                "warning": ds.warning,
            }
            for ds in cfg.validate_directories()
        ]
        p_state = player.get_state()
        return {
            "version": "1.0.0",
            "database_path": str(cfg.get_database_path()),
            "config_path": cfg.config_file_path,
            "directories": dir_statuses,
            "mpv_available": player.is_mpv_installed(),
            "player_state": {
                "is_running": p_state.is_running,
                "is_playing": p_state.is_playing,
                "is_paused": p_state.is_paused,
                "current_title": p_state.current_title,
                "time_pos": p_state.time_pos,
                "duration": p_state.duration,
                "volume": p_state.volume,
                "media_id": p_state.media_id,
            }
        }

    @app.get("/api/stats")
    def get_stats() -> Dict[str, Any]:
        """Exact real statistics from SQLite database."""
        return db.get_stats()

    @app.get("/api/media")
    def list_media(
        media_type: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        artist: Optional[str] = Query(None),
        album: Optional[str] = Query(None),
        series_name: Optional[str] = Query(None),
        favorite: bool = Query(False),
        q: Optional[str] = Query(None),
        order_by: str = Query("title"),
        desc: bool = Query(False),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> Dict[str, Any]:
        """Query and filter real media library."""
        items, total = db.list_media(
            media_type=media_type,
            category=category,
            artist=artist,
            album=album,
            series_name=series_name,
            favorite_only=favorite,
            search_query=q,
            order_by=order_by,
            desc=desc,
            limit=limit,
            offset=offset,
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

    @app.get("/api/media/{media_id}")
    def get_media_detail(media_id: int) -> Dict[str, Any]:
        """Get full details of a specific media file."""
        media = db.get_media_by_id(media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        return media

    @app.post("/api/scan")
    def trigger_scan(req: ScanRequest = ScanRequest()) -> Dict[str, Any]:
        """Trigger recursive / incremental rescan."""
        result = scanner.scan(force=req.force)
        return {
            "directories_scanned": result.directories_scanned,
            "audio_found": result.audio_found,
            "video_found": result.video_found,
            "total_found": result.total_found,
            "added": result.added,
            "updated": result.updated,
            "removed": result.removed,
            "unchanged": result.unchanged,
            "duration_sec": result.duration_sec,
            "warnings": result.warnings,
        }

    @app.get("/api/artists")
    def get_artists() -> List[Dict[str, Any]]:
        return db.get_artists()

    @app.get("/api/albums")
    def get_albums(artist: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return db.get_albums(artist=artist)

    @app.get("/api/series")
    def get_series() -> List[Dict[str, Any]]:
        return db.get_series()

    @app.post("/api/config/directories")
    def manage_directories(req: DirectoryActionRequest) -> Dict[str, Any]:
        """Add or remove media directory from config without touching media files."""
        clean_dir = os.path.normpath(req.directory.strip())
        current = [os.path.normpath(d) for d in cfg.media.directories]

        if req.action == "add":
            if clean_dir not in current:
                cfg.media.directories.append(req.directory.strip())
                save_config(cfg)
        elif req.action == "remove":
            cfg.media.directories = [d for d in cfg.media.directories if os.path.normpath(d) != clean_dir]
            save_config(cfg)

        return {
            "status": "success",
            "directories": [
                {
                    "path": ds.path,
                    "exists": ds.exists,
                    "readable": ds.readable,
                    "status": ds.status_label,
                    "warning": ds.warning,
                }
                for ds in cfg.validate_directories()
            ]
        }

    @app.post("/api/play/{media_id}")
    def play_media(media_id: int) -> Dict[str, Any]:
        """Directly open real media file in MPV player."""
        success = player.play_media_id(media_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to play media on MPV")
        return {"status": "playing", "media_id": media_id}

    @app.post("/api/playback/control")
    def control_playback(req: PlaybackControlRequest) -> Dict[str, Any]:
        """Control MPV player."""
        act = req.action.lower()
        if act == "pause":
            ok = player.pause()
        elif act == "resume":
            ok = player.resume()
        elif act == "toggle":
            ok = player.toggle_pause()
        elif act == "stop":
            ok = player.stop()
        elif act == "seek" and req.value is not None:
            ok = player.seek(req.value, mode=req.mode or "relative")
        elif act == "volume" and req.value is not None:
            ok = player.set_volume(req.value)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")

        return {"status": "ok" if ok else "error", "action": act}

    @app.get("/api/playback/status")
    def playback_status() -> Dict[str, Any]:
        """Get live MPV player status."""
        state = player.get_state()
        return {
            "is_running": state.is_running,
            "is_playing": state.is_playing,
            "is_paused": state.is_paused,
            "current_title": state.current_title,
            "time_pos": state.time_pos,
            "duration": state.duration,
            "volume": state.volume,
            "media_id": state.media_id,
        }

    @app.post("/api/media/{media_id}/favorite")
    def toggle_favorite(media_id: int) -> Dict[str, Any]:
        is_fav = db.toggle_favorite(media_id)
        return {"media_id": media_id, "favorite": is_fav}

    @app.get("/api/thumbnail/{media_id}")
    def get_thumbnail(media_id: int):
        """Serve thumbnail image for media."""
        media = db.get_media_by_id(media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")

        thumb_path = media.get("thumbnail_path")
        if thumb_path and Path(thumb_path).exists():
            return FileResponse(thumb_path, media_type="image/jpeg")

        # Try on-the-fly generation if not yet cached
        real_path = media.get("path")
        if real_path and Path(real_path).exists():
            thumb = thumbnail_mgr.generate_thumbnail(real_path, media.get("media_type", "audio"))
            if thumb and thumb.exists():
                db.update_media(media_id, {"thumbnail_path": str(thumb)})
                return FileResponse(str(thumb), media_type="image/jpeg")

        raise HTTPException(status_code=404, detail="Thumbnail not available")

    @app.get("/stream/{media_id}")
    def stream_media(media_id: int):
        """Direct file stream for web browser preview."""
        media = db.get_media_by_id(media_id)
        if not media or not media.get("path"):
            raise HTTPException(status_code=404, detail="Media not found")

        p = Path(media["path"])
        if not p.exists():
            raise HTTPException(status_code=404, detail="File missing on storage")

        mime_type, _ = mimetypes.guess_type(str(p))
        return FileResponse(str(p), media_type=mime_type or "application/octet-stream", filename=p.name)

    # Static web UI assets
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
