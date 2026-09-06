"""Speech-to-text and text-to-speech via Hack Club AI's Replicate proxy.

Hack AI's own chat/embeddings endpoints have no audio input or output at
all — confirmed against their live model catalog (every model's
output_modalities is text-only or text+image, never audio) and their
docs (no /audio endpoints exist, chat.send() doesn't even list
`modalities` as a parameter). Voice is only reachable through Replicate,
proxied at https://ai.hackclub.com/proxy/v1/replicate using the same
Hack Club AI key as everything else — per Hack AI's own Replicate guide,
you point the official Replicate client/API at that base URL.

Endpoints below match Replicate's real, documented HTTP API
(https://replicate.com/docs/reference/http), just with the Hack AI
base URL and key substituted in:
  - POST /models/{owner}/{name}/predictions   (official models)
  - GET  /predictions/{id}                     (poll status)
  - POST /files                                (upload local audio)

STT: vaibhavs10/incredibly-fast-whisper — whisper-large-v3 optimized for
speed, audio in, transcript out. Verified against Replicate's real input
schema (audio, task, language, batch_size, return_timestamps) and output
shape ({"text": "..."}).

TTS: inworld/realtime-tts-1.5-mini — ~120ms latency per Inworld's own
benchmarks, the fastest option in Replicate's text-to-speech collection,
picked specifically because "close to how humans talk" depends on the
speak step not being the bottleneck. Verified against Replicate's real
input schema (text, voice_id, temperature, audio_format, sample_rate).
"Ashley" is the model's own documented default voice.
"""
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

REPLICATE_BASE_URL = "https://ai.hackclub.com/proxy/v1/replicate"
STT_MODEL = ("vaibhavs10", "incredibly-fast-whisper")
TTS_MODEL = ("inworld", "realtime-tts-1.5-mini")
DEFAULT_TTS_VOICE = "Ashley"

SYNC_WAIT_SECONDS = 25  # `Prefer: wait` — most requests finish inside this
POLL_INTERVAL_SECONDS = 0.6
POLL_TIMEOUT_SECONDS = 30  # fallback if a request doesn't finish within SYNC_WAIT_SECONDS
REQUEST_TIMEOUT_SECONDS = SYNC_WAIT_SECONDS + 10


class VoiceError(Exception):
    """Raised for any STT/TTS failure. Callers show str(e) directly, so
    messages here are already user-facing — never a raw stack trace."""
    pass


def _api_key():
    """Same key used everywhere else in Buddy — Hack Club AI's proxy
    accepts one token for chat, embeddings, and Replicate alike."""
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


def _run_prediction(owner, name, input_payload, cancel_check=None):
    """Creates a prediction with Prefer: wait for a fast synchronous
    result; falls back to polling /predictions/{id} if it isn't done
    yet. Raises VoiceError with a specific, honest reason on any
    failure — mirrors core/agent.py's run_image_creation_task, which
    exists precisely because an earlier silent-empty-result bug there
    made Buddy fail with no diagnostic information at all."""
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "Prefer": f"wait={SYNC_WAIT_SECONDS}",
    }
    try:
        resp = requests.post(
            f"{REPLICATE_BASE_URL}/models/{owner}/{name}/predictions",
            headers=headers,
            json={"input": input_payload},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise VoiceError(f"Couldn't reach the voice service: {e}")

    if resp.status_code >= 400:
        raise VoiceError(f"Voice service rejected the request ({resp.status_code}): {resp.text[:200]}")

    prediction = resp.json()
    status = prediction.get("status")

    if status == "succeeded":
        return prediction.get("output")
    if status == "failed":
        raise VoiceError(f"Voice generation failed: {prediction.get('error') or 'unknown error'}")

    # Didn't finish inside the sync window — poll like any async prediction.
    get_url = prediction.get("urls", {}).get("get")
    if not get_url:
        raise VoiceError("Voice service didn't return a prediction to track.")

    elapsed = 0.0
    while elapsed < POLL_TIMEOUT_SECONDS:
        if cancel_check and cancel_check():
            raise VoiceError("Cancelled.")
        try:
            poll_resp = requests.get(get_url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            poll_resp.raise_for_status()
            result = poll_resp.json()
        except requests.RequestException as e:
            raise VoiceError(f"Lost connection while waiting on the voice service: {e}")

        status = result.get("status")
        if status == "succeeded":
            return result.get("output")
        if status == "failed":
            raise VoiceError(f"Voice generation failed: {result.get('error') or 'unknown error'}")
        if status == "canceled":
            raise VoiceError("Cancelled.")

        time.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

    raise VoiceError("Voice service is taking too long to respond. Try again in a moment.")


def upload_audio_file(file_path):
    """Uploads a local recording so it can be passed as an `audio` URL to
    transcribe_audio() — incredibly-fast-whisper's input schema takes a
    URI, not raw bytes. Matches Replicate's real POST /files multipart
    contract."""
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{REPLICATE_BASE_URL}/files",
                headers={"Authorization": f"Bearer {_api_key()}"},
                files={"content": (filename, f, "audio/wav")},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        resp.raise_for_status()
        url = resp.json().get("urls", {}).get("get")
        if not url:
            raise VoiceError("Upload succeeded but no file URL was returned.")
        return url
    except requests.RequestException as e:
        raise VoiceError(f"Couldn't upload the recording: {e}")


def transcribe_audio(audio_url, cancel_check=None):
    """Speech-to-text via incredibly-fast-whisper. audio_url must already
    be reachable by Replicate — use upload_audio_file() first for local
    recordings. Returns the transcript text; raises VoiceError (never
    returns silently empty) if nothing was transcribed, since a dropped
    transcript would make Buddy respond to nothing with no indication
    why."""
    owner, name = STT_MODEL
    output = _run_prediction(
        owner, name,
        {"audio": audio_url, "task": "transcribe", "batch_size": 24, "return_timestamps": False},
        cancel_check=cancel_check,
    )
    # Real output shape is {"text": "..."} (optionally with "chunks" if
    # return_timestamps was requested) — not a bare string or "transcription".
    text = output.get("text", "") if isinstance(output, dict) else str(output or "")
    text = text.strip()
    if not text:
        raise VoiceError("Didn't catch that — no speech was detected in the recording.")
    return text


def synthesize_speech(text, voice=DEFAULT_TTS_VOICE, cancel_check=None):
    """Text-to-speech via Inworld Realtime TTS 1.5 Mini (~120ms latency,
    the fastest model in Replicate's TTS collection — picked so the
    speak step doesn't become the bottleneck in a live conversation).
    Returns a playable audio URL. Raises VoiceError with a specific
    reason if generation fails or returns nothing."""
    if not text or not text.strip():
        raise VoiceError("Nothing to say — the reply was empty.")

    owner, name = TTS_MODEL
    output = _run_prediction(
        owner, name,
        {"text": text.strip(), "voice_id": voice, "audio_format": "mp3"},
        cancel_check=cancel_check,
    )
    url = output if isinstance(output, str) else None
    if not url:
        raise VoiceError("The voice model responded but didn't return any audio.")
    return url