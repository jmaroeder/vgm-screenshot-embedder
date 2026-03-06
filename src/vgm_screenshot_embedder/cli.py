"""Command-line interface for VGM Screenshot Embedder."""

import logging
from pathlib import Path

import typer

from vgm_screenshot_embedder import __version__
from vgm_screenshot_embedder.embedder import (
    embed_artwork,
    get_artwork,
    has_artwork,
)
from vgm_screenshot_embedder.image_finder import RAWGClient
from vgm_screenshot_embedder.metadata import (
    get_game_name,
    get_song_title,
    load_audio,
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="Embed VGM screenshots into audio files")


def process_file(file_path: Path, rawg_client: RAWGClient, overwrite: bool) -> bool:
    """Process a single audio file.

    Args:
        file_path: Path to audio file.
        rawg_client: RAWG API client.
        overwrite: Whether to overwrite existing artwork.

    Returns:
        True if successful, False otherwise.
    """
    # Load audio file
    logger.debug(f"Loading audio file: {file_path}")
    audio = load_audio(file_path)
    if audio is None:
        typer.echo(
            f"[SKIP] {file_path}: Not a supported audio file",
            err=True,
        )
        return False

    # Check for existing artwork
    if has_artwork(audio) and not overwrite:
        typer.echo(
            f"[SKIP] {file_path}: Already has artwork (use --overwrite to replace)"
        )
        return False

    # Extract game name
    game_name = get_game_name(audio, file_path)
    logger.debug(f"Extracted game name: {game_name}")
    if not game_name:
        typer.echo(
            f"[ERROR] {file_path}: Could not determine game name (check album tag or parent directory)",
            err=True,
        )
        return False

    # Extract song title
    song_title = get_song_title(audio, file_path)
    logger.debug(f"Extracted song title: {song_title}")
    if not song_title:
        typer.echo(
            f"[ERROR] {file_path}: Could not determine song title (check title tag or filename)",
            err=True,
        )
        return False

    # Find screenshot
    result = rawg_client.find_screenshot(game_name)
    if not result:
        typer.echo(
            f"[ERROR] {file_path}: No screenshot found for '{game_name}'",
            err=True,
        )
        return False

    image_data, mime_type = result

    # Embed artwork
    if not embed_artwork(audio, image_data, mime_type, file_path):
        typer.echo(
            f"[ERROR] {file_path}: Failed to embed artwork",
            err=True,
        )
        return False

    typer.echo(f"[OK] {file_path}: '{game_name}' - '{song_title}'")
    return True


def walk_paths(paths: list[str], recursive: bool) -> list[Path]:
    """Walk through provided paths and yield audio files.

    Args:
        paths: List of file or directory paths.
        recursive: Whether to recurse into directories.

    Returns:
        List of Path objects to process.
    """
    files = []

    for path_str in paths:
        path = Path(path_str).expanduser().resolve()

        if path.is_file():
            files.append(path)
        elif path.is_dir():
            if recursive:
                files.extend(path.rglob("*"))
            else:
                files.extend(path.iterdir())

    return [p for p in files if p.is_file()]


@app.command()
def embed(
    audio_paths: list[str] = typer.Argument(
        ..., help="Audio file(s) or director(ies) to process"
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Process directories recursively"
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="RAWG_API_KEY",
        help="RAWG.io API key (or set RAWG_API_KEY env var)",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "-f",
        help="Overwrite existing artwork",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
) -> None:
    """Embed game screenshots into audio files.

    Extracts game name from the album tag or parent directory name,
    and song title from the title tag or filename. Finds a screenshot
    via RAWG.io and embeds it into the audio file.
    """
    # Configure logging: only vgm_screenshot_embedder modules at DEBUG level when verbose
    if verbose:
        logging.getLogger("vgm_screenshot_embedder").setLevel(logging.DEBUG)

    # Set up basic logging config if not already configured
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s: %(message)s",
        )

    if version:
        typer.echo(f"vgm-screenshot-embedder {__version__}")
        raise typer.Exit()

    if not api_key:
        typer.echo(
            "Error: RAWG_API_KEY not provided. Use --api-key or set RAWG_API_KEY env var",
            err=True,
        )
        raise typer.Exit(1)

    # Collect files to process
    files = walk_paths(audio_paths, recursive)
    if not files:
        typer.echo("Error: No audio files found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Processing {len(files)} file(s)...")

    # Initialize RAWG client
    rawg_client = RAWGClient(api_key)

    # Process each file
    success_count = 0
    for file_path in files:
        if process_file(file_path, rawg_client, overwrite):
            success_count += 1

    typer.echo(
        f"\nCompleted: {success_count}/{len(files)} files processed successfully"
    )


@app.command()
def extract(
    audio_file: str = typer.Argument(..., help="Audio file to extract artwork from"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Extract embedded artwork from an audio file.

    Saves the artwork as 'folder.jpg' or 'folder.png' in the same directory
    as the audio file. The extension depends on the image format.
    """
    # Configure logging: only vgm_screenshot_embedder modules at DEBUG level when verbose
    if verbose:
        logging.getLogger("vgm_screenshot_embedder").setLevel(logging.DEBUG)

    # Set up basic logging config if not already configured
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s: %(message)s",
        )

    file_path = Path(audio_file).expanduser().resolve()

    if not file_path.exists():
        typer.echo(f"Error: File not found: {file_path}", err=True)
        raise typer.Exit(1)

    if not file_path.is_file():
        typer.echo(f"Error: Not a file: {file_path}", err=True)
        raise typer.Exit(1)

    # Load audio file
    audio = load_audio(file_path)
    if audio is None:
        typer.echo(
            f"Error: Not a supported audio file: {file_path}",
            err=True,
        )
        raise typer.Exit(1)

    # Extract artwork
    result = get_artwork(audio)
    if not result:
        typer.echo(
            f"Error: No artwork found in: {file_path}",
            err=True,
        )
        raise typer.Exit(1)

    image_data, mime_type = result

    # Determine file extension based on MIME type
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    ext = ext_map.get(mime_type, ".jpg")

    # Save artwork
    output_path = file_path.parent / f"folder{ext}"
    try:
        output_path.write_bytes(image_data)
        typer.echo(f"Saved: {output_path}")
    except Exception as e:
        typer.echo(f"Error: Failed to write {output_path}: {e}", err=True)
        raise typer.Exit(1) from e
