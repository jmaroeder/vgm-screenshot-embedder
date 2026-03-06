"""Interactive image picker using local HTTP server and browser."""

import json
import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger(__name__)


class ImagePickerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the image picker."""

    def do_GET(self) -> None:
        """Serve the HTML page."""
        if self.path == "/":
            html = self.server.image_picker.generate_html()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        """Handle /embed and /skip endpoints."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path == "/embed":
            try:
                data = json.loads(body)
                url = data.get("url", "").strip()
                if not url:
                    response = {"ok": False, "error": "No URL provided"}
                else:
                    result = self.server.image_picker.download_image(url)
                    if result:
                        self.server.image_picker.result = result
                        self.server.image_picker.event.set()
                        response = {"ok": True}
                    else:
                        response = {"ok": False, "error": "Failed to download image"}
            except Exception as e:
                response = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/skip":
            self.server.image_picker.result = None
            self.server.image_picker.event.set()
            response = {"ok": True}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default logging."""
        pass


class ImagePicker:
    """Interactive image picker using browser and local HTTP server."""

    def __init__(self) -> None:
        """Initialize the picker."""
        self.result: tuple[bytes, str] | None = None
        self.event = threading.Event()
        self.game_name = ""
        self.song_title = ""
        self.server: HTTPServer | None = None
        self.server_thread: threading.Thread | None = None

    def generate_html(self) -> str:
        """Generate the HTML page for image selection."""
        duckduckgo_images_url = self.build_duckduckgo_images_url()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VGM Screenshot Embedder</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 100%;
            padding: 30px;
        }}
        h1 {{
            font-size: 20px;
            margin-bottom: 8px;
            color: #333;
        }}
        .subtitle {{
            font-size: 14px;
            color: #666;
            margin-bottom: 24px;
            line-height: 1.4;
        }}
        .game-info {{
            background: #f9f9f9;
            padding: 12px;
            border-left: 4px solid #0066cc;
            margin-bottom: 20px;
            border-radius: 4px;
        }}
        .game-info strong {{ display: block; margin-bottom: 4px; }}
        .game-info span {{ color: #666; font-size: 13px; }}
        .section {{
            margin-bottom: 20px;
        }}
        .section-title {{
            font-size: 13px;
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        button.primary {{
            display: block;
            width: 100%;
            padding: 12px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 10px;
            transition: background 0.2s;
        }}
        button.primary:hover {{
            background: #0052a3;
        }}
        button.primary:active {{
            background: #003d7a;
        }}
        input[type="text"] {{
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            margin-bottom: 10px;
            font-family: monospace;
        }}
        input[type="text"]:focus {{
            outline: none;
            border-color: #0066cc;
            box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.1);
        }}
        .preview {{
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 10px;
            text-align: center;
            margin-bottom: 15px;
            min-height: 100px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #999;
            font-size: 13px;
        }}
        .preview img {{
            max-width: 100%;
            max-height: 300px;
            border-radius: 2px;
        }}
        .preview.loading {{
            animation: pulse 1s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 0.6; }}
            50% {{ opacity: 1; }}
        }}
        .button-group {{
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }}
        button.secondary {{
            flex: 1;
            padding: 12px;
            background: #e0e0e0;
            color: #333;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button.secondary:hover {{
            background: #d0d0d0;
        }}
        .status {{
            margin-top: 15px;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}
        .error {{
            color: #d32f2f;
        }}
        .success {{
            color: #388e3c;
        }}
        button:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 VGM Screenshot Embedder</h1>
        <p class="subtitle">Find and embed a screenshot for your audio file</p>

        <div class="game-info">
            <strong>{self.game_name}</strong>
            <span>{self.song_title}</span>
        </div>

        <div class="section">
            <div class="section-title">Step 1: Find an image</div>
            <button class="primary" onclick="openImageSearch()">
                🔍 Search DuckDuckGo Images
            </button>
        </div>

        <div class="section">
            <div class="section-title">Step 2: Paste image URL</div>
            <input
                type="text"
                id="imageUrl"
                placeholder="https://example.com/image.jpg"
                spellcheck="false"
                oninput="onUrlInput()"
            />
            <div class="preview" id="preview">No image selected</div>
        </div>

        <div class="button-group">
            <button class="primary" id="embedBtn" onclick="embedImage()" disabled>
                ✓ Embed This Image
            </button>
            <button class="secondary" onclick="skipFile()">→ Skip</button>
        </div>

        <div class="status" id="status"></div>
    </div>

    <script>
        const imageSearchUrl = "{duckduckgo_images_url}";
        let previewTimeout;

        function openImageSearch() {{
            window.open(imageSearchUrl, "image_search");
        }}

        function onUrlInput() {{
            const url = document.getElementById("imageUrl").value.trim();
            clearTimeout(previewTimeout);

            if (!url) {{
                document.getElementById("preview").innerHTML = "No image selected";
                document.getElementById("embedBtn").disabled = true;
                return;
            }}

            // Debounce preview
            previewTimeout = setTimeout(() => {{
                const preview = document.getElementById("preview");
                preview.className = "preview loading";
                preview.innerHTML = "Loading...";

                // Try to load image
                const img = new Image();
                img.onload = () => {{
                    preview.className = "preview";
                    preview.innerHTML = "";
                    preview.appendChild(img);
                    document.getElementById("embedBtn").disabled = false;
                }};
                img.onerror = () => {{
                    preview.className = "preview error";
                    preview.innerHTML = "⚠️ Failed to load image (bad URL or CORS issue)";
                    document.getElementById("embedBtn").disabled = true;
                }};
                img.src = url;
            }}, 300);
        }}

        function embedImage() {{
            const url = document.getElementById("imageUrl").value.trim();
            if (!url) return;

            const btn = document.getElementById("embedBtn");
            const status = document.getElementById("status");
            btn.disabled = true;
            status.textContent = "Embedding...";
            status.className = "";

            fetch("/embed", {{
                method: "POST",
                headers: {{"Content-Type": "application/json"}},
                body: JSON.stringify({{url: url}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.ok) {{
                    status.textContent = "✓ Image embedded! Closing...";
                    status.className = "success";
                    setTimeout(() => window.close(), 1000);
                }} else {{
                    status.textContent = "✗ Error: " + (data.error || "Unknown error");
                    status.className = "error";
                    btn.disabled = false;
                }}
            }})
            .catch(e => {{
                status.textContent = "✗ Error: " + e.message;
                status.className = "error";
                btn.disabled = false;
            }});
        }}

        function skipFile() {{
            const status = document.getElementById("status");
            status.textContent = "Skipping...";
            status.className = "";

            fetch("/skip", {{method: "POST"}})
            .then(() => {{
                status.textContent = "✓ Skipped. Closing...";
                status.className = "success";
                setTimeout(() => window.close(), 1000);
            }})
            .catch(e => {{
                status.textContent = "✗ Error: " + e.message;
                status.className = "error";
            }});
        }}
    </script>
</body>
</html>"""

    def build_duckduckgo_images_url(self) -> str:
        """Build a DuckDuckGo Images search URL for the game/track."""
        search_query = f"{self.game_name} screenshot {self.song_title}"
        return f"https://duckduckgo.com/?q={quote(search_query)}&iax=images&ia=images"

    def download_image(self, url: str) -> tuple[bytes, str] | None:
        """Download an image from a URL.

        Args:
            url: Image URL.

        Returns:
            Tuple of (image_bytes, mime_type) or None if download fails.
        """
        try:
            with httpx.Client() as client:
                response = client.get(url, follow_redirects=True, timeout=10)
                response.raise_for_status()
                image_data = response.content

            # Determine MIME type from Content-Type header first
            content_type = response.headers.get("content-type", "").split(";")[0].strip()
            if content_type and content_type.startswith("image/"):
                mime_type = content_type
            else:
                # Fall back to extension-based detection
                path = Path(url.split("?")[0])  # Remove query params
                suffix = path.suffix.lower()
                mime_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }.get(suffix, "image/jpeg")

            logger.debug(f"Downloaded image ({len(image_data)} bytes, {mime_type})")
            return image_data, mime_type
        except Exception as e:
            logger.debug(f"Failed to download image from {url}: {e}")
            return None

    def pick(self, game_name: str, song_title: str) -> tuple[bytes, str] | None:
        """Open browser and let user pick an image.

        Args:
            game_name: Name of the game.
            song_title: Title of the song/track.

        Returns:
            Tuple of (image_bytes, mime_type) or None if skipped.
        """
        self.game_name = game_name
        self.song_title = song_title
        self.result = None
        self.event.clear()

        # Start HTTP server
        self.server = HTTPServer(("localhost", 0), ImagePickerHandler)
        self.server.image_picker = self
        port = self.server.server_port

        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

        # Open browser
        url = f"http://localhost:{port}/"
        logger.debug(f"Opening browser at {url}")
        webbrowser.open(url)

        # Wait for user input
        self.event.wait()

        # Shutdown server
        if self.server:
            self.server.shutdown()
            self.server.server_close()

        return self.result
