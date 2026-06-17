import os
import http.server
import subprocess
import requests
import logging
import threading
import time
import re
import urllib.parse


def get_directory_handler(directory, debug_mode=False):
    class DirectoryQuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format, *args):
            if debug_mode:
                logging.debug(f"HTTP Server: {format % args}")

    return DirectoryQuietHandler


class Tunnel:
    def __init__(self, cfg, file_path, ui):
        self.cfg = cfg
        self.file_path = os.path.abspath(file_path)
        self.directory = os.path.dirname(self.file_path)
        self.filename = os.path.basename(self.file_path)
        self.ui = ui
        self.server = None
        self.tunnel_process = None
        self.tunnel_url = None

    def __enter__(self):
        with self.ui.status("Setting up local server & tunneling..."):
            handler = get_directory_handler(self.directory, self.cfg.debug)
            self.server = http.server.HTTPServer(("", self.cfg.port), handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

            self.tunnel_process = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", f"http://localhost:{self.cfg.port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if not self.tunnel_process.stderr:
                raise RuntimeError("Failed to open stderr for cloudflared process.")

            start_time = time.time()
            while time.time() - start_time < 15:
                if self.tunnel_process.poll() is not None:
                    raise RuntimeError("Cloudflared crashed unexpectedly.")

                line = self.tunnel_process.stderr.readline()

                if not line:
                    break

                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    self.tunnel_url = match.group(0)
                    break

            if not self.tunnel_url:
                self.tunnel_process.terminate()
                raise RuntimeError("Timed out waiting for Cloudflare Tunnel URL.")

            safe_filename = urllib.parse.quote(self.filename)
            audio_url = f"{self.tunnel_url}/{safe_filename}"

            for attempt in range(20):
                try:
                    r = requests.head(audio_url, timeout=5)
                    if r.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                logging.debug(
                    f"Tunnel not ready yet (attempt {attempt + 1}/20), retrying..."
                )
                time.sleep(1)
            else:
                self.tunnel_process.terminate()
                raise RuntimeError("Tunnel came up but never started serving the file.")

        self.ui.success(f"Local HTTP server running on port {self.cfg.port}")
        self.ui.success(
            f"Cloudflare tunnel active: [link={audio_url}]{audio_url}[/link]"
        )
        return audio_url

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.tunnel_process:
            self.tunnel_process.terminate()
            try:
                self.tunnel_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.tunnel_process.kill()


class TempUpload:
    def __init__(self, cfg, file_path, ui):
        self.cfg = cfg
        self.file_path = file_path
        self.ui = ui

    def _upload(self):
        url = self.cfg.upload_url
        filename = os.path.basename(self.file_path)

        with open(self.file_path, "rb") as f:
            if "litterbox.catbox.moe" in url:
                r = requests.post(
                    url,
                    data={"reqtype": "fileupload", "time": "72h"},
                    files={"fileToUpload": (filename, f, "audio/mpeg")},
                    timeout=60,
                )
            elif "transfer.sh" in url:
                r = requests.put(
                    f"{url.rstrip('/')}/{filename}",
                    data=f,
                    timeout=60,
                )
            else:
                r = requests.post(
                    url,
                    files={"file": (filename, f, "audio/mpeg")},
                    timeout=60,
                )

        if not r.ok:
            raise RuntimeError(f"Upload failed: {r.status_code} {r.text}")
        return r.text.strip()

    def __enter__(self):
        with self.ui.status(f"Uploading audio to {self.cfg.upload_url}..."):
            public_url = self._upload()
        self.ui.success(f"Audio hosted at: [link={public_url}]{public_url}[/link]")
        return public_url

    def __exit__(self, *_):
        pass
