"""Interactive image picker using local HTTP server and browser."""

import json
import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import httpx
from compression import gzip

logger = logging.getLogger(__name__)


class ImagePickerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the image picker."""

    def do_GET(self) -> None:
        """Serve the HTML page, API endpoints, or proxy all other requests to DuckDuckGo."""
        if self.path == "/":
            # Serve our custom HTML page
            html = self.server.image_picker.generate_html()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif self.path == "/api/current":
            # Return current game and song info as JSON
            picker = self.server.image_picker
            response = {
                "game_name": picker.game_name,
                "song_title": picker.song_title
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        elif self.path == "/api/search-url":
            # Return the DuckDuckGo search URL for the current game (as relative path)
            picker = self.server.image_picker
            response = {
                "url": picker.build_duckduckgo_search_path()
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        elif self.path == "/api/is-processing":
            # Return whether the CLI is still processing files
            picker = self.server.image_picker
            response = {
                "processing": picker.is_processing
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            # Proxy all other requests to DuckDuckGo
            self._proxy_to_duckduckgo()

    def _proxy_to_duckduckgo(self) -> None:
        """Proxy a request to DuckDuckGo and return the response."""
        # Build the target URL
        target_url = f"https://duckduckgo.com{self.path}"
        if self.path.startswith("?"):
            target_url = f"https://duckduckgo.com/{self.path}"

        try:
            # Build headers to send to DuckDuckGo, forwarding most from the client request
            headers = {}

            # Headers to skip when forwarding (connection-related, host-related, etc.)
            skip_headers = {
                "host",
                "connection",
                "content-length",
                "transfer-encoding",
                "upgrade",
                "proxy-connection",
                "proxy-authenticate",
            }

            # Forward headers from the client request
            for header_name, header_value in self.headers.items():
                if header_name.lower() not in skip_headers:
                    headers[header_name] = header_value

            # Set/override important headers for DuckDuckGo
            # headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            headers["Referer"] = "https://duckduckgo.com/"
            headers["Accept-Encoding"] = "gzip"

            # Fetch from DuckDuckGo
            with httpx.Client() as client:
                response = client.get(
                    target_url, follow_redirects=True, timeout=10, headers=headers
                )
                response.raise_for_status()
                content = response.content

            # Determine content type
            content_type = response.headers.get(
                "content-type", "application/octet-stream"
            )

            # If HTML, inject JavaScript to detect image clicks
            if "text/html" in content_type:
                content_str = content.decode("utf-8", errors="ignore")
                # Inject image click detector script before closing body
                injection = r"""
                    <script>
                    let lastAsideCount = 0;
                    let lastSentUrl = null;

                    function extractImageUrlFromAside() {
                        const asides = document.querySelectorAll('aside');
                        if (asides.length === 0) return;

                        const aside = asides[asides.length - 1];

                        // Find the currently visible image (aria-hidden="false")
                        const visibleContainers = aside.querySelectorAll('[aria-hidden="false"]');
                        if (visibleContainers.length === 0) return;

                        const visibleContainer = visibleContainers[visibleContainers.length - 1];

                        // Extract image URL from the visible container
                        let imageUrl = extractUrlFromContainer(visibleContainer);

                        // Only send if we found a URL and it's different from the last one we sent
                        if (imageUrl && imageUrl !== lastSentUrl) {
                            console.log('Detected new visible image, sending URL:', imageUrl);
                            lastSentUrl = imageUrl;
                            window.parent.postMessage({type: 'image_selected', url: imageUrl}, '*');
                        }
                    }

                    function extractUrlFromContainer(container) {
                        let imageUrl = null;

                        // Look for the "View File" link with an image file extension
                        const links = container.querySelectorAll('a[href]');
                        for (const link of links) {
                            const href = link.href;

                            // Skip links to video/social sites
                            if (href.includes('youtube.com') || href.includes('facebook.com') ||
                                href.includes('instagram.com') || href.includes('twitter.com')) {
                                continue;
                            }

                            // Check if it looks like an image URL
                            if (href.match(/\.(jpg|jpeg|png|webp|gif|svg)$/i) ||
                                href.includes('image') || href.includes('presskit')) {
                                console.log('Found image link:', href);
                                return href;
                            }
                        }

                        // Fallback: try to extract from proxy URLs in img tags
                        const images = container.querySelectorAll('img[src]');
                        for (const img of images) {
                            if (img.src && img.src.includes('external-content.duckduckgo.com')) {
                                try {
                                    const srcUrl = new URL(img.src);
                                    const actualUrl = srcUrl.searchParams.get('u');
                                    if (actualUrl) {
                                        imageUrl = decodeURIComponent(actualUrl);
                                        console.log('Extracted from proxy:', imageUrl);
                                        return imageUrl;
                                    }
                                } catch (e) {
                                    console.log('Error parsing proxy URL:', e);
                                }
                            }
                        }

                        return null;
                    }

                    // Poll frequently to detect when user navigates to different images
                    setInterval(extractImageUrlFromAside, 200);
                    </script>
                    """
                # Try to inject before closing body tag
                if "</body>" in content_str:
                    content_str = content_str.replace("</body>", injection + "</body>")
                else:
                    # If no body tag, just append
                    content_str = content_str + injection
                content = content_str.encode("utf-8")

            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("X-Frame-Options", "ALLOWALL")
            # Don't cache
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.debug(f"Proxy error for {target_url}: {e}")
            self.send_response(502)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode("utf-8"))

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
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.is_processing = True  # Set to False when CLI is done

    def generate_html(self) -> str:
        """Generate the HTML page for image selection."""
        # Build search parameters for DuckDuckGo (everything after duckduckgo.com)
        search_query = f"{self.game_name} screenshot {self.song_title}"
        search_params = f"?q={quote(search_query)}&iax=images&ia=images"

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
            flex-direction: column;
            height: 100vh;
        }}
        .container {{
            background: white;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            font-size: 20px;
            margin-bottom: 8px;
            color: #333;
        }}
        .subtitle {{
            font-size: 14px;
            color: #666;
            margin-bottom: 16px;
            line-height: 1.4;
        }}
        .game-info {{
            background: #f9f9f9;
            padding: 12px;
            border-left: 4px solid #0066cc;
            margin-bottom: 16px;
            border-radius: 4px;
        }}
        .game-info strong {{ display: block; margin-bottom: 4px; }}
        .game-info span {{ color: #666; font-size: 13px; }}
        .search-section {{
            margin-bottom: 16px;
        }}
        .section-title {{
            font-size: 13px;
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .search-frame {{
            width: 100%;
            height: 400px;
            border: 1px solid #ddd;
            border-radius: 4px;
            display: none;
        }}
        .search-frame.active {{
            display: block;
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
            margin-top: 15px;
        }}
        button.primary {{
            flex: 1;
            padding: 12px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button.primary:hover {{
            background: #0052a3;
        }}
        button.primary:active {{
            background: #003d7a;
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

        <div class="search-section">
            <div class="section-title">Step 1: Search and select an image</div>
            <iframe id="searchFrame" class="search-frame active" src="/{search_params}"></iframe>
        </div>

        <div>
            <div class="section-title">Step 2: Preview selected image</div>
            <div class="preview" id="preview">Click an image to select it</div>
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
        let selectedImageUrl = null;

        // Listen for image selection from the iframe
        window.addEventListener('message', function(event) {{
            if (event.data.type === 'image_selected') {{
                selectedImageUrl = event.data.url;
                const preview = document.getElementById('preview');
                preview.className = 'preview loading';
                preview.innerHTML = 'Loading...';

                // Try to load the image to verify it works
                const img = new Image();
                img.onload = function() {{
                    preview.className = 'preview';
                    preview.innerHTML = '';
                    preview.appendChild(img);
                    document.getElementById('embedBtn').disabled = false;
                }};
                img.onerror = function() {{
                    preview.className = 'preview error';
                    preview.innerHTML = '⚠️ Failed to load image';
                    document.getElementById('embedBtn').disabled = true;
                    selectedImageUrl = null;
                }};
                img.src = selectedImageUrl;
            }}
        }});

        function waitForNextFile() {{
            // Poll for when the game/song info changes (next file)
            let lastGameName = document.querySelector('.game-info strong').textContent;
            let lastSongTitle = document.querySelector('.game-info span').textContent;

            const pollInterval = setInterval(() => {{
                fetch('/api/current')
                    .then(r => r.json())
                    .then(data => {{
                        if (data.game_name !== lastGameName || data.song_title !== lastSongTitle) {{
                            // Game/song changed - new file is ready!
                            clearInterval(pollInterval);
                            resetForNextFile();
                        }}
                    }})
                    .catch(e => console.log('Poll error:', e));
            }}, 500);
        }}

        function resetForNextFile() {{
            // Check if processing is complete
            fetch('/api/is-processing')
                .then(r => r.json())
                .then(data => {{
                    if (!data.processing) {{
                        // CLI is done - show completion message
                        showCompletionMessage();
                    }} else {{
                        // More files to process - update UI without full reload
                        // Reset state
                        selectedImageUrl = null;
                        lastSentUrl = null;
                        document.getElementById('preview').innerHTML = 'Click an image to select it';
                        document.getElementById('preview').className = 'preview';
                        document.getElementById('embedBtn').disabled = true;
                        document.getElementById('status').textContent = '';
                        document.getElementById('status').className = '';

                        // Fetch new game/song info and search URL
                        Promise.all([
                            fetch('/api/current').then(r => r.json()),
                            fetch('/api/search-url').then(r => r.json())
                        ])
                        .then(([currentData, searchData]) => {{
                            // Update game info display
                            document.querySelector('.game-info strong').textContent = currentData.game_name;
                            document.querySelector('.game-info span').textContent = currentData.song_title;

                            // Update iframe with new search URL
                            const iframe = document.getElementById('searchFrame');
                            iframe.src = searchData.url;
                        }})
                        .catch(e => {{
                            console.log('Error updating UI:', e);
                            // Fallback to reload if something goes wrong
                            window.location.reload();
                        }});
                    }}
                }})
                .catch(e => {{
                    console.log('Error checking processing status:', e);
                    // Assume still processing if we can't check
                    window.location.reload();
                }});
        }}

        function showCompletionMessage() {{
            // Hide iframe and show completion message
            const searchFrame = document.getElementById('searchFrame');
            const searchSection = searchFrame.parentElement;
            searchSection.innerHTML = '<p style="text-align: center; padding: 20px; color: #388e3c; font-size: 16px;">✓ All files processed! You can close this window.</p>';
        }}

        function embedImage() {{
            if (!selectedImageUrl) return;

            const btn = document.getElementById('embedBtn');
            const status = document.getElementById('status');
            btn.disabled = true;
            status.textContent = 'Embedding...';
            status.className = '';

            fetch('/embed', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{url: selectedImageUrl}})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.ok) {{
                    status.textContent = '✓ Image embedded! Waiting for next file...';
                    status.className = 'success';
                    btn.disabled = true;
                    waitForNextFile();
                }} else {{
                    status.textContent = '✗ Error: ' + (data.error || 'Unknown error');
                    status.className = 'error';
                    btn.disabled = false;
                }}
            }})
            .catch(e => {{
                status.textContent = '✗ Error: ' + e.message;
                status.className = 'error';
                btn.disabled = false;
            }});
        }}

        function skipFile() {{
            const status = document.getElementById('status');
            status.textContent = 'Skipping...';
            status.className = '';

            fetch('/skip', {{method: 'POST'}})
            .then(() => {{
                status.textContent = '✓ Skipped! Waiting for next file...';
                status.className = 'success';
                waitForNextFile();
            }})
            .catch(e => {{
                status.textContent = '✗ Error: ' + e.message;
                status.className = 'error';
            }});
        }}
    </script>
</body>
</html>"""

    def build_duckduckgo_images_url(self) -> str:
        """Build a DuckDuckGo Images search URL for the game/track."""
        search_query = f"{self.game_name} screenshot {self.song_title}"
        return f"https://duckduckgo.com/?q={quote(search_query)}&iax=images&ia=images"

    def build_duckduckgo_search_path(self) -> str:
        """Build a relative path for DuckDuckGo Images search (for local proxy)."""
        search_query = f"{self.game_name} screenshot {self.song_title}"
        return f"/?q={quote(search_query)}&iax=images&ia=images"

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
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip()
            )
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

        # Start HTTP server only on first call
        if self.server is None:
            self.server = ThreadingHTTPServer(("localhost", 0), ImagePickerHandler)
            self.server.image_picker = self  # type: ignore
            port = self.server.server_port

            self.server_thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.server_thread.start()

            # Open browser
            url = f"http://localhost:{port}/"
            print(f"Opening image picker at: {url}")
            webbrowser.open(url)

        # Wait for user input
        self.event.wait()

        # Keep server running for next file - don't shutdown
        return self.result
