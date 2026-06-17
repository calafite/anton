import os
from dotenv import load_dotenv
import logging
import subprocess


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
        self.upload_url = os.environ.get("TEMP_UPLOAD_URL", "https://transfer.sh")
        self.recordings_dir = os.path.expanduser(
            os.environ.get("RECORDINGS_DIR", "~/anton_recordings")
        )
        self.history_file = os.path.expanduser(
            os.environ.get("HISTORY_FILE", "~/.anton_history")
        )

    def validate(self):
        required = ["project", "token", "space", "from_number"]
        missing = [var for var in required if not getattr(self, var)]

        if missing:
            raise ValueError(f"Missing Environment Variables: {', '.join(missing)}")

        for binary in ["ffmpeg", "ffprobe", "cloudflared"]:
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
