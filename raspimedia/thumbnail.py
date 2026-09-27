"""
Thumbnail generation and caching for RaspiMedia.
Never alters original user media files.
"""

from __future__ import annotations
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def get_thumbnail_filename(file_path: str) -> str:
    """Generate deterministic hash filename for cached thumbnail."""
    path_hash = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
    return f"{path_hash}.jpg"


class ThumbnailManager:
    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir).resolve()
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def get_thumbnail_path(self, file_path: str) -> Optional[Path]:
        """Check if cached thumbnail exists."""
        thumb_file = self.cache_dir / get_thumbnail_filename(file_path)
        if thumb_file.exists() and thumb_file.stat().st_size > 0:
            return thumb_file
        return None

    def generate_thumbnail(self, media_path: str, media_type: str) -> Optional[Path]:
        """
        Generate thumbnail for media file if not already cached.
        Audio: Extracts embedded cover art.
        Video: Extracts preview frame using ffmpeg if available.
        Never modifies the original media file.
        """
        target = self.cache_dir / get_thumbnail_filename(media_path)
        if target.exists() and target.stat().st_size > 0:
            return target

        p = Path(media_path)
        if not p.exists():
            return None

        try:
            if media_type == "audio":
                return self._extract_audio_cover(p, target)
            elif media_type == "video":
                return self._extract_video_frame(p, target)
        except Exception:
            # Fallback gracefully - media playback and library must continue working
            pass

        return None

    def _extract_audio_cover(self, media_path: Path, target_path: Path) -> Optional[Path]:
        """Extract embedded cover image from audio tags."""
        try:
            import mutagen
            audio = mutagen.File(str(media_path))
            if audio is None:
                return None

            img_data = None

            # ID3 (MP3 / AIFF)
            if hasattr(audio, "tags") and audio.tags:
                for key in audio.tags.keys():
                    if key.startswith("APIC:"):
                        img_data = audio.tags[key].data
                        break

            # FLAC
            if not img_data and hasattr(audio, "pictures") and audio.pictures:
                img_data = audio.pictures[0].data

            # MP4 / M4A
            if not img_data and hasattr(audio, "tags") and audio.tags:
                if "covr" in audio.tags and audio.tags["covr"]:
                    img_data = bytes(audio.tags["covr"][0])

            if img_data:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "wb") as f:
                    f.write(img_data)
                return target_path
        except Exception:
            pass

        return None

    def _extract_video_frame(self, media_path: Path, target_path: Path) -> Optional[Path]:
        """Extract a frame from video using ffmpeg at 5 seconds."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return None

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-ss", "00:00:05",
                "-i", str(media_path),
                "-vframes", "1",
                "-q:v", "3",
                "-vf", "scale=480:-1",
                str(target_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if res.returncode == 0 and target_path.exists() and target_path.stat().st_size > 0:
                return target_path
        except Exception:
            pass

        return None
