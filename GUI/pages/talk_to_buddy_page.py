"""Talk to Buddy — a real-time voice conversation page.

Pipeline per turn: record mic -> upload -> Whisper transcribes -> the same
Manager/Worker pipeline used everywhere else in Buddy replies -> Chatterbox
Turbo speaks the reply -> played back automatically, then the mic
re-arms for the next turn.

Every network step (upload, transcribe, think, speak) is real, so latency
is the sum of those calls, not something this page can fake. What it does
control: recording starts instantly, each stage shows a specific status
label instead of one long silent "Thinking...", and Chatterbox Turbo was
picked specifically because Resemble built it for sub-200ms low-latency
voice agents (see voice_client.py's docstring) rather than the higher-
quality-but-slower chatterbox-pro used nowhere in this app.

Uses core.process_message_incognito so voice turns don't get saved as a
permanent chat transcript by default — this is a live conversation, not
a chat log.
"""
import os
import tempfile
import threading

from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtMultimedia import (
    QAudioSource, QAudioFormat, QMediaDevices, QMediaPlayer, QAudioOutput,
)

import core
import voice_client
from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    ON_PRIMARY_TEXT, BORDER_COLOR, SECTION_CARD_BG, HOVER_BG_COLOR,
    PRESSED_BG_COLOR, TEXT_COLOR_DARK, DANGER_COLOR, DANGER_SOFT_BG, DANGER_BORDER,
)

# --- Recording format: 16kHz mono 16-bit PCM WAV — small, fast to upload,
# and exactly what Whisper expects, so no server-side conversion needed. ---
SAMPLE_RATE = 16000
MAX_RECORDING_SECONDS = 60  # safety ceiling so a stuck mic can't record forever


def _write_wav_header(pcm_byte_count, sample_rate=SAMPLE_RATE, channels=1, bits_per_sample=16):
    """Builds a minimal WAV header for raw PCM bytes captured via
    QAudioSource, which delivers headerless PCM, not a playable file."""
    import struct
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    return b"RIFF" + struct.pack("<I", 36 + pcm_byte_count) + b"WAVE" + \
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample) + \
        b"data" + struct.pack("<I", pcm_byte_count)


class _VoiceTurnWorker(QThread):
    """Runs the upload -> transcribe -> think -> speak pipeline for one
    conversational turn, entirely off the UI thread. Emits a stage label
    at each step so the page can show real progress instead of one
    unbroken 'thinking' spinner."""
    stage = Signal(str)
    user_text_ready = Signal(str)
    reply_ready = Signal(str, str)  # (reply_text, audio_url) — audio_url may be ""
    failed = Signal(str)

    def __init__(self, wav_path, message_history, voice_name):
        super().__init__()
        self.wav_path = wav_path
        self.message_history = message_history
        self.voice_name = voice_name
        self.cancel_event = threading.Event()

    def run(self):
        try:
            self.stage.emit("Uploading...")
            audio_url = voice_client.upload_audio_file(self.wav_path)

            self.stage.emit("Listening...")
            user_text = voice_client.transcribe_audio(audio_url, cancel_check=self.cancel_event.is_set)
            self.user_text_ready.emit(user_text)

            self.stage.emit("Thinking...")
            result = core.process_message_incognito(
                user_text, self.message_history, cancel_check=self.cancel_event.is_set,
            )
            reply_text = result.get("reply", "")

            self.stage.emit("Speaking...")
            try:
                audio_reply_url = voice_client.synthesize_speech(
                    reply_text, voice=self.voice_name, cancel_check=self.cancel_event.is_set,
                )
            except voice_client.VoiceError:
                # Text reply still succeeded even if speech synthesis
                # failed — show it rather than losing the whole turn.
                audio_reply_url = ""

            self.reply_ready.emit(reply_text, audio_reply_url)
        except voice_client.VoiceError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Something went wrong: {e}")
        finally:
            try:
                os.remove(self.wav_path)
            except OSError:
                pass


class TalkToBuddyPage(CardPage):
    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_PROCESSING = "processing"
    STATE_ERROR = "error"

    def __init__(self, parent=None, close_callback=None):
        super().__init__("Talk to Buddy", "A live voice conversation — tap the mic and start talking.", parent, close_callback)
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self.voice_name = "Luna"
        self.state = self.STATE_IDLE
        self._audio_source = None
        self._audio_io_device = None
        self._pcm_buffer = bytearray()
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._stop_recording)
        self._turn_worker = None
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_playback_status_changed)

        self._build_ui()

    # --- UI ---
    def _build_ui(self):
        self.transcript_container = QVBoxLayout()
        self.transcript_container.setSpacing(10)
        self.main_layout.addLayout(self.transcript_container)
        self.main_layout.addStretch()

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_dot = QLabel("\u25cf")
        self.status_dot.setFixedWidth(16)
        status_row.addWidget(self.status_dot)
        self.status_label = QLabel("Tap the mic to start talking")
        self.status_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.main_layout.addLayout(status_row)

        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.mic_button = QPushButton("\U0001F3A4")
        self.mic_button.setFixedSize(72, 72)
        self.mic_button.setCursor(Qt.PointingHandCursor)
        self.mic_button.setToolTip("Tap to talk, tap again to stop")
        self.mic_button.clicked.connect(self._on_mic_clicked)
        mic_row.addWidget(self.mic_button)
        mic_row.addStretch()
        self.main_layout.addLayout(mic_row)
        self._style_idle()

        hint = QLabel("Voice powered by Whisper (listening) and Chatterbox Turbo (speaking), via Hack Club AI's Replicate proxy.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none; margin-top: 8px;")
        self.main_layout.addWidget(hint)

    def _mic_style(self, bg, hover_bg):
        return f"""
            QPushButton {{ background: {bg}; border: none; border-radius: 36px; font-size: 28px; color: {ON_PRIMARY_TEXT}; }}
            QPushButton:hover {{ background: {hover_bg}; }}
        """

    def _style_idle(self):
        self.state = self.STATE_IDLE
        self.status_dot.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText("Tap the mic to start talking")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))

    def _style_recording(self):
        self.state = self.STATE_RECORDING
        self.status_dot.setStyleSheet(f"color: {DANGER_COLOR}; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText("Listening — tap the mic to stop")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(DANGER_COLOR, DANGER_COLOR))

    def _style_processing(self, label):
        self.state = self.STATE_PROCESSING
        self.status_dot.setStyleSheet("color: #f1c40f; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText(label)
        self.mic_button.setEnabled(False)
        self.mic_button.setStyleSheet(self._mic_style(BORDER_COLOR, BORDER_COLOR))

    def _style_error(self, message):
        self.state = self.STATE_ERROR
        self.status_dot.setStyleSheet(f"color: {DANGER_COLOR}; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText(message)
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))

    # --- transcript bubbles (lightweight — this page isn't a saved chat) ---
    def _add_transcript_line(self, text, is_user):
        bubble = QFrame()
        bg = PRIMARY_COLOR if is_user else SECTION_CARD_BG
        text_color = ON_PRIMARY_TEXT if is_user else CARD_TEXT_COLOR
        bubble.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 12px; }}")
        layout = QVBoxLayout(bubble)
        layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {text_color}; font-size: 13px; background: transparent; border: none;")
        layout.addWidget(label)

        row = QHBoxLayout()
        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
        self.transcript_container.addLayout(row)

    # --- mic capture ---
    def _on_mic_clicked(self):
        if self.state == self.STATE_RECORDING:
            self._stop_recording()
        elif self.state in (self.STATE_IDLE, self.STATE_ERROR):
            self._start_recording()

    def _start_recording(self):
        device = QMediaDevices.defaultAudioInput()
        if device is None:
            self._style_error("No microphone found. Check your system's audio input settings.")
            return

        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)

        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()

        self._pcm_buffer = bytearray()
        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_io_device = self._audio_source.start()
        if self._audio_io_device is None:
            self._style_error("Couldn't open the microphone. Check permissions and try again.")
            return
        self._audio_io_device.readyRead.connect(self._on_audio_ready_read)

        self._style_recording()
        self._record_timer.start(MAX_RECORDING_SECONDS * 1000)

    def _on_audio_ready_read(self):
        if self._audio_io_device is None:
            return
        chunk = self._audio_io_device.readAll()
        self._pcm_buffer.extend(bytes(chunk))

    def _stop_recording(self):
        if self._audio_source is None:
            return
        self._record_timer.stop()
        self._audio_source.stop()
        actual_rate = self._audio_source.format().sampleRate()
        self._audio_source = None
        self._audio_io_device = None

        if len(self._pcm_buffer) < SAMPLE_RATE:  # under ~0.5s of audio at 16-bit mono
            self._style_error("That was too short — try holding the mic a little longer.")
            return

        wav_bytes = _write_wav_header(len(self._pcm_buffer), sample_rate=actual_rate) + bytes(self._pcm_buffer)
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy_voice_")
        with os.fdopen(fd, "wb") as f:
            f.write(wav_bytes)

        self._run_turn(wav_path)

    # --- pipeline ---
    def _run_turn(self, wav_path):
        self._style_processing("Uploading...")
        self._turn_worker = _VoiceTurnWorker(wav_path, self.message_history, self.voice_name)
        self._turn_worker.stage.connect(lambda label: self._style_processing(label))
        self._turn_worker.user_text_ready.connect(lambda text: self._add_transcript_line(text, is_user=True))
        self._turn_worker.reply_ready.connect(self._on_reply_ready)
        self._turn_worker.failed.connect(self._on_turn_failed)
        self._turn_worker.start()

    def _on_reply_ready(self, reply_text, audio_url):
        self._add_transcript_line(reply_text, is_user=False)
        if audio_url:
            self._player.setSource(QUrl(audio_url))
            self._player.play()
        else:
            self._style_idle()

    def _on_playback_status_changed(self, status):
        if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.InvalidMedia):
            self._style_idle()

    def _on_turn_failed(self, message):
        self._style_error(message)

    def hideEvent(self, event):
        """Stop any in-flight recording/playback if the user navigates
        away mid-turn, so nothing keeps running against a closed page."""
        if self._audio_source is not None:
            self._audio_source.stop()
            self._audio_source = None
        if self._turn_worker is not None and self._turn_worker.isRunning():
            self._turn_worker.cancel_event.set()
        self._player.stop()
        super().hideEvent(event)