import os
import logging
import questionary
from rich.console import Console
from rich.panel import Panel

from .config import Config
from .audio import Audio, Media
from .hosting import Tunnel, TempUpload
from .telephony import Caller, Phone, PhoneHistory


class UI:
    def __init__(self):
        self.console = Console()

    def header(self):
        self.console.print(
            Panel.fit("[bold cyan]🐈 Anton: Remote Audio Caller[/bold cyan]")
        )

    def status(self, message):
        return self.console.status(f"[bold cyan]{message}[/bold cyan]")

    def success(self, message):
        self.console.print(f"[green]✓[/green] {message}")

    def error(self, message):
        self.console.print(f"[bold red]✗ {message}[/bold red]")

    def print(self, message):
        self.console.print(message)


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
        expanded_path = os.path.expanduser(path)
        return (
            os.path.isfile(expanded_path) or "File does not exist. Press TAB to browse."
        )

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

            input_file = os.path.abspath(os.path.expanduser(input_file))

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

            hosting_mode = questionary.select(
                "Choose hosting mode:",
                choices=[
                    "1. Cloudflare tunnel (local network)",
                    "2. Upload to temp host (slow; 0x0, catbox, etc)",
                ],
            ).ask()

            if not hosting_mode:
                return

            host_ctx = (
                Tunnel(self.cfg, audio_file, self.ui)
                if hosting_mode.startswith("1")
                else TempUpload(self.cfg, audio_file, self.ui)
            )

            with host_ctx as audio_url:
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
