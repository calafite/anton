import os
import time
import logging
import requests
import phonenumbers
from signalwire.rest import Client


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
                timeout=self.cfg.call_timeout,
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
