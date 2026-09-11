"""Speech-to-text and text-to-speech via Hack Club AI's Replicate proxy.

Proxy source:
  https://github.com/hackclub/ai/blob/main/src/routes/proxy/v1/replicate.ts

Base URL:
  https://ai.hackclub.com/proxy/v1/replicate

Never put `model` in the JSON body. Replicate's POST /v1/predictions schema
rejects it with 422 "Additional property model is not allowed". Hack Club
forwards that body as-is on POST /predictions.

Community models (Whisper) must use the version in the PATH. That route
strips `model`/`version` from the body and sends only input + canonical
version to Replicate:

  POST /models/{owner}/{name}:{version}/predictions
  {"input": {...}}

Official models (Inworld TTS) use the unversioned official path:

  POST /models/{owner}/{name}/predictions
  {"input": {...}}

Pinned Whisper version is from Hack Club's allowlist:
  src/config/allowed-replicate-model-versions.json
"""
import base64
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

REPLICATE_BASE_URL = "https://ai.hackclub.com/proxy/v1/replicate"

STT_OWNER = "vaibhavs10"
STT_NAME = "incredibly-fast-whisper"
STT_VERSION = "3ab86df6c8f54c11309d4d1f930ac292bad43ace52d10c80d87eb258b3c9f79c"
TTS_OWNER = "inworld"
TTS_NAME = "realtime-tts-1.5-mini"
DEFAULT_TTS_VOICE = "Ashley"
GEMINI_STT_MODELS = (
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-flash",
    "google/gemini-3-flash-preview",
)
STT_PROMPT = (
    "Transcribe this voice recording verbatim. "
    "Return only the spoken words. No quotes, labels, or commentary. "
    "If there is no speech, return an empty string."
)

SYNC_WAIT_SECONDS = 25
POLL_INTERVAL_SECONDS = 0.6
POLL_TIMEOUT_SECONDS = 45
REQUEST_TIMEOUT_SECONDS = SYNC_WAIT_SECONDS + 15


class VoiceError(Exception):
    """Raised for any STT/TTS failure. Callers show str(e) directly."""
    pass


def _api_key():
    api_key = os.getenv("API_KEY")
    try:
        from storage import db
        profile = db.get_profile()
        custom_key = (profile or {}).get("byo_api_key")
        if custom_key:
            api_key = custom_key
    except Exception:
        pass
    return api_key


def _headers():
    return {
        "Authorization": "Bearer %s" % _api_key(),
        "Content-Type": "application/json",
        "Prefer": "wait=%s" % SYNC_WAIT_SECONDS,
    }


def _prediction_id(prediction):
    if not isinstance(prediction, dict):
        return None
    pred_id = prediction.get("id")
    if pred_id:
        return pred_id
    get_url = (prediction.get("urls") or {}).get("get") or ""
    if "/predictions/" in get_url:
        return get_url.rstrip("/").split("/predictions/")[-1].split("?")[0]
    return None


def _wait_for_output(prediction, cancel_check=None, on_partial=None):
    if not isinstance(prediction, dict):
        return prediction

    status = prediction.get("status")
    if status == "succeeded":
        return prediction.get("output")
    if status == "failed":
        raise VoiceError("Voice generation failed: %s" % (prediction.get("error") or "unknown error"))
    if status == "canceled":
        raise VoiceError("Cancelled.")

    pred_id = _prediction_id(prediction)
    if not pred_id:
        raise VoiceError("Voice service didn't return a prediction to track.")

    elapsed = 0.0
    headers = _headers()
    while elapsed < POLL_TIMEOUT_SECONDS:
        if cancel_check and cancel_check():
            raise VoiceError("Cancelled.")
        try:
            poll_resp = requests.get(
                "%s/predictions/%s" % (REPLICATE_BASE_URL, pred_id),
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise VoiceError("Lost connection while waiting on the voice service: %s" % e)

        if poll_resp.status_code >= 400:
            raise VoiceError(
                "Voice service rejected the request (%s): %s"
                % (poll_resp.status_code, poll_resp.text[:200])
            )

        result = poll_resp.json()
        status = result.get("status")
        if on_partial:
            logs = result.get("logs") or ""
            partial = result.get("output")
            snippet = ""
            if isinstance(partial, str) and partial.strip():
                snippet = partial.strip()
            elif logs:
                snippet = str(logs).strip().splitlines()[-1][:180]
            if snippet:
                try:
                    on_partial(snippet)
                except Exception:
                    pass
        if status == "succeeded":
            return result.get("output")
        if status == "failed":
            raise VoiceError("Voice generation failed: %s" % (result.get("error") or "unknown error"))
        if status == "canceled":
            raise VoiceError("Cancelled.")

        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    raise VoiceError("Voice service is taking too long to respond. Try again in a moment.")


def _create_prediction(path, input_payload, cancel_check=None, on_partial=None):
    """POST a prediction. Body is only {"input": ...} — never model or version."""
    try:
        resp = requests.post(
            "%s/%s" % (REPLICATE_BASE_URL, path.lstrip("/")),
            headers=_headers(),
            json={"input": input_payload},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise VoiceError("Couldn't reach the voice service: %s" % e)

    if resp.status_code >= 400:
        raise VoiceError(
            "Voice service rejected the request (%s): %s"
            % (resp.status_code, resp.text[:200])
        )
    return _wait_for_output(resp.json(), cancel_check=cancel_check, on_partial=on_partial)


def _as_transcript(output):
    if output is None:
        return ""
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, dict):
        for key in ("text", "transcription", "transcript", "output"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        chunks = output.get("chunks") or output.get("segments")
        if isinstance(chunks, list):
            parts = []
            for chunk in chunks:
                if isinstance(chunk, dict) and chunk.get("text"):
                    parts.append(str(chunk["text"]))
                elif isinstance(chunk, str):
                    parts.append(chunk)
            return " ".join(parts).strip()
    if isinstance(output, list):
        return " ".join(_as_transcript(item) for item in output).strip()
    return str(output).strip()


def _as_audio_url(output):
    if output is None:
        return ""
    if isinstance(output, str) and output.startswith(("http://", "https://", "data:")):
        return output
    if isinstance(output, dict):
        for key in ("url", "audio", "wav", "mp3", "output", "audio_url"):
            value = output.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://", "data:")):
                return value
            found = _as_audio_url(value)
            if found:
                return found
        urls = output.get("urls")
        if isinstance(urls, dict):
            return _as_audio_url(urls.get("get") or urls.get("stream"))
    if isinstance(output, list) and output:
        return _as_audio_url(output[0])
    url = getattr(output, "url", None)
    if callable(url):
        try:
            url = url()
        except Exception:
            url = None
    if isinstance(url, str) and url.startswith(("http://", "https://", "data:")):
        return url
    return ""


def upload_audio_file(file_path):
    """Talk page still calls this. Returns a data URI so we never POST /files."""
    with open(file_path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return "data:audio/wav;base64,%s" % encoded


def _audio_bytes(audio_url):
    if isinstance(audio_url, str) and audio_url.startswith("data:") and "," in audio_url:
        return base64.b64decode(audio_url.split(",", 1)[1])
    if isinstance(audio_url, str) and os.path.exists(audio_url):
        with open(audio_url, "rb") as handle:
            return handle.read()
    if isinstance(audio_url, str) and audio_url.startswith("http"):
        resp = requests.get(audio_url, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.content
    raise VoiceError("Couldn't read the recording.")


def _gemini_transcribe(audio_bytes, cancel_check=None):
    import models

    encoded = base64.b64encode(audio_bytes).decode("ascii")
    content = [
        {"type": "text", "text": STT_PROMPT},
        {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}},
    ]
    last_error = None
    for model_id in GEMINI_STT_MODELS:
        if cancel_check and cancel_check():
            raise VoiceError("Cancelled.")
        try:
            response = models.run_manager_step(
                model_id,
                [{"role": "user", "content": content}],
                max_tokens=512,
                cancel_check=cancel_check,
            )
            message = response.choices[0].message
            text = models.message_text(message).strip()
            if text:
                return text
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return ""


def _whisper_transcribe(audio_url, audio_bytes, cancel_check=None):
    data_uri = audio_url
    if not (isinstance(audio_url, str) and audio_url.startswith("data:")):
        data_uri = "data:audio/wav;base64,%s" % base64.b64encode(audio_bytes).decode("ascii")
    output = _create_prediction(
        "models/%s/%s:%s/predictions" % (STT_OWNER, STT_NAME, STT_VERSION),
        {"audio": data_uri, "task": "transcribe", "batch_size": 8},
        cancel_check=cancel_check,
    )
    return _as_transcript(output)


def transcribe_audio(audio_url, cancel_check=None, engine=None, on_partial=None):
    audio_bytes = _audio_bytes(audio_url)
    if engine is None:
        try:
            from core.thinking import listening_model
            engine = listening_model()
        except Exception:
            engine = "gemini"

    errors = []
    order = ("whisper", "gemini") if engine == "whisper" else ("gemini", "whisper")
    for name in order:
        try:
            if on_partial:
                try:
                    on_partial("Listening with %s…" % name)
                except Exception:
                    pass
            if name == "gemini":
                text = _gemini_transcribe(audio_bytes, cancel_check=cancel_check)
            else:
                text = _whisper_transcribe(audio_url, audio_bytes, cancel_check=cancel_check)
            if text:
                if on_partial:
                    try:
                        on_partial(text)
                    except Exception:
                        pass
                return text
        except Exception as exc:
            errors.append("%s: %s" % (name, exc))

    if errors:
        raise VoiceError("Didn't catch that — %s" % errors[-1])
    raise VoiceError("Didn't catch that — no speech was detected in the recording.")


def synthesize_speech(text, voice=DEFAULT_TTS_VOICE, cancel_check=None, on_partial=None):
    """Paid Replicate TTS. Talk page no longer uses this — system voices are free."""
    if not text or not text.strip():
        raise VoiceError("Nothing to say — the reply was empty.")
    output = _create_prediction(
        "models/%s/%s/predictions" % (TTS_OWNER, TTS_NAME),
        {
            "text": text.strip(),
            "voice_id": voice or DEFAULT_TTS_VOICE,
            "audio_format": "mp3",
        },
        cancel_check=cancel_check,
        on_partial=on_partial,
    )
    url = _as_audio_url(output)
    if not url:
        raise VoiceError("The voice model responded but didn't return any audio.")
    return url


def mac_premium_voice():
    """Pick a downloaded Enhanced/Premium macOS voice, then a Siri/Samantha voice."""
    import shutil
    import subprocess

    if not shutil.which("say"):
        return None
    try:
        raw = subprocess.check_output(["say", "-v", "?"], text=True, stderr=subprocess.STDOUT)
    except Exception:
        return None

    names = []
    for line in raw.splitlines():
        if "#" in line:
            name = line.split("#", 1)[0].rstrip()
        else:
            name = line.rstrip()
        # Voice name is everything before the locale column.
        parts = name.split()
        locale_idx = next((i for i, part in enumerate(parts) if "_" in part or part.startswith("en")), None)
        voice = " ".join(parts[:locale_idx] if locale_idx else parts).strip()
        if voice:
            names.append(voice)

    for needle in ("Premium", "Enhanced"):
        for voice in names:
            if needle.lower() in voice.lower() and ("en_" in voice.lower() or True):
                if any(tag in voice for tag in ("Premium", "Enhanced", "Samantha", "Allison", "Zoe", "Nicky", "Evan", "Siri")):
                    return voice
        matches = [voice for voice in names if needle.lower() in voice.lower()]
        if matches:
            return matches[0]
    for preferred in ("Samantha (Premium)", "Allison (Premium)", "Zoe (Premium)", "Samantha", "Allison", "Siri Voice 1"):
        if preferred in names:
            return preferred
    return names[0] if names else None


def system_say_command(text):
    """Free TTS via the OS speech engine. Prefers Mac Premium/Enhanced voices."""
    import shutil
    import sys

    spoken = (text or "").strip()
    if not spoken:
        return None
    if sys.platform == "darwin" and shutil.which("say"):
        voice = mac_premium_voice()
        if voice:
            return ["say", "-v", voice, spoken]
        return ["say", spoken]
    if sys.platform.startswith("win"):
        escaped = spoken.replace("'", "''")
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak('%s')" % escaped,
        ]
    for binary in ("espeak-ng", "espeak", "spd-say"):
        if shutil.which(binary):
            return [binary, spoken]
    return None


def system_record_command(wav_path, sample_rate=16000):
    """Record mic to a WAV file without Qt Multimedia.

    Prefers sox `rec`, then ffmpeg. Returns argv or None.
    """
    import shutil
    import sys

    if shutil.which("rec"):
        return ["rec", "-q", "-r", str(sample_rate), "-c", "1", "-b", "16", wav_path]
    if shutil.which("ffmpeg"):
        if sys.platform == "darwin":
            return [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "avfoundation", "-i", ":0",
                "-ac", "1", "-ar", str(sample_rate), wav_path,
            ]
        if sys.platform.startswith("win"):
            return [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "dshow", "-i", "audio=default",
                "-ac", "1", "-ar", str(sample_rate), wav_path,
            ]
        return [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "alsa", "-i", "default",
            "-ac", "1", "-ar", str(sample_rate), wav_path,
        ]
    return None
