# ~ anton ~
🐈 *a remote audio caller named after ufpb's stupidest clever perpetuously drooling black cat*

Anton is a Python CLI tool that rings up a phone number and plays audio. Give it a pre-existing mp3 or hand it a plain text file -> Anton generates speech using Piper, exposes it to the web via cloudflared (or uploads it to a temporary host), and bridges the phone call using SignalWire.

### ~ features ~
* **interactive config** -> fully guided terminal setup via `anton config` to validate and save your credentials.
* **number memory** -> saves and recalls your past destination numbers globally in `~/.anton_history`.
* **local TTS pipeline** -> reads text files and converts them to speech via Piper + ffmpeg.
* **flexible hosting** -> spins up a quiet local HTTP server exposed via a zero-config Cloudflare Quick Tunnel, OR uploads your audio to temporary external hosts (like transfer.sh or litterbox) if you prefer.
* **call logic** -> dials out, waits for the status, and automatically fetches the call recording.
* **safeguards** -> verifies phone formatting, probes audio length before calling, and optionally cleans up generated files.

***

### ~ prerequisites ~
Anton requires a few system-level binaries to handle audio manipulation, tunnels, and TTS. Make sure these are installed and in your PATH:
* `ffmpeg`
* `ffprobe`
* `cloudflared` (Cloudflare Tunnel daemon, only required if using the tunnel hosting mode)
* `python 3.8+`

You also need active API credentials for:
* SignalWire

***

### ~ installation ~
Clone this directory, step inside, and install the package:

```bash
pip install -e .
```
This registers the `anton` command globally on your system.

***

### ~ configuration ~
The easiest way to configure Anton is by running its built-in interactive setup, which will prompt you for your credentials, validate them with SignalWire, and generate a `.env` file for you:

```bash
> anton config
```

If you prefer to configure it manually, Anton looks for a `.env` file in the directory where you execute the command. Create a `.env` file and populate it:

```ini
# ~ required ~
SW_PROJECT_ID=your_signalwire_project_id
SW_API_TOKEN=your_signalwire_api_token
SW_SPACE_URL=your_workspace.signalwire.com
SW_FROM=+1234567890

# ~ optional tweaks ~
PIPER_MODEL=pt_BR-cadu-medium
PORT=8080
PHONE_REGION=BR
PHONE_PREFIX=+55
MAX_AUDIO_DURATION=600
CALL_TIMEOUT=60
CLEANUP_TTS_AUDIO=True
TEMP_UPLOAD_URL=https://transfer.sh
RECORDINGS_DIR=~/anton_recordings
HISTORY_FILE=~/.anton_history
ERROR_LOG_DIR=~/.anton_logs
MAX_LOG_FILES=5
DEBUG=False
```

***

### ~ usage ~
Invoke the tool from your terminal:

```bash
> anton
```

Follow the interactive prompts:
1. Select a past phone number or input a new one.
2. Choose your input mode -> `TTS from text file` OR `Existing audio file`.
3. Provide the path to the file (supports home directory paths like `~/Desktop/file.mp3`).
4. Choose your hosting mode -> `Cloudflare tunnel` OR `Upload to temp host`.

Anton handles the rest. Once the call completes, the `.mp3` recording is downloaded straight to your `~/anton_recordings` directory.

***
*meow.*
