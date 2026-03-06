"""Command-line interface for VGM Screenshot Embedder."""

import typer

from vgm_screenshot_embedder import __version__

app = typer.Typer(help="Embed VGM screenshots into audio files")


@app.command()
def main(
    audio_paths: list[str] = typer.Argument(
        ..., help="Audio file(s) or director(ies) to process"
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Process directories recursively"
    ),
    version: bool = typer.Option(
        False, "--version", help="Show version and exit"
    ),
) -> None:
    """Embed screenshots into audio files."""
    if version:
        typer.echo(f"vgm-screenshot-embedder {__version__}")
        raise typer.Exit()

    typer.echo(f"Processing {len(audio_paths)} path(s)")
    if recursive:
        typer.echo("Recursive mode enabled")

    for path in audio_paths:
        typer.echo(f"  - {path}")
