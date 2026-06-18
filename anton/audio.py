import subprocess
import logging
import os
import questionary


class Media:
    @staticmethod
    def get_duration(file_path):
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
