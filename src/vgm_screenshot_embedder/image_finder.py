"""Find game screenshots using RAWG.io API."""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class RAWGClient:
    """Client for RAWG.io API to find game screenshots."""

    BASE_URL = "https://api.rawg.io/api"

    def __init__(self, api_key: str):
        """Initialize RAWG client.

        Args:
            api_key: RAWG.io API key.
        """
        self.api_key = api_key

    def find_screenshot(self, game_name: str) -> tuple[bytes, str] | None:
        """Find and download a screenshot for the given game.

        Attempts to:
        1. Search for the game by name
        2. Get screenshots for the first result
        3. Download the first available screenshot

        Args:
            game_name: Name of the game to search for.

        Returns:
            Tuple of (image_bytes, mime_type) or None if not found.
        """
        try:
            logger.debug(f"Searching for game: {game_name}")

            # Search for the game
            game_id = self._search_game(game_name)
            if game_id is None:
                logger.debug(f"No game found for: {game_name}")
                return None

            logger.debug(f"Found game ID: {game_id}")

            # Get screenshots for the game
            screenshot_url = self._get_screenshot_url(game_id)
            if screenshot_url is None:
                logger.debug(f"No screenshots found for game ID: {game_id}")
                return None

            logger.debug(f"Found screenshot URL: {screenshot_url}")

            # Download the screenshot
            result = self._download_image(screenshot_url)
            if result:
                image_data, mime_type = result
                logger.debug(
                    f"Downloaded image ({len(image_data)} bytes, {mime_type})"
                )
            return result
        except Exception as e:
            logger.debug(f"Error finding screenshot: {e}")
            return None

    def _search_game(self, game_name: str) -> int | None:
        """Search for a game by name.

        Args:
            game_name: Name of the game.

        Returns:
            Game ID if found, None otherwise.
        """
        with httpx.Client() as client:
            response = client.get(
                f"{self.BASE_URL}/games",
                params={
                    "search": game_name,
                    "key": self.api_key,
                    "page_size": 1,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("results"):
                return data["results"][0]["id"]

        return None

    def _get_screenshot_url(self, game_id: int) -> str | None:
        """Get the first screenshot URL for a game.

        Args:
            game_id: ID of the game.

        Returns:
            Screenshot URL if found, None otherwise.
        """
        with httpx.Client() as client:
            response = client.get(
                f"{self.BASE_URL}/games/{game_id}/screenshots",
                params={"key": self.api_key},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("results"):
                return data["results"][0]["image"]

        return None

    def _download_image(self, url: str) -> tuple[bytes, str] | None:
        """Download image from URL and determine MIME type.

        Args:
            url: Image URL.

        Returns:
            Tuple of (image_bytes, mime_type) or None if download fails.
        """
        with httpx.Client() as client:
            response = client.get(url, timeout=10)
            response.raise_for_status()
            image_data = response.content

        # Determine MIME type from URL extension
        path = Path(url)
        suffix = path.suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")

        return image_data, mime_type
