"""Extract game and song metadata from audio files."""

from pathlib import Path

from mutagen import File, FileType


def load_audio(path: Path) -> FileType | None:
    """Load audio file using mutagen with easy tag interface.

    Args:
        path: Path to audio file.

    Returns:
        mutagen File object with easy tags, or None if not a valid audio file.
    """
    try:
        audio = File(path, easy=True)
        return audio if audio is not None else None
    except Exception:
        return None


def get_game_name(audio: FileType, path: Path) -> str | None:
    """Extract game name from audio tags or directory name.

    Attempts to find game name in this order:
    1. 'album' tag from audio metadata
    2. Parent directory name

    Args:
        audio: mutagen File object with easy tags.
        path: Path to audio file.

    Returns:
        Game name, or None if not found.
    """
    if audio is None:
        return None

    # Try album tag first
    if "album" in audio:
        album = audio["album"]
        if album and isinstance(album, list):
            album = album[0]
        if album and isinstance(album, str) and album.strip():
            return album.strip()

    # Fall back to parent directory name
    parent_name = path.parent.name
    if parent_name and parent_name != ".":
        return parent_name

    return None


def get_song_title(audio: FileType, path: Path) -> str | None:
    """Extract song title from audio tags or filename.

    Attempts to find song title in this order:
    1. 'title' tag from audio metadata
    2. Filename (without extension)

    Args:
        audio: mutagen File object with easy tags.
        path: Path to audio file.

    Returns:
        Song title, or None if not found.
    """
    if audio is None:
        return None

    # Try title tag first
    if "title" in audio:
        title = audio["title"]
        if title and isinstance(title, list):
            title = title[0]
        if title and isinstance(title, str) and title.strip():
            return title.strip()

    # Fall back to filename (without extension)
    filename = path.stem
    if filename and filename.strip():
        return filename.strip()

    return None
