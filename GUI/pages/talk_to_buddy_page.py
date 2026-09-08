"""Talk to Buddy — a real-time voice conversation page.

Pipeline per turn: record mic -> Whisper transcribes (Replicate) ->
the same Manager/Worker pipeline replies -> the operating system's
built-in speech engine speaks the reply for free. No paid TTS.

Uses core.process_message_incognito so voice turns don't get saved as a
permanent chat transcript by default — this is a live conversation, not
a chat log.
"""
import os
import tempfile
import threading

from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy, QWidget
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess, QSize

import core
import voice_client
from .card_page import CardPage
from ..icons import get_svg_icon, ICONS
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    ON_PRIMARY_TEXT, BORDER_COLOR, SECTION_CARD_BG, HOVER_BG_COLOR,
    PRESSED_BG_COLOR, TEXT_COLOR_DARK, DANGER_COLOR, DANGER_SOFT_BG, DANGER_BORDER,
    UI_CHAT_FONT_SIZE,
)
from ..widgets.voice_animation import VoiceAnimation

# --- Recording format: 16kHz mono 16-bit PCM WAV — small, fast to upload. ---
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
    reply_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, wav_path, message_history, conversation_id=None):
        super().__init__()
        self.wav_path = wav_path
        self.message_history = message_history
        self.conversation_id = conversation_id
        self.cancel_event = threading.Event()

    def run(self):
        try:
            self.stage.emit("Listening...")
            audio_url = voice_client.upload_audio_file(self.wav_path)
            user_text = voice_client.transcribe_audio(audio_url, cancel_check=self.cancel_event.is_set)
            self.user_text_ready.emit(user_text)

            self.stage.emit("Thinking...")
            if self.conversation_id and self.message_history:
                self.message_history[0]["conversation_id"] = self.conversation_id
            result = core.process_message(
                user_text, self.message_history, cancel_check=self.cancel_event.is_set,
            )
            self.reply_ready.emit(result.get("reply", ""))
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
        self.conversation_id = None
        self._last_user_text = ""
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self.state = self.STATE_IDLE
        self._audio_source = None
        self._audio_io_device = None
        self._pcm_buffer = bytearray()
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._stop_recording)
        self._turn_worker = None
        self._tts_engine = None
        self._record_process = None
        self._record_wav_path = None
        self._say_process = QProcess(self)
        self._say_process.finished.connect(lambda *_: self._style_idle())
        self._init_tts()

        if hasattr(self, "account_chip"):
            self.account_chip.setVisible(False)
        if hasattr(self, "account_button"):
            self.account_button.setVisible(False)
        self._build_ui()

    # --- UI ---
    def _build_ui(self):
        self.transcript_container = QVBoxLayout()
        self.transcript_container.setSpacing(12)
        self.transcript_container.setContentsMargins(8, 4, 8, 8)
        self.main_layout.addLayout(self.transcript_container)
        self.main_layout.addStretch()

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_dot = QLabel("\u25cf")
        self.status_dot.setFixedWidth(16)
        status_row.addWidget(self.status_dot)
        self.status_label = QLabel("Tap the mic to start talking")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.main_layout.addLayout(status_row)

        self.voice_animation = VoiceAnimation()
        self.voice_animation.setAccessibleName("Buddy voice activity")
        animation_row = QHBoxLayout()
        animation_row.addStretch()
        animation_row.addWidget(self.voice_animation)
        animation_row.addStretch()
        self.main_layout.addLayout(animation_row)

        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.mic_button = QPushButton()
        self.mic_button.setFixedSize(72, 72)
        self.mic_button.setCursor(Qt.PointingHandCursor)
        self.mic_button.setToolTip("Tap to talk, tap again to stop")
        self.mic_button.setIcon(get_svg_icon(ICONS["mic"], ON_PRIMARY_TEXT, 28))
        self.mic_button.setIconSize(QSize(28, 28))
        self.mic_button.clicked.connect(self._on_mic_clicked)
        mic_row.addWidget(self.mic_button)
        mic_row.addStretch()
        self.main_layout.addLayout(mic_row)
        self._style_idle()

        hint = QLabel("Listening uses Gemini Flash-Lite. Speaking uses your Mac Premium/Enhanced system voice — $0. This session is saved in Library as a Voice chat.")
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
        self.voice_animation.set_mode("idle")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))

    def _style_recording(self):
        self.state = self.STATE_RECORDING
        self.status_dot.setStyleSheet(f"color: {DANGER_COLOR}; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText("Listening — tap the mic to stop")
        self.voice_animation.set_mode("recording")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(DANGER_COLOR, DANGER_COLOR))

    def _style_processing(self, label):
        self.state = self.STATE_PROCESSING
        self.status_dot.setStyleSheet("color: #f1c40f; background: transparent; border: none; font-size: 11px;")
        self.status_label.setText(label)
        self.voice_animation.set_mode("processing")
        self.mic_button.setEnabled(False)
        self.mic_button.setStyleSheet(self._mic_style(BORDER_COLOR, BORDER_COLOR))

    def _style_error(self, message):
        self.state = self.STATE_ERROR
        self.status_dot.setStyleSheet(f"color: {DANGER_COLOR}; background: transparent; border: none; font-size: 11px;")
        clean = " ".join(str(message or "").split())
        if len(clean) > 140:
            clean = clean[:137] + "…"
        self.status_label.setText(clean)
        self.voice_animation.set_mode("error")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))

    # --- transcript bubbles (lightweight — this page isn't a saved chat) ---
    def _add_transcript_line(self, text, is_user):
        bubble = QFrame()
        bg = PRIMARY_COLOR if is_user else SECTION_CARD_BG
        text_color = ON_PRIMARY_TEXT if is_user else CARD_TEXT_COLOR
        radius = "18px"
        tail = "4px" if is_user else "4px"
        if is_user:
            bubble.setStyleSheet(
                f"QFrame {{ background: {bg}; border-radius: {radius}; border-bottom-right-radius: {tail}; }}"
            )
        else:
            bubble.setStyleSheet(
                f"QFrame {{ background: {bg}; border: 1px solid {BORDER_COLOR}; border-radius: {radius}; border-bottom-left-radius: {tail}; }}"
            )
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        max_w = max(220, int(self.width() * 0.68) if self.width() > 0 else 360)
        bubble.setMaximumWidth(max_w)

        layout = QVBoxLayout(bubble)
        layout.setContentsMargins(14, 10, 14, 10)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMaximumWidth(max_w - 28)
        label.setStyleSheet(
            f"color: {text_color}; font-size: {UI_CHAT_FONT_SIZE}px; line-height: 140%; background: transparent; border: none;"
        )
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(0)
        if is_user:
            row.addStretch()
            row.addWidget(bubble, 0)
        else:
            row.addWidget(bubble, 0)
            row.addStretch()
        wrap = QWidget()
        wrap.setLayout(row)
        self.transcript_container.addWidget(wrap)

    # --- mic capture ---
    def _on_mic_clicked(self):
        if self.state == self.STATE_RECORDING:
            self._stop_recording()
        elif self.state in (self.STATE_IDLE, self.STATE_ERROR):
            self._start_recording()

    def _start_recording(self):
        self._pcm_buffer = bytearray()
        self._audio_source = None
        self._audio_io_device = None
        self._record_process = getattr(self, "_record_process", None)
        self._record_wav_path = None

        if self._start_qt_recording():
            self._style_recording()
            self._record_timer.start(MAX_RECORDING_SECONDS * 1000)
            return

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy_voice_")
        os.close(fd)
        command = voice_client.system_record_command(wav_path, sample_rate=SAMPLE_RATE)
        if not command:
            try:
                os.remove(wav_path)
            except OSError:
                pass
            self._style_error(
                "No microphone module found. In the Buddy folder run: pip install PySide6-Addons"
            )
            return

        self._record_wav_path = wav_path
        self._record_process = QProcess(self)
        self._record_process.start(command[0], command[1:])
        if not self._record_process.waitForStarted(2000):
            try:
                os.remove(wav_path)
            except OSError:
                pass
            self._record_process = None
            self._record_wav_path = None
            self._style_error("Couldn't start the microphone recorder. Check mic permissions.")
            return

        self._style_recording()
        self._record_timer.start(MAX_RECORDING_SECONDS * 1000)

    def _start_qt_recording(self):
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
        except Exception:
            return False

        device = QMediaDevices.defaultAudioInput()
        if device is None:
            return False

        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()

        self._audio_source = QAudioSource(device, fmt, self)
        self._audio_io_device = self._audio_source.start()
        if self._audio_io_device is None:
            self._audio_source = None
            return False
        self._audio_io_device.readyRead.connect(self._on_audio_ready_read)
        return True

    def _on_audio_ready_read(self):
        if self._audio_io_device is None:
            return
        chunk = self._audio_io_device.readAll()
        self._pcm_buffer.extend(bytes(chunk))

    def _stop_recording(self):
        self._record_timer.stop()

        if self._audio_source is not None:
            actual_rate = self._audio_source.format().sampleRate()
            self._audio_source.stop()
            self._audio_source = None
            self._audio_io_device = None
            if len(self._pcm_buffer) < SAMPLE_RATE:
                self._style_error("That was too short — try holding the mic a little longer.")
                return
            wav_bytes = _write_wav_header(len(self._pcm_buffer), sample_rate=actual_rate) + bytes(self._pcm_buffer)
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy_voice_")
            with os.fdopen(fd, "wb") as handle:
                handle.write(wav_bytes)
            self._run_turn(wav_path)
            return

        process = getattr(self, "_record_process", None)
        wav_path = getattr(self, "_record_wav_path", None)
        self._record_process = None
        self._record_wav_path = None
        if process is not None and process.state() != QProcess.NotRunning:
            process.write(b"q\n")
            if not process.waitForFinished(1500):
                process.terminate()
                process.waitForFinished(1000)

        if not wav_path or not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
            if wav_path:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            self._style_error("That was too short — try holding the mic a little longer.")
            return
        self._run_turn(wav_path)

    # --- pipeline ---
    def _run_turn(self, wav_path):
        self._style_processing("Listening...")
        if self.conversation_id is None:
            try:
                from storage import db
                self.conversation_id = db.create_conversation(title="Voice chat", kind="voice")
            except Exception:
                self.conversation_id = None
        self._turn_worker = _VoiceTurnWorker(wav_path, self.message_history, self.conversation_id)
        self._turn_worker.stage.connect(lambda label: self._style_processing(label))
        self._turn_worker.user_text_ready.connect(self._on_user_text)
        self._turn_worker.reply_ready.connect(self._on_reply_ready)
        self._turn_worker.failed.connect(self._on_turn_failed)
        self._turn_worker.start()

    def _init_tts(self):
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self._tts_engine = QTextToSpeech(self)
            self._tts_engine.stateChanged.connect(self._on_tts_state)
        except Exception:
            self._tts_engine = None

    def _on_tts_state(self, state):
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            if state != QTextToSpeech.Speaking:
                self._style_idle()
        except Exception:
            self._style_idle()

    def _speak(self, text):
        spoken = (text or "").strip()
        if not spoken:
            self._style_idle()
            return
        self._style_processing("Speaking...")
        command = voice_client.system_say_command(spoken)
        if command:
            self._say_process.start(command[0], command[1:])
            return
        if self._tts_engine is not None:
            self._tts_engine.say(spoken)
            return
        self._style_idle()

    def _on_user_text(self, text):
        self._last_user_text = text
        self._add_transcript_line(text, is_user=True)

    def _on_reply_ready(self, reply_text):
        self._add_transcript_line(reply_text, is_user=False)
        self._persist_turn(self._last_user_text if hasattr(self, "_last_user_text") else "", reply_text)
        self._speak(reply_text)

    def start_new_voice_chat(self):
        self.conversation_id = None
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self._clear_transcript()
        self._style_idle()

    def load_conversation(self, conversation_id):
        self.conversation_id = conversation_id
        try:
            history = core.get_conversation_history(conversation_id)
        except Exception:
            history = []
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self._clear_transcript()
        for message in history:
            role = message.get("role")
            text = (message.get("content") or "").strip()
            if not text or role not in ("user", "assistant"):
                continue
            self.message_history.append({"role": role, "content": text})
            self._add_transcript_line(text, is_user=(role == "user"))
        self._style_idle()

    def _clear_transcript(self):
        while self.transcript_container.count():
            item = self.transcript_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            layout = item.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _persist_turn(self, user_text, reply_text):
        try:
            from storage import db
            if self.conversation_id is None:
                self.conversation_id = db.create_conversation(title="Voice chat", kind="voice")
            current_title = (db.get_conversation_title(self.conversation_id) or "").strip().lower()
            if user_text and current_title in ("voice chat", "new chat", "untitled chat", ""):
                try:
                    from core.agent import generate_conversation_title
                    title = generate_conversation_title(user_text)
                except Exception:
                    title = db.auto_title_from_first_message(user_text)
                if title:
                    db.touch_conversation(self.conversation_id, title=title)
            if user_text:
                db.save_message(self.conversation_id, "user", content=user_text)
            if reply_text:
                db.save_message(self.conversation_id, "assistant", content=reply_text)
        except Exception:
            pass

    def _on_turn_failed(self, message):
        self._style_error(message)

    def hideEvent(self, event):
        """Stop any in-flight recording/playback if the user navigates
        away mid-turn, so nothing keeps running against a closed page."""
        if self._audio_source is not None:
            try:
                self._audio_source.stop()
            except Exception:
                pass
            self._audio_source = None
        if getattr(self, "_record_process", None) is not None:
            if self._record_process.state() != QProcess.NotRunning:
                self._record_process.kill()
            self._record_process = None
        if self._turn_worker is not None and self._turn_worker.isRunning():
            self._turn_worker.cancel_event.set()
        if self._tts_engine is not None:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
        if self._say_process.state() != QProcess.NotRunning:
            self._say_process.kill()
        super().hideEvent(event)
