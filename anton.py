import os
import subprocess
import threading
import http.server
import time
import requests
import logging

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
import questionary
import phonenumbers

from signalwire.rest import Client
from pyngrok import ngrok, conf


class Config:
    def __init__(self):
        load_dotenv()

        self.debug = os.environ.get("DEBUG", "False").lower() in (
            "true",
            "1",
            "yes",
            "t",
        )
        logging.basicConfig(
            level=logging.DEBUG if self.debug else logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        self.project = os.environ.get("SW_PROJECT_ID")
        self.token = os.environ.get("SW_API_TOKEN")
        self.space = os.environ.get("SW_SPACE_URL")
        self.from_number = os.environ.get("SW_FROM")
        self.ngrok_token = os.environ.get("NGROK_AUTHTOKEN")

        self.model = os.environ.get("PIPER_MODEL", "pt_BR-cadu-medium")
        self.port = int(os.environ.get("PORT", 8080))
        self.default_region = os.environ.get("PHONE_REGION", "BR")
        self.country_code_prefix = os.environ.get("PHONE_PREFIX", "+55")

        self.max_audio_duration = int(os.environ.get("MAX_AUDIO_DURATION", 600))
        self.call_timeout = int(os.environ.get("CALL_TIMEOUT", 60))

        self.poll_interval = int(os.environ.get("POLL_INTERVAL", 2))
        self.fetch_retries = int(os.environ.get("FETCH_RETRIES", 15))
        self.fetch_delay = int(os.environ.get("FETCH_DELAY", 3))
        self.max_history = int(os.environ.get("MAX_HISTORY", 5))
        self.cleanup_tts = os.environ.get("CLEANUP_TTS_AUDIO", "True").lower() in (
            "true",
            "1",
            "yes",
            "t",
        )

        self.recordings_dir = os.environ.get("RECORDINGS_DIR", "recordings")
        self.history_file = os.environ.get("HISTORY_FILE", ".phone_history.txt")

    def validate(self):
        required = ["project", "token", "space", "from_number", "ngrok_token"]
        missing = [var for var in required if not getattr(self, var)]

        if missing:
            raise ValueError(f"Missing Environment Variables: {', '.join(missing)}")

        for binary in ["ffmpeg", "ffprobe"]:
            if (
                subprocess.call(
                    ["which", binary],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                != 0
            ):
                raise RuntimeError(
                    f"Dependency '{binary}' is not installed or not in PATH."
                )


class UI:
    def __init__(self):
        self.console = Console()

    def header(self):
        self.console.print(Panel.fit("[bold cyan] Remote Call Tool[/bold cyan]"))

    def status(self, message):
        return self.console.status(f"[bold cyan]{message}[/bold cyan]")

    def success(self, message):
        self.console.print(f"[green]✓[/green] {message}")

    def error(self, message):
        self.console.print(f"[bold red]✗ {message}[/bold red]")

    def print(self, message):
        self.console.print(message)


class Phone:
    @staticmethod
    def get_validator(region):
        def validator(text):
            try:
                p = phonenumbers.parse(text, region)
                return (
                    True if phonenumbers.is_valid_number(p) else "Invalid phone number."
                )
            except phonenumbers.NumberParseException:
                return f"Invalid format for region {region}."

        return validator

    @staticmethod
    def format(text, region):
        parsed = phonenumbers.parse(text, region)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class PhoneHistory:
    def __init__(self, filepath, max_entries):
        self.filepath = filepath
        self.max_entries = max_entries

    def load(self):
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def save(self, number):
        history = self.load()
        if number in history:
            history.remove(number)

        history.insert(0, number)
        history = history[: self.max_entries]

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(history))


class Media:
    @staticmethod
    def get_duration(file_path):
        """Uses ffprobe to return the audio duration in seconds."""
        try:
            r = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(r.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            logging.debug(f"Could not probe duration for {file_path}: {e}")
            return 0.0


class Audio:
    def __init__(self, model, ui):
        self.model = model
        self.ui = ui

    def generate(self, text_file):
        """Returns a tuple of (audio_file_path, was_newly_generated_boolean)"""
        audio_file = os.path.splitext(text_file)[0] + ".mp3"

        if os.path.isfile(audio_file):
            if not questionary.confirm(
                f"'{audio_file}' already exists. Overwrite?"
            ).ask():
                self.ui.success(f"Reusing existing {audio_file}")
                return audio_file, False

        with self.ui.status("Generating speech with Piper..."):
            with open(text_file, "r", encoding="utf-8") as f:
                text = f.read()

            wav_file = audio_file.replace(".mp3", ".wav")

            r = subprocess.run(
                ["python3", "-m", "piper", "-m", self.model, "-f", wav_file],
                input=text.encode("utf-8"),
                capture_output=True,
            )

            if r.returncode != 0:
                logging.error(f"Piper error stderr: {r.stderr.decode()}")
                raise RuntimeError(
                    "Piper generation failed. Enable debug mode for more info."
                )

        with self.ui.status("Converting to mp3 with ffmpeg..."):
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_file, audio_file],
                capture_output=True,
                check=True,
            )
            os.remove(wav_file)

        self.ui.success(f"Audio generated: [bold]{audio_file}[/bold]")
        return audio_file, True


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
        self.ngrok_url = None

    def __enter__(self):
        with self.ui.status("Setting up local server & tunneling..."):
            handler = get_directory_handler(self.directory, self.cfg.debug)
            self.server = http.server.HTTPServer(("", self.cfg.port), handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

            conf.get_default().auth_token = self.cfg.ngrok_token
            self.ngrok_url = ngrok.connect(self.cfg.port, "http").public_url

            audio_url = f"{self.ngrok_url}/{self.filename}"

        self.ui.success(f"Local HTTP server running on port {self.cfg.port}")
        self.ui.success(f"Ngrok tunnel active: [link={audio_url}]{audio_url}[/link]")
        return audio_url

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.ngrok_url:
            ngrok.disconnect(self.ngrok_url)


class Caller:
    TERMINAL_STATUSES = {"completed", "failed", "busy", "no-answer", "canceled"}

    def __init__(self, config, ui):
        self.cfg = config
        self.ui = ui
        self.client = Client(
            self.cfg.project, self.cfg.token, signalwire_space_url=self.cfg.space
        )

    def place_call(self, to_number, audio_url):
        with self.ui.status(f"Calling {to_number}..."):
            call = self.client.calls.create(
                to=to_number,
                from_=self.cfg.from_number,
                twiml=f"<Response><Play>{audio_url}</Play></Response>",
                record=True,
                timeout=self.cfg.call_timeout,  # Kept timeout for ringing duration, removed time_limit
            )
        self.ui.success(f"Call placed! SID: [bold dim]{call.sid}[/bold dim]")
        return call.sid

    def wait(self, call_sid):
        last_status = None
        with self.ui.status("Waiting for call status..."):
            while True:
                curr_status = self.client.calls(call_sid).fetch().status
                if curr_status != last_status:
                    self.ui.print(
                        f"  [dim]↳ Status update:[/] [bold]{curr_status}[/bold]"
                    )
                    last_status = curr_status
                if curr_status in self.TERMINAL_STATUSES:
                    return curr_status
                time.sleep(self.cfg.poll_interval)

    def fetch_recording(self, call_sid):
        with self.ui.status("Fetching recording data..."):
            for _ in range(self.cfg.fetch_retries):
                recs = self.client.recordings.list(call_sid=call_sid)
                if recs:
                    rec = recs[0]
                    url = f"{self.cfg.space.rstrip('/')}{rec.uri.replace('.json', '.mp3')}"
                    self._download_file(url, call_sid, rec.duration)
                    return
                time.sleep(self.cfg.fetch_delay)
        self.ui.error("No recording found.")

    def _download_file(self, url, call_sid, duration):
        with self.ui.status(f"Downloading recording ({duration}s)..."):
            r = requests.get(url, auth=(self.cfg.project, self.cfg.token))
            if r.ok:
                os.makedirs(self.cfg.recordings_dir, exist_ok=True)
                filepath = os.path.join(
                    self.cfg.recordings_dir, f"recording_{call_sid[:8]}.mp3"
                )
                with open(filepath, "wb") as f:
                    f.write(r.content)
                self.ui.success(f"Recording saved: [bold]{filepath}[/bold]")
            else:
                logging.debug(
                    f"Download request failed. Status: {r.status_code}, Body: {r.text}"
                )
                self.ui.error(f"Download failed: {r.status_code}")


class App:
    def __init__(self):
        self.cfg = Config()
        self.ui = UI()

    def get_destination_number(self):
        history_mgr = PhoneHistory(self.cfg.history_file, self.cfg.max_history)
        past_numbers = history_mgr.load()
        raw_number = None

        if past_numbers:
            choices = past_numbers + ["Enter new number..."]
            selection = questionary.select(
                "Select destination phone number:", choices=choices
            ).ask()

            if not selection:
                return None

            if selection != "Enter new number...":
                raw_number = selection

        if not raw_number:
            raw_number = questionary.text(
                "Enter destination phone number:",
                default=self.cfg.country_code_prefix,
                validate=Phone.get_validator(self.cfg.default_region),
            ).ask()

            if not raw_number:
                return None

        to_number = Phone.format(raw_number, self.cfg.default_region)
        history_mgr.save(to_number)
        return to_number

    @staticmethod
    def validate_file_exists(path):
        return os.path.isfile(path) or "File does not exist. Press TAB to browse."

    def run(self):
        generated_audio_cleanup_target = None

        try:
            self.ui.header()
            self.cfg.validate()

            to_number = self.get_destination_number()
            if not to_number:
                return

            mode = questionary.select(
                "Choose audio source:",
                choices=[
                    "1. TTS from text file (Piper)",
                    "2. Play existing audio file (mp3/wav)",
                ],
            ).ask()
            if not mode:
                return

            input_file = questionary.path(
                "Select the file:",
                validate=self.validate_file_exists,
            ).ask()
            if not input_file:
                return

            self.ui.print("\n[bold dim]Starting execution pipeline...[/bold dim]")

            if mode.startswith("1"):
                audio = Audio(self.cfg.model, self.ui)
                audio_file, newly_created = audio.generate(input_file)
                if newly_created and self.cfg.cleanup_tts:
                    generated_audio_cleanup_target = audio_file
            else:
                audio_file = input_file
                self.ui.success(f"Using existing audio file: [bold]{audio_file}[/bold]")

            duration = Media.get_duration(audio_file)
            if duration > self.cfg.max_audio_duration:
                self.ui.error(
                    f"Warning: Audio file is unusually long ({duration:.1f}s). Max limit is {self.cfg.max_audio_duration}s."
                )
                if not questionary.confirm(
                    "Are you sure you want to proceed and place the call?"
                ).ask():
                    self.ui.print("Operation cancelled by user.")
                    return

            with Tunnel(self.cfg, audio_file, self.ui) as audio_url:
                caller = Caller(self.cfg, self.ui)
                call_sid = caller.place_call(to_number, audio_url)

                final_status = caller.wait(call_sid)
                color = "green" if final_status == "completed" else "red"
                self.ui.print(
                    f"\n[bold]Call ended with status:[/bold] [{color}]{final_status}[/{color}]"
                )

                caller.fetch_recording(call_sid)

        except KeyboardInterrupt:
            self.ui.error("Interrupted by user. Cleaning up...")
        except Exception as e:
            logging.exception("An unexpected error occurred:")
            self.ui.error(f"An error occurred: {str(e)}")
        finally:
            self.ui.print("[dim]Shutting down services...[/dim]")

            if generated_audio_cleanup_target and os.path.exists(
                generated_audio_cleanup_target
            ):
                os.remove(generated_audio_cleanup_target)
                self.ui.success(
                    f"Cleaned up temporary audio file: [dim]{generated_audio_cleanup_target}[/dim]"
                )

            self.ui.success("Cleanup complete. Goodbye!")


if __name__ == "__main__":
    App().run()
