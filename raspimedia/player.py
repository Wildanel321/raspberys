"""
MPV Player JSON-IPC Controller for RaspiMedia.
Plays real files directly with zero transcoding and zero temporary copies.
"""

from __future__ import annotations
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from raspimedia.config import AppConfig
from raspimedia.database import Database


@dataclass
class PlayerState:
    is_running: bool = False
    is_playing: bool = False
    is_paused: bool = False
    current_path: Optional[str] = None
    current_title: Optional[str] = None
    time_pos: float = 0.0
    duration: float = 0.0
    volume: float = 100.0
    media_id: Optional[int] = None
    media_type: Optional[str] = None


class MPVController:
    def __init__(self, config: AppConfig, db: Optional[Database] = None):
        self.config = config
        self.db = db
        self.ipc_socket = config.mpv.ipc_socket
        self.executable = config.mpv.executable
        self.mpv_process: Optional[subprocess.Popen] = None
        self._current_media_id: Optional[int] = None

    def is_mpv_installed(self) -> bool:
        """Check if mpv binary is available in PATH."""
        return shutil.which(self.executable) is not None

    def _ensure_mpv_running(self) -> bool:
        """Ensure MPV is running with the IPC server enabled."""
        if self._test_ipc_connection():
            return True

        if not self.is_mpv_installed():
            return False

        # Clean up old socket file if on UNIX
        if sys.platform != "win32":
            sock_p = Path(self.ipc_socket)
            if sock_p.exists():
                try:
                    sock_p.unlink()
                except Exception:
                    pass

        cmd = [
            self.executable,
            f"--input-ipc-server={self.ipc_socket}",
            "--idle=yes",
            "--keep-open=yes",
        ] + self.config.mpv.default_args

        try:
            self.mpv_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=(sys.platform != "win32"),
            )
            # Wait briefly for IPC socket creation
            for _ in range(25):
                time.sleep(0.1)
                if self._test_ipc_connection():
                    return True
        except Exception:
            return False

        return self._test_ipc_connection()

    def _test_ipc_connection(self) -> bool:
        """Check if IPC server is accepting commands."""
        try:
            res = self.send_command(["get_property", "idle-active"])
            return res is not None
        except Exception:
            return False

    def send_command(self, command: List[Any], timeout: float = 2.0) -> Optional[Any]:
        """
        Send a JSON-IPC command to MPV and return the parsed result.
        """
        payload = json.dumps({"command": command}) + "\n"

        if sys.platform == "win32":
            # Named pipe communication on Windows
            try:
                with open(self.ipc_socket, "r+b", buffering=0) as pipe:
                    pipe.write(payload.encode("utf-8"))
                    response_line = pipe.readline().decode("utf-8")
                    data = json.loads(response_line)
                    if data.get("error") == "success":
                        return data.get("data")
                    return None
            except Exception:
                return None
        else:
            # UNIX domain socket communication
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(self.ipc_socket)
                sock.sendall(payload.encode("utf-8"))
                response = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    if b"\n" in chunk:
                        break
                sock.close()
                for line in response.decode("utf-8", errors="ignore").splitlines():
                    if line.strip():
                        data = json.loads(line)
                        if data.get("error") == "success":
                            return data.get("data")
                return None
            except Exception:
                return None

    def play_file(self, file_path: str, media_id: Optional[int] = None) -> bool:
        """
        Load real media file directly into MPV without copy or transcode.
        """
        real_p = Path(file_path).resolve()
        if not real_p.exists():
            return False

        if not self._ensure_mpv_running():
            return False

        # Send command to load the real file path
        res = self.send_command(["loadfile", str(real_p), "replace"])
        self._current_media_id = media_id

        if self.db and media_id:
            try:
                self.db.record_playback(media_id)
            except Exception:
                pass

        return res is not None or True

    def play_media_id(self, media_id: int) -> bool:
        """Play media by its database ID."""
        if not self.db:
            return False
        media = self.db.get_media_by_id(media_id)
        if not media or not media.get("path"):
            return False
        return self.play_file(media["path"], media_id=media_id)

    def pause(self) -> bool:
        return self.send_command(["set_property", "pause", True]) is not None

    def resume(self) -> bool:
        return self.send_command(["set_property", "pause", False]) is not None

    def toggle_pause(self) -> bool:
        return self.send_command(["cycle", "pause"]) is not None

    def stop(self) -> bool:
        self._current_media_id = None
        return self.send_command(["stop"]) is not None

    def seek(self, seconds: float, mode: str = "relative") -> bool:
        return self.send_command(["seek", seconds, mode]) is not None

    def set_volume(self, volume: float) -> bool:
        vol = max(0.0, min(100.0, float(volume)))
        return self.send_command(["set_property", "volume", vol]) is not None

    def get_state(self) -> PlayerState:
        """Query MPV for current playback state."""
        state = PlayerState()
        if not self._test_ipc_connection():
            state.is_running = False
            return state

        state.is_running = True
        try:
            current_path = self.send_command(["get_property", "path"])
            if current_path:
                state.current_path = str(current_path)
                state.is_playing = True
                paused = self.send_command(["get_property", "pause"])
                state.is_paused = bool(paused)
                time_pos = self.send_command(["get_property", "time-pos"])
                state.time_pos = round(float(time_pos), 2) if time_pos is not None else 0.0
                duration = self.send_command(["get_property", "duration"])
                state.duration = round(float(duration), 2) if duration is not None else 0.0
                volume = self.send_command(["get_property", "volume"])
                state.volume = round(float(volume), 1) if volume is not None else 100.0
                title = self.send_command(["get_property", "media-title"])
                state.current_title = str(title) if title else Path(str(current_path)).name
                state.media_id = self._current_media_id
            else:
                state.is_playing = False
        except Exception:
            pass

        return state
