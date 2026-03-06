"""Embed artwork into audio files using mutagen."""

import base64
from pathlib import Path

from mutagen import File, FileType
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggflac import OggFLAC
from mutagen.oggtheora import OggTheora
from mutagen.oggvorbis import OggVorbis


def get_artwork(audio: FileType) -> tuple[bytes, str] | None:
    """Extract artwork from audio file.

    Supports: MP3 (ID3), FLAC, OGG Vorbis, OGG FLAC, OGG Theora, M4A/MP4.

    Args:
        audio: mutagen File object.

    Returns:
        Tuple of (image_bytes, mime_type) or None if no artwork found.
    """
    if audio is None:
        return None

    try:
        # MP3 with ID3 tags
        if isinstance(audio, ID3):
            for frame in audio.values():
                if isinstance(frame, APIC):
                    return frame.data, frame.mime

        # FLAC
        if isinstance(audio, FLAC):
            if audio.pictures:
                pic = audio.pictures[0]
                return pic.data, pic.mime

        # OGG FLAC
        if isinstance(audio, OggFLAC):
            if audio.pictures:
                pic = audio.pictures[0]
                return pic.data, pic.mime

        # OGG Vorbis / Theora
        if isinstance(audio, (OggVorbis, OggTheora)):
            if "METADATA_BLOCK_PICTURE" in audio:
                pic_b64 = audio["METADATA_BLOCK_PICTURE"][0]
                pic_data = base64.b64decode(pic_b64)
                pic = Picture(pic_data)
                return pic.data, pic.mime

        # M4A/MP4
        if isinstance(audio, MP4):
            if "covr" in audio:
                cover = audio["covr"][0]
                return cover, "image/jpeg"

    except Exception:
        pass

    return None


def has_artwork(audio: FileType) -> bool:
    """Check if audio file already has embedded artwork.

    Supports: MP3 (ID3), FLAC, OGG Vorbis, OGG FLAC, OGG Theora, M4A/MP4.

    Args:
        audio: mutagen File object.

    Returns:
        True if artwork is present, False otherwise.
    """
    if audio is None:
        return False

    # MP3 with ID3 tags
    if isinstance(audio, ID3):
        return any(frame.startswith("APIC") for frame in audio.keys())

    # FLAC
    if isinstance(audio, FLAC):
        return len(audio.pictures) > 0

    # OGG FLAC
    if isinstance(audio, OggFLAC):
        return len(audio.pictures) > 0

    # OGG Vorbis / OGG Theora
    if isinstance(audio, (OggVorbis, OggTheora)):
        return "METADATA_BLOCK_PICTURE" in audio

    # M4A/MP4
    if isinstance(audio, MP4):
        return "covr" in audio

    # Try generic check via tags
    if hasattr(audio, "tags") and audio.tags is not None:
        return "METADATA_BLOCK_PICTURE" in audio.tags

    return False


def embed_artwork(
    audio: FileType, image_data: bytes, mime_type: str, path: Path
) -> bool:
    """Embed artwork into audio file (format-specific).

    Supports: MP3 (ID3), FLAC, OGG Vorbis, OGG FLAC, M4A/MP4.

    Args:
        audio: mutagen File object.
        image_data: Image bytes.
        mime_type: MIME type (e.g., 'image/jpeg').
        path: Path to audio file (needed to reload for some formats).

    Returns:
        True if successful, False otherwise.
    """
    try:
        # MP3 with ID3 tags
        if isinstance(audio, ID3):
            audio.add(
                APIC(
                    encoding=3,
                    mime=mime_type,
                    type=3,  # Cover Front
                    desc="",
                    data=image_data,
                )
            )
            audio.save(v2_version=4)
            return True

        # FLAC
        if isinstance(audio, FLAC):
            pic = Picture()
            pic.data = image_data
            pic.mime = mime_type
            pic.type = 3  # Cover Front
            audio.add_picture(pic)
            audio.save()
            return True

        # OGG FLAC
        if isinstance(audio, OggFLAC):
            pic = Picture()
            pic.data = image_data
            pic.mime = mime_type
            pic.type = 3
            audio.add_picture(pic)
            audio.save()
            return True

        # OGG Vorbis / Theora
        if isinstance(audio, (OggVorbis, OggTheora)):
            pic = Picture()
            pic.data = image_data
            pic.mime = mime_type
            pic.type = 3
            pic_data = pic.write()
            audio["METADATA_BLOCK_PICTURE"] = [
                base64.b64encode(pic_data).decode("ascii")
            ]
            audio.save()
            return True

        # M4A/MP4
        if isinstance(audio, MP4):
            format_map = {
                "image/jpeg": MP4Cover.FORMAT_JPEG,
                "image/png": MP4Cover.FORMAT_PNG,
            }
            fmt = format_map.get(mime_type, MP4Cover.FORMAT_JPEG)
            audio["covr"] = [MP4Cover(image_data, fmt)]
            audio.save()
            return True

        return False
    except Exception:
        return False
