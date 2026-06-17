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

    def configure(self):
        self.ui.header()
        self.ui.print("[bold]Interactive Configuration[/bold]\n")

        env_file = os.path.join(os.getcwd(), ".env")
        current_config = {}

        if os.path.exists(env_file):
            if not questionary.confirm(
                "A .env file already exists. Do you want to update it?"
            ).ask():
                return

            from dotenv import dotenv_values

            current_config = dotenv_values(env_file) or {}

        def require_val(text):
            return True if text.strip() else "This field cannot be empty."

        def require_int(text):
            if not text.strip():
                return "This field cannot be empty."
            return True if str(text).isdigit() else "Please enter a valid number."

        try:
            self.ui.print("[bold cyan]--- Core Settings ---[/bold cyan]")

            project = questionary.text(
                "SignalWire Project ID:",
                default=current_config.get("SW_PROJECT_ID", ""),
                validate=require_val,
            ).ask()
            if project is None:
                raise KeyboardInterrupt

            token = questionary.password(
                "SignalWire API Token:",
                default=current_config.get("SW_API_TOKEN", ""),
                validate=require_val,
            ).ask()
            if token is None:
                raise KeyboardInterrupt

            space = questionary.text(
                "SignalWire Space URL (e.g., example.signalwire.com):",
                default=current_config.get("SW_SPACE_URL", ""),
                validate=require_val,
            ).ask()
            if space is None:
                raise KeyboardInterrupt

            space = space.strip().rstrip("/")
            if not space.startswith("http://") and not space.startswith("https://"):
                space = f"https://{space}"

            region = questionary.text(
                "Default Phone Region (e.g., BR, US):",
                default=current_config.get("PHONE_REGION", "BR"),
                validate=require_val,
            ).ask()
            if region is None:
                raise KeyboardInterrupt

            raw_from_number = questionary.text(
                "SignalWire From Number:",
                default=current_config.get("SW_FROM", ""),
                validate=Phone.get_validator(region),
            ).ask()
            if raw_from_number is None:
                raise KeyboardInterrupt

            from_number = Phone.format(raw_from_number, region)

            prefix = questionary.text(
                "Default Country Code Prefix (e.g., +55, +1):",
                default=current_config.get("PHONE_PREFIX", "+55"),
                validate=require_val,
            ).ask()
            if prefix is None:
                raise KeyboardInterrupt

            self.ui.print("\n[bold cyan]--- Advanced Settings ---[/bold cyan]")
            configure_advanced = questionary.confirm(
                "Do you want to configure advanced settings (remote host, TTS model, timeouts, logging, etc.)?",
                default=False,
            ).ask()
            if configure_advanced is None:
                raise KeyboardInterrupt

            adv_config = {
                "TEMP_UPLOAD_URL": current_config.get(
                    "TEMP_UPLOAD_URL", "https://transfer.sh"
                ),
                "PIPER_MODEL": current_config.get("PIPER_MODEL", "pt_BR-cadu-medium"),
                "PORT": str(current_config.get("PORT", "8080")),
                "MAX_AUDIO_DURATION": str(
                    current_config.get("MAX_AUDIO_DURATION", "600")
                ),
                "CALL_TIMEOUT": str(current_config.get("CALL_TIMEOUT", "60")),
                "CLEANUP_TTS_AUDIO": current_config.get("CLEANUP_TTS_AUDIO", "True"),
                "RECORDINGS_DIR": current_config.get(
                    "RECORDINGS_DIR", "~/anton_recordings"
                ),
                "HISTORY_FILE": current_config.get("HISTORY_FILE", "~/.anton_history"),
                "ERROR_LOG_DIR": current_config.get("ERROR_LOG_DIR", "~/.anton_logs"),
                "MAX_LOG_FILES": str(current_config.get("MAX_LOG_FILES", "5")),
            }

            if configure_advanced:
                adv_config["TEMP_UPLOAD_URL"] = questionary.text(
                    "Remote upload host URL:",
                    default=adv_config["TEMP_UPLOAD_URL"],
                    validate=require_val,
                ).ask()
                if adv_config["TEMP_UPLOAD_URL"] is None:
                    raise KeyboardInterrupt

                adv_config["PIPER_MODEL"] = questionary.text(
                    "Piper TTS Model:",
                    default=adv_config["PIPER_MODEL"],
                    validate=require_val,
                ).ask()
                if adv_config["PIPER_MODEL"] is None:
                    raise KeyboardInterrupt

                adv_config["PORT"] = questionary.text(
                    "Local server port (for Cloudflare tunnels):",
                    default=adv_config["PORT"],
                    validate=require_int,
                ).ask()
                if adv_config["PORT"] is None:
                    raise KeyboardInterrupt

                adv_config["MAX_AUDIO_DURATION"] = questionary.text(
                    "Max audio duration in seconds:",
                    default=adv_config["MAX_AUDIO_DURATION"],
                    validate=require_int,
                ).ask()
                if adv_config["MAX_AUDIO_DURATION"] is None:
                    raise KeyboardInterrupt

                adv_config["CALL_TIMEOUT"] = questionary.text(
                    "Call timeout in seconds:",
                    default=adv_config["CALL_TIMEOUT"],
                    validate=require_int,
                ).ask()
                if adv_config["CALL_TIMEOUT"] is None:
                    raise KeyboardInterrupt

                cleanup_bool = questionary.confirm(
                    "Clean up temporary TTS audio files after completion?",
                    default=(
                        adv_config["CLEANUP_TTS_AUDIO"].lower()
                        in ("true", "1", "yes", "t")
                    ),
                ).ask()
                if cleanup_bool is None:
                    raise KeyboardInterrupt
                adv_config["CLEANUP_TTS_AUDIO"] = "True" if cleanup_bool else "False"

                adv_config["RECORDINGS_DIR"] = questionary.text(
                    "Recordings save directory:",
                    default=adv_config["RECORDINGS_DIR"],
                    validate=require_val,
                ).ask()
                if adv_config["RECORDINGS_DIR"] is None:
                    raise KeyboardInterrupt

                adv_config["HISTORY_FILE"] = questionary.text(
                    "Phone history file location:",
                    default=adv_config["HISTORY_FILE"],
                    validate=require_val,
                ).ask()
                if adv_config["HISTORY_FILE"] is None:
                    raise KeyboardInterrupt

                adv_config["ERROR_LOG_DIR"] = questionary.text(
                    "Error logs directory:",
                    default=adv_config["ERROR_LOG_DIR"],
                    validate=require_val,
                ).ask()
                if adv_config["ERROR_LOG_DIR"] is None:
                    raise KeyboardInterrupt

                adv_config["MAX_LOG_FILES"] = questionary.text(
                    "Maximum number of session error log files to keep:",
                    default=adv_config["MAX_LOG_FILES"],
                    validate=require_int,
                ).ask()
                if adv_config["MAX_LOG_FILES"] is None:
                    raise KeyboardInterrupt

            self.ui.print("")
            with self.ui.status("Validating SignalWire credentials..."):
                try:
                    from signalwire.rest import Client

                    client = Client(project, token, signalwire_space_url=space)
                    # A lightweight API call to verify the token/project combination
                    client.api.accounts(project).fetch()
                except Exception as e:
                    self.ui.error(
                        "SignalWire validation failed. The credentials or URL might be invalid."
                    )
                    self.ui.print(f"  [dim]↳ Detail: {str(e)}[/dim]")
                    if not questionary.confirm("Save configuration anyway?").ask():
                        return

            final_env_vars = {
                "SW_PROJECT_ID": project,
                "SW_API_TOKEN": token,
                "SW_SPACE_URL": space,
                "SW_FROM": from_number,
                "PHONE_REGION": region,
                "PHONE_PREFIX": prefix,
            }

            final_env_vars.update(adv_config)

            if "DEBUG" in current_config:
                final_env_vars["DEBUG"] = current_config["DEBUG"]

            with open(env_file, "w") as f:
                for key, val in final_env_vars.items():
                    f.write(f"{key}={val}\n")

            self.ui.success(f"Configuration successfully saved to {env_file}")

        except KeyboardInterrupt:
            self.ui.print("\n[dim]Configuration aborted by user.[/dim]")

    def run(self):
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

            hosting_mode = questionary.select(
                "Choose hosting mode:",
                choices=[
                    "1. Cloudflare tunnel (local network)",
                    "2. Upload to temp host (slow; 0x0, catbox, etc)",
                ],
            ).ask()
            if not hosting_mode:
                return

            while True:
                generated_audio_cleanup_target = None

                try:
                    self.ui.print(
                        "\n[bold dim]Starting execution pipeline...[/bold dim]"
                    )

                    if mode.startswith("1"):
                        audio = Audio(self.cfg.model, self.ui)
                        audio_file, newly_created = audio.generate(input_file)
                        if newly_created and self.cfg.cleanup_tts:
                            generated_audio_cleanup_target = audio_file
                    else:
                        audio_file = input_file
                        self.ui.success(
                            f"Using existing audio file: [bold]{audio_file}[/bold]"
                        )

                    duration = Media.get_duration(audio_file)
                    if duration > self.cfg.max_audio_duration:
                        self.ui.error(
                            f"Warning: Audio file is unusually long ({duration:.1f}s). Max limit is {self.cfg.max_audio_duration}s."
                        )
                        if not questionary.confirm(
                            "Are you sure you want to proceed and place the call?"
                        ).ask():
                            self.ui.print("Operation cancelled by user.")
                            break

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

                    break

                except KeyboardInterrupt:
                    raise

                except Exception as e:
                    logging.exception(f"Execution encountered an error: {str(e)}")

                    self.ui.error(f"Execution failed: {str(e)}")

                    retry = questionary.confirm(
                        "An error occurred. Do you want to retry with the same settings?"
                    ).ask()
                    if not retry:
                        break

                    self.ui.print("\n[dim]Retrying pipeline...[/dim]")

                finally:
                    self.ui.print("[dim]Cleaning up resources for this run...[/dim]")
                    if generated_audio_cleanup_target and os.path.exists(
                        generated_audio_cleanup_target
                    ):
                        try:
                            os.remove(generated_audio_cleanup_target)
                            self.ui.success(
                                f"Cleaned up temporary audio file: [dim]{generated_audio_cleanup_target}[/dim]"
                            )
                        except Exception as cleanup_err:
                            if self.cfg.debug:
                                logging.debug(
                                    f"Failed to cleanup {generated_audio_cleanup_target}: {cleanup_err}"
                                )

        except KeyboardInterrupt:
            self.ui.error("\nInterrupted by user. Exiting gracefully...")
        except Exception as e:
            logging.exception(f"Fatal system error: {str(e)}")
            self.ui.error(f"A fatal initialization error occurred: {str(e)}")
        finally:
            self.ui.success("Session closed. Goodbye!")
