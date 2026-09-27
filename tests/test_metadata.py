from pathlib import Path
from raspimedia.metadata import (
    clean_title_noise,
    is_media_file,
    get_media_type,
    parse_series_info,
    parse_music_fallback,
    parse_video_fallback,
)


def test_supported_extensions():
    assert is_media_file("song.mp3") is True
    assert is_media_file("audio.flac") is True
    assert is_media_file("track.wav") is True
    assert is_media_file("sound.ogg") is True
    assert is_media_file("clip.opus") is True
    assert is_media_file("music.m4a") is True
    assert is_media_file("audio.aac") is True
    
    assert is_media_file("movie.mp4") is True
    assert is_media_file("film.mkv") is True
    assert is_media_file("video.avi") is True
    assert is_media_file("stream.webm") is True
    assert is_media_file("video.mov") is True
    assert is_media_file("clip.m4v") is True
    assert is_media_file("stream.ts") is True
    assert is_media_file("stream.m2ts") is True

    assert is_media_file("document.pdf") is False
    assert is_media_file("image.jpg") is False


def test_media_type():
    assert get_media_type("track.flac") == "audio"
    assert get_media_type("video.mkv") == "video"


def test_clean_title_noise():
    assert clean_title_noise("Inception.2010.1080p.BluRay.x264") == "Inception 2010"
    assert clean_title_noise("Movie.Name.[1080p].[HEVC]") == "Movie Name"
    assert clean_title_noise("01 - Song Title") == "01 - Song Title"


def test_series_parsing_s01e03():
    # Prompt requirement: S01E03 - The Journey.mkv must parse cleanly, not "Unknown Media"
    info = parse_series_info("S01E03 - The Journey.mkv", parent_folder="My Show")
    assert info is not None
    assert info["season_number"] == 1
    assert info["episode_number"] == 3
    assert info["title"] == "The Journey"
    assert info["category"] == "series"


def test_series_parsing_1x04():
    info = parse_series_info("Breaking Bad - 1x04 - Cancer Man.mkv", parent_folder="Breaking Bad")
    assert info is not None
    assert info["season_number"] == 1
    assert info["episode_number"] == 4
    assert info["title"] == "Cancer Man"
    assert info["category"] == "series"


def test_music_fallback_parsing():
    p = Path("/mnt/media/Music/Daft Punk/Discovery/03 - Digital Love.flac")
    info = parse_music_fallback(p)
    assert info["artist"] == "Daft Punk"
    assert info["album"] == "Discovery"
    assert info["track_number"] == 3
    assert info["title"] == "Digital Love"
