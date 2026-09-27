# 🍓 RaspiMedia

> **High-Performance, Read-Only Media Library & Hardware Player for Raspberry Pi & Linux**

RaspiMedia is designed for user-provided media collections on Raspberry Pi and Linux. It indexes your real media files directly from your storage devices (SD Card, USB HDD/SSD, SATA, Network mounts) and plays them via hardware-accelerated MPV directly to HDMI with **zero transcoding, zero file duplication, and strict read-only safety**.

---

## 🔒 Strict Read-Only Philosophy

RaspiMedia works directly on your **existing media files**:

* ❌ **Never creates dummy files or downloads samples**
* ❌ **Never copies or duplicates your media**
* ❌ **Never moves, renames, or deletes your files**
* ❌ **Never performs transcoding**
* ❌ **Never modifies `/etc/fstab` or auto-formats storage drives**
* ✅ **100% Real metadata & database records matching real disk paths**

---

## 🚀 Key Features

* **Recursive & Incremental Scanner**: Fast scanner that inspects file modification times (`mtime`) and sizes (`size`) to skip unchanged files instantly.
* **Intelligent Metadata Parser**: Reads ID3/Vorbis/FLAC/MP4 tags with fallback parsing that cleanly extracts Series name, Season, Episode, and Title (e.g. `S01E03 - The Journey.mkv` parsed cleanly rather than "Unknown Media").
* **Hardware MPV IPC Playback**: Communicates with MPV via JSON-IPC socket (`loadfile <real_path> replace`). Zero temp files, direct HDMI audio/video output.
* **Non-Destructive Storage Detection**: Safely validates configured paths (`Ready`, `Missing`, `Permission Error`). Unmounted drives display a warning without purging your library.
* **Modern Glassmorphism Web UI & Remote**: Responsive control dashboard with instant search, real-time library counts (`Videos: 248`, `Music: 1,024`), category filters, and live player controls.
* **Command Line Interface (`raspimedia`)**: First-class CLI support for scanning, status inspection, and direct playback.

---

## 📦 Supported Formats

| Media Type | Formats Supported |
| :--- | :--- |
| **Audio** | `.mp3`, `.flac`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.wma`, `.alac`, `.aiff`, `.ape` |
| **Video** | `.mp4`, `.mkv`, `.avi`, `.webm`, `.mov`, `.m4v`, `.ts`, `.m2ts`, `.wmv`, `.vob`, `.flv` |

---

## ⚙️ Configuration (`config.toml`)

Configure one or more media directories:

```toml
[media]
directories = [
    "/mnt/media",
    "/mnt/storage/Music",
    "/mnt/storage/Movies",
    "/mnt/storage/Series"
]

[server]
host = "0.0.0.0"
port = 8080

[mpv]
ipc_socket = "/tmp/mpvsocket"
executable = "mpv"
default_args = [
    "--no-terminal",
    "--force-window=immediate",
    "--hwdec=auto-safe"
]

[cache]
thumbnail_dir = "/var/cache/raspimedia/thumbnails"
```

---

## 💻 CLI Usage

### 1. Incremental Scan
```bash
raspimedia scan
```
**Output Example:**
```text
Scanning media...

Directory:
  /mnt/media
  /mnt/storage/Music

Found:
  Audio: 1024
  Video: 248

Added:
  17

Updated:
  6

Removed:
  2

Unchanged:
  1247

Scan completed in 1.42s.
```

### 2. Force Full Rescan
```bash
raspimedia scan --force
```

### 3. Check System & Storage Status
```bash
raspimedia status
```

### 4. Play Media on MPV
```bash
# By database ID
raspimedia play 42

# Or by real filesystem path
raspimedia play "/mnt/media/Movies/Inception.mkv"
```

### 5. Start Web Server & Remote Control
```bash
raspimedia server --host 0.0.0.0 --port 8080
```

---

## 🏗️ Architecture Flow

```text
Configured Directories (USB/SD/Network)
                 ↓
      Recursive Media Scanner
                 ↓
    Metadata Extraction (Mutagen / Fallback)
                 ↓
           SQLite Database
                 ↓
    FastAPI REST API / Web UI / CLI
                 ↓
         MPV JSON-IPC Controller
                 ↓
      Hardware HDMI Output (Raspberry Pi)
```

---

## 🧪 Running Tests

```bash
pytest
```
All unit and integration tests run with 100% real filesystem tests in isolated temporary directories.
