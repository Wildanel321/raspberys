"""
Metadata extraction and intelligent filename/path parsing for RaspiMedia.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Supported Extensions
AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac",
    ".wma", ".alac", ".aiff", ".aif", ".ape", ".mka", ".wv"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v", ".ts",
    ".m2ts", ".wmv", ".vob", ".flv", ".3gp", ".ogv", ".divx"
}

ALL_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def is_media_file(path: Path | str) -> bool:
    """Check if file extension matches supported audio or video format."""
    ext = Path(path).suffix.lower()
    return ext in ALL_MEDIA_EXTENSIONS


def get_media_type(path: Path | str) -> Optional[str]:
    """Return 'audio' or 'video' based on extension."""
    ext = Path(path).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def clean_title_noise(name: str) -> str:
    """
    Remove release groups, resolution, codecs, and tags from title strings.
    E.g. "Inception.2010.1080p.BluRay.x264-SPARKS" -> "Inception"
    """
    cleaned = re.sub(r"[\._]", " ", name)
    # Remove bracketed tags like [1080p], [x264], [YTS.LT], (2020)
    cleaned = re.sub(r"\[.*?\]", " ", cleaned)
    # Remove resolution and video tags
    noise_patterns = [
        r"\b(2160p|4k|1080p|720p|480p|360p|uhd|fhd|hdrip|bluray|blu-ray|web-dl|webrip|brrip|dvdrip|hdtv)\b",
        r"\b(x264|x265|hevc|h264|h265|avc|10bit|aac5\.1|dd5\.1|dts|ac3|atmos|truehd)\b",
        r"\b(repack|proper|unrated|extended|remastered|directors\.cut|multi)\b",
    ]
    for pat in noise_patterns:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

    # Clean multiple spaces and trim
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -._")
    return cleaned if cleaned else name


def parse_series_info(filename: str, parent_folder: str = "") -> Optional[Dict[str, Any]]:
    """
    Intelligently parse series name, season, episode, and episode title.
    Supports formats:
    - S01E03 - The Journey
    - Show.Name.S02E05.Episode.Title
    - Show Name - 1x04 - Title
    - Season 1/03 - Episode Title.mkv
    """
    stem = Path(filename).stem

    # Pattern 1: S01E02 or s01e02 or S1E2
    m1 = re.search(r"^(.*?)(?:[\s\._-]*)s(\d{1,2})[\s\._-]*e(\d{1,3})(?:[\s\._-]*)(.*)$", stem, re.IGNORECASE)
    if m1:
        raw_show, season, episode, raw_title = m1.groups()
        show = clean_title_noise(raw_show) or clean_title_noise(parent_folder)
        ep_title = clean_title_noise(raw_title)
        return {
            "series_name": show if show else parent_folder,
            "season_number": int(season),
            "episode_number": int(episode),
            "title": ep_title if ep_title else f"Episode {int(episode)}",
            "category": "series"
        }

    # Pattern 2: 1x04 format
    m2 = re.search(r"^(.*?)(?:[\s\._-]*)(\d{1,2})x(\d{1,3})(?:[\s\._-]*)(.*)$", stem, re.IGNORECASE)
    if m2:
        raw_show, season, episode, raw_title = m2.groups()
        show = clean_title_noise(raw_show) or clean_title_noise(parent_folder)
        ep_title = clean_title_noise(raw_title)
        return {
            "series_name": show if show else parent_folder,
            "season_number": int(season),
            "episode_number": int(episode),
            "title": ep_title if ep_title else f"Episode {int(episode)}",
            "category": "series"
        }

    # Pattern 3: Check if parent folder indicates Season e.g. "Series Name/Season 1/03. Episode Title"
    season_match = re.search(r"Season\s*(\d+)", parent_folder, re.IGNORECASE)
    if season_match:
        season_num = int(season_match.group(1))
        ep_match = re.search(r"^(\d{1,3})[\s\._-]+(.*)$", stem)
        if ep_match:
            ep_num = int(ep_match.group(1))
            ep_title = clean_title_noise(ep_match.group(2))
            return {
                "series_name": clean_title_noise(Path(parent_folder).parent.name) or parent_folder,
                "season_number": season_num,
                "episode_number": ep_num,
                "title": ep_title if ep_title else f"Episode {ep_num}",
                "category": "series"
            }

    return None


def parse_music_fallback(file_path: Path) -> Dict[str, Any]:
    """
    Intelligently infer artist, album, track number, and title from folder hierarchy and filename.
    Standard patterns:
    - Music/Artist/Album/01 - Song.mp3
    - Music/Artist/Album/01. Song.flac
    - Artist - Song.mp3
    """
    stem = file_path.stem
    parent = file_path.parent
    grandparent = parent.parent

    track_num = None
    title = stem
    artist = None
    album = None

    # Check track number in filename like "01 - Title" or "01. Title" or "01 Title"
    m_track = re.match(r"^(\d{1,3})[\s\.\-_]+(.*)$", stem)
    if m_track:
        try:
            track_num = int(m_track.group(1))
            title = m_track.group(2).strip()
        except ValueError:
            pass

    # Check "Artist - Title" format
    if " - " in title:
        parts = title.split(" - ", 1)
        artist = clean_title_noise(parts[0])
        title = clean_title_noise(parts[1])
    else:
        title = clean_title_noise(title)

    # Use directory structure if available (e.g. Artist/Album/Song)
    if parent.name and parent.name.lower() not in ["music", "audio", "songs"]:
        album = clean_title_noise(parent.name)
        if grandparent.name and grandparent.name.lower() not in ["music", "audio", "storage", "media", "mnt"]:
            if not artist:
                artist = clean_title_noise(grandparent.name)

    return {
        "title": title or stem,
        "artist": artist or "Unknown Artist",
        "album": album or "Unknown Album",
        "track_number": track_num,
    }


def parse_video_fallback(file_path: Path) -> Dict[str, Any]:
    """
    Parse video filename and parent directories for clean metadata.
    Categorizes as movie, series, or other_video.
    """
    stem = file_path.stem
    parent_name = file_path.parent.name
    full_path_str = str(file_path).lower()

    # Check if series
    series_info = parse_series_info(file_path.name, parent_name)
    if series_info:
        return series_info

    # Check if folder path contains 'series' or 'tv' or 'episodes'
    if any(k in full_path_str for k in ["/series", "/tv", "/shows", "\\series", "\\tv", "\\shows"]):
        cleaned = clean_title_noise(stem)
        return {
            "series_name": clean_title_noise(parent_name),
            "season_number": 1,
            "episode_number": 1,
            "title": cleaned or stem,
            "category": "series"
        }

    # Extract year if present e.g. "Inception (2010)"
    year = None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", stem)
    if year_match:
        year = int(year_match.group(1))

    title = clean_title_noise(stem)

    category = "movie" if any(k in full_path_str for k in ["movie", "film", "cinema"]) else "other_video"

    return {
        "title": title or stem,
        "year": year,
        "category": category,
    }


def extract_media_metadata(file_path: Path | str) -> Dict[str, Any]:
    """
    Extract comprehensive metadata from a media file.
    Uses file tags (Mutagen) if available, with robust clean fallbacks.
    Never modifies the user's file.
    """
    p = Path(file_path).resolve()
    stat = p.stat()
    size = stat.st_size
    mtime = stat.st_mtime
    ext = p.suffix.lower()
    media_type = get_media_type(p) or ("audio" if ext in AUDIO_EXTENSIONS else "video")

    data: Dict[str, Any] = {
        "path": str(p),
        "filename": p.name,
        "extension": ext,
        "media_type": media_type,
        "category": "music" if media_type == "audio" else "other_video",
        "title": clean_title_noise(p.stem),
        "artist": None,
        "album": None,
        "album_artist": None,
        "genre": None,
        "year": None,
        "track_number": None,
        "disc_number": None,
        "series_name": None,
        "season_number": None,
        "episode_number": None,
        "duration": 0.0,
        "resolution": None,
        "codec": ext.lstrip("."),
        "size": size,
        "mtime": mtime,
        "thumbnail_path": None,
    }

    # Step 1: Intelligent filename/directory fallback parsing
    if media_type == "audio":
        fallback = parse_music_fallback(p)
        data.update(fallback)
        data["category"] = "music"
    else:
        fallback = parse_video_fallback(p)
        data.update(fallback)

    # Step 2: Try reading actual tags via Mutagen
    try:
        import mutagen
        audio_file = mutagen.File(str(p), easy=True)
        if audio_file is not None:
            if hasattr(audio_file, "info") and audio_file.info:
                if hasattr(audio_file.info, "length"):
                    data["duration"] = round(float(audio_file.info.length), 2)
                if hasattr(audio_file.info, "codec"):
                    data["codec"] = str(audio_file.info.codec)

            tags = audio_file.tags or {}
            # EasyID3 / Vorbis tags mapping
            if "title" in tags and tags["title"]:
                data["title"] = str(tags["title"][0]).strip()
            if "artist" in tags and tags["artist"]:
                data["artist"] = str(tags["artist"][0]).strip()
            if "album" in tags and tags["album"]:
                data["album"] = str(tags["album"][0]).strip()
            if "albumartist" in tags and tags["albumartist"]:
                data["album_artist"] = str(tags["albumartist"][0]).strip()
            if "genre" in tags and tags["genre"]:
                data["genre"] = str(tags["genre"][0]).strip()
            if "date" in tags and tags["date"]:
                date_str = str(tags["date"][0])
                m_year = re.search(r"\b(19\d{2}|20\d{2})\b", date_str)
                if m_year:
                    data["year"] = int(m_year.group(1))
            if "tracknumber" in tags and tags["tracknumber"]:
                raw_track = str(tags["tracknumber"][0]).split("/")[0]
                try:
                    data["track_number"] = int(raw_track)
                except ValueError:
                    pass
            if "discnumber" in tags and tags["discnumber"]:
                raw_disc = str(tags["discnumber"][0]).split("/")[0]
                try:
                    data["disc_number"] = int(raw_disc)
                except ValueError:
                    pass
    except Exception:
        # Gracefully preserve fallback metadata if file tags are corrupted or unsupported
        pass

    # Ensure title is never empty or "Unknown Media"
    if not data["title"] or data["title"].lower() in ["unknown", "unknown media", "track"]:
        data["title"] = clean_title_noise(p.stem) or p.name

    return data
