"""Talk to Buddy — a live voice conversation.

State machine:
  Idle → Listening → Thinking → Speaking → Listening
plus Paused, Interrupted, and Error.

The microphone stays open while Buddy speaks so the user can interrupt.
Voice chats are saved to Library automatically. Delete is an explicit action.
"""
import array
import math
import os
import tempfile
import threading
import time

from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy,
    QWidget, QComboBox, QMessageBox, QBoxLayout,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess, QSize

import core
import voice_client
from .card_page import CardPage
from ..icons import get_svg_icon, ICONS
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    ON_PRIMARY_TEXT, BORDER_COLOR, SECTION_CARD_BG,
    TEXT_COLOR_DARK, INPUT_BG, ACTIVE_BG_COLOR,
    DANGER_COLOR,
    UI_CHAT_FONT_SIZE,
)
from ..widgets.voice_animation import VoiceAnimation

SAMPLE_RATE = 16000
MAX_RECORDING_SECONDS = 60
SILENCE_MS = 1100
MIN_SPEECH_MS = 280
SPEECH_RMS = 900
BARGE_RMS = 1700
BARGE_HOLD_MS = 260
IGNORE_ECHO_MS = 450


def _write_wav_header(pcm_byte_count, sample_rate=SAMPLE_RATE, channels=1, bits_per_sample=16):
    import struct
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    return b"RIFF" + struct.pack("<I", 36 + pcm_byte_count) + b"WAVE" + \
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample) + \
        b"data" + struct.pack("<I", pcm_byte_count)


def _pcm_rms(pcm_bytes):
    if not pcm_bytes or len(pcm_bytes) < 4:
        return 0.0
    usable = pcm_bytes[-(len(pcm_bytes) // 2 * 2):]
    samples = array.array("h")
    try:
        samples.frombytes(usable[-6400:])
    except Exception:
        return 0.0
    if not samples:
        return 0.0
    total = 0.0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


class _VoiceTurnWorker(QThread):
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
        self.preserved_user_text = ""

    def run(self):
        try:
            self.stage.emit("Listening")
            audio_url = voice_client.upload_audio_file(self.wav_path)
            user_text = voice_client.transcribe_audio(audio_url, cancel_check=self.cancel_event.is_set)
            self.preserved_user_text = user_text
            self.user_text_ready.emit(user_text)

            self.stage.emit("Thinking")
            if self.conversation_id and self.message_history:
                self.message_history[0]["conversation_id"] = self.conversation_id
            result = core.process_message(
                user_text, self.message_history, cancel_check=self.cancel_event.is_set,
            )
            self.reply_ready.emit(result.get("reply", ""))
        except voice_client.VoiceError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit("Something went wrong: %s" % e)
        finally:
            try:
                os.remove(self.wav_path)
            except OSError:
                pass


class TalkToBuddyPage(CardPage):
    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING = "thinking"
    STATE_SPEAKING = "speaking"
    STATE_PAUSED = "paused"
    STATE_ERROR = "error"

    def __init__(self, parent=None, close_callback=None):
        super().__init__("Talk to Buddy", "A live voice conversation. Interrupt, pause, or end anytime.", parent, close_callback)
        self.conversation_id = None
        self._last_user_text = ""
        self._pending_user_text = ""
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self.state = self.STATE_IDLE
        self._paused_from = self.STATE_IDLE
        self._audio_source = None
        self._audio_io_device = None
        self._pcm_buffer = bytearray()
        self._heard_speech = False
        self._speech_started_at = 0.0
        self._last_loud_at = 0.0
        self._speaking_started_at = 0.0
        self._barge_started_at = 0.0
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._finish_utterance)
        self._vad_timer = QTimer(self)
        self._vad_timer.setInterval(80)
        self._vad_timer.timeout.connect(self._poll_vad)
        self._turn_worker = None
        self._tts_engine = None
        self._record_process = None
        self._record_wav_path = None
        self._say_process = QProcess(self)
        self._say_process.finished.connect(self._on_say_finished)
        self._init_tts()

        if hasattr(self, "account_chip"):
            self.account_chip.setVisible(False)
        if hasattr(self, "account_button"):
            self.account_button.setVisible(False)
        self._build_ui()

    def _build_ui(self):
        self._build_voice_controls()
        self.transcript_container = QVBoxLayout()
        self.transcript_container.setSpacing(12)
        self.transcript_container.setContentsMargins(8, 4, 8, 8)
        self.main_layout.addLayout(self.transcript_container)
        self.main_layout.addStretch()

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_dot = QLabel("\u25cf")
        self.status_dot.setFixedWidth(16)
        self.status_dot.setAccessibleName("Voice status")
        status_row.addWidget(self.status_dot)
        self.status_label = QLabel("Tap the mic to start talking")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.status_label, 1)
        self.main_layout.addLayout(status_row)

        self.partial_label = QLabel("")
        self.partial_label.setWordWrap(True)
        self.partial_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 11px; background: transparent; border: none;")
        self.main_layout.addWidget(self.partial_label)

        self.voice_animation = VoiceAnimation()
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
        self.mic_button.setToolTip("Start or stop listening")
        self.mic_button.setAccessibleName("Microphone")
        self.mic_button.setIcon(get_svg_icon(ICONS["mic"], ON_PRIMARY_TEXT, 28))
        self.mic_button.setIconSize(QSize(28, 28))
        self.mic_button.clicked.connect(self._on_mic_clicked)
        mic_row.addWidget(self.mic_button)
        mic_row.addStretch()
        self.main_layout.addLayout(mic_row)

        actions = QBoxLayout(QBoxLayout.LeftToRight)
        actions.setSpacing(8)
        self.actions_layout = actions
        self.pause_button = self._action_button("Pause")
        self.pause_button.setAccessibleName("Pause or resume")
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.stop_button = self._action_button("Stop speaking")
        self.stop_button.setAccessibleName("Stop speaking")
        self.stop_button.clicked.connect(self._stop_speaking)
        self.end_button = self._action_button("End chat")
        self.end_button.setAccessibleName("End voice chat")
        self.end_button.clicked.connect(self._end_chat)
        self.delete_button = self._action_button("Delete chat")
        self.delete_button.setAccessibleName("Delete this voice chat")
        self.delete_button.clicked.connect(self._delete_chat)
        for button in (self.pause_button, self.stop_button, self.end_button, self.delete_button):
            actions.addWidget(button)
        self.main_layout.addLayout(actions)
        self._style_idle()

        self.voice_hint = QLabel("")
        self.voice_hint.setWordWrap(True)
        self.voice_hint.setAlignment(Qt.AlignCenter)
        self.voice_hint.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none; margin-top: 8px;")
        self.main_layout.addWidget(self.voice_hint)
        self._refresh_voice_hint()

    def _action_button(self, text):
        button = QPushButton(text)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: {SECTION_CARD_BG}; color: {CARD_TEXT_COLOR}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 8px; padding: 6px 10px; font-size: 11px; font-weight: 600; }"
            f"QPushButton:hover {{ border: 1px solid {PRIMARY_COLOR}; }}"
            f"QPushButton:disabled {{ color: {CARD_SUBTITLE_COLOR}; }}"
        )
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "actions_layout"):
            return
        direction = (
            QBoxLayout.TopToBottom
            if self.width() < 560
            else QBoxLayout.LeftToRight
        )
        self.actions_layout.setDirection(direction)

    def _build_voice_controls(self):
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {SECTION_CARD_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 14px; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Voice engines")
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 14px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(title)
        description = QLabel("Listening is speech-to-text. Speaking is your Mac's system voice or Inworld.")
        description.setWordWrap(True)
        description.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(description)

        fields = QHBoxLayout()
        fields.setSpacing(8)
        from core.thinking import listening_model, speaking_model
        self.listening_model_combo = self._voice_combo()
        self.listening_model_combo.addItem("Gemini 2.5 Flash Lite", "gemini")
        self.listening_model_combo.addItem("Whisper · Hack Club AI", "whisper")
        self.listening_model_combo.setCurrentIndex(0 if listening_model() == "gemini" else 1)
        self.speaking_model_combo = self._voice_combo()
        self.speaking_model_combo.addItem("System voice · macOS", "system")
        self.speaking_model_combo.addItem("Inworld · Hack Club AI", "inworld")
        self.speaking_model_combo.setCurrentIndex(0 if speaking_model() == "system" else 1)
        fields.addLayout(self._voice_field("Listening", self.listening_model_combo), 1)
        fields.addLayout(self._voice_field("Speaking", self.speaking_model_combo), 1)
        layout.addLayout(fields)
        self.listening_model_combo.currentIndexChanged.connect(self._on_listen_changed)
        self.speaking_model_combo.currentIndexChanged.connect(self._on_speak_changed)
        self.main_layout.addWidget(card)

    def _on_listen_changed(self):
        from core.thinking import set_listening_model
        set_listening_model(self.listening_model_combo.currentData())
        self._refresh_voice_hint()

    def _on_speak_changed(self):
        from core.thinking import set_speaking_model
        set_speaking_model(self.speaking_model_combo.currentData())
        self._refresh_voice_hint()

    def _voice_combo(self):
        combo = QComboBox()
        combo.setCursor(Qt.PointingHandCursor)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setStyleSheet(f"""
            QComboBox {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; border: 1px solid {BORDER_COLOR};
                border-radius: 8px; padding: 6px 8px; font-size: 10px; }}
            QComboBox:hover {{ border: 1px solid {PRIMARY_COLOR}; }}
            QComboBox QAbstractItemView {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK};
                selection-background-color: {ACTIVE_BG_COLOR}; }}
        """)
        return combo

    def _voice_field(self, label_text, combo):
        field = QVBoxLayout()
        field.setSpacing(3)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; font-weight: 700; background: transparent; border: none;")
        field.addWidget(label)
        field.addWidget(combo)
        return field

    def _refresh_voice_hint(self):
        if not hasattr(self, "voice_hint"):
            return
        listener = self.listening_model_combo.currentText()
        speaker = self.speaking_model_combo.currentText()
        self.voice_hint.setText(
            "Listening: %s. Speaking: %s. This session is saved in Library as a Voice chat."
            % (listener, speaker)
        )

    def _mic_style(self, bg, hover_bg):
        return (
            "QPushButton { background: %s; border: none; border-radius: 36px; font-size: 28px; color: %s; }"
            "QPushButton:hover { background: %s; }"
        ) % (bg, ON_PRIMARY_TEXT, hover_bg)

    def _set_status(self, color, text, mode):
        self.status_dot.setStyleSheet("color: %s; background: transparent; border: none; font-size: 11px;" % color)
        self.status_label.setText(text)
        self.voice_animation.set_mode(mode)

    def _style_idle(self):
        self.state = self.STATE_IDLE
        self._set_status(CARD_SUBTITLE_COLOR, "Tap the mic to start talking", "idle")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.partial_label.setText("")

    def _style_listening(self):
        self.state = self.STATE_LISTENING
        self._set_status(DANGER_COLOR, "Listening — talk, or tap the mic to send", "listening")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(DANGER_COLOR, DANGER_COLOR))
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _style_thinking(self, label="Thinking"):
        self.state = self.STATE_THINKING
        self._set_status("#f1c40f", label, "thinking")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _style_speaking(self):
        self.state = self.STATE_SPEAKING
        self._speaking_started_at = time.monotonic()
        self._set_status(PRIMARY_COLOR, "Speaking — talk to interrupt, or tap Stop", "speaking")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)

    def _style_paused(self):
        self.state = self.STATE_PAUSED
        self._set_status("#8492a6", "Paused", "paused")
        self.mic_button.setEnabled(True)
        self.pause_button.setText("Resume")
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _style_error(self, message):
        self.state = self.STATE_ERROR
        clean = " ".join(str(message or "").split())
        if len(clean) > 140:
            clean = clean[:137] + "…"
        self._set_status(DANGER_COLOR, clean, "error")
        self.mic_button.setEnabled(True)
        self.mic_button.setStyleSheet(self._mic_style(PRIMARY_COLOR, PRIMARY_COLOR_DARK))
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        if self._pending_user_text:
            self.partial_label.setText("Kept what you said: %s" % self._pending_user_text)

    def _add_transcript_line(self, text, is_user):
        bubble = QFrame()
        bg = PRIMARY_COLOR if is_user else SECTION_CARD_BG
        text_color = ON_PRIMARY_TEXT if is_user else CARD_TEXT_COLOR
        if is_user:
            bubble.setStyleSheet("QFrame { background: %s; border-radius: 18px; border-bottom-right-radius: 4px; }" % bg)
        else:
            bubble.setStyleSheet(
                "QFrame { background: %s; border: 1px solid %s; border-radius: 18px; border-bottom-left-radius: 4px; }"
                % (bg, BORDER_COLOR)
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
            "color: %s; font-size: %spx; background: transparent; border: none;"
            % (text_color, UI_CHAT_FONT_SIZE)
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

    def _mic_allowed(self):
        try:
            from core.plugins import load_plugins
            from tools.macos_permissions import probe_microphone
            plugins = load_plugins()
            if not plugins["system"].get("microphone", True):
                self._style_error("Microphone is turned off in Plugins.")
                return False
            if not probe_microphone():
                self._style_error("macOS has not granted the microphone to this Buddy process yet.")
                return False
        except Exception:
            pass
        return True

    def _on_mic_clicked(self):
        if self.state == self.STATE_LISTENING:
            self._finish_utterance()
        elif self.state == self.STATE_SPEAKING:
            self._interrupt_speaking()
        elif self.state == self.STATE_THINKING:
            self._cancel_turn()
            self._start_listening()
        elif self.state == self.STATE_PAUSED:
            self._resume()
        elif self.state in (self.STATE_IDLE, self.STATE_ERROR):
            self._start_listening()

    def _on_pause_clicked(self):
        if self.state == self.STATE_PAUSED:
            self._resume()
            return
        if self.state in (self.STATE_LISTENING, self.STATE_THINKING, self.STATE_SPEAKING):
            self._paused_from = self.state
            # Set the state before stopping playback so QProcess/QTextToSpeech
            # callbacks cannot interpret the pause as natural speech completion.
            was_speaking = self.state == self.STATE_SPEAKING
            self._vad_timer.stop()
            self._record_timer.stop()
            self._style_paused()
            if was_speaking:
                self._halt_playback()

    def _resume(self):
        target = self._paused_from or self.STATE_LISTENING
        if target == self.STATE_SPEAKING:
            self._style_listening()
            self._ensure_mic()
            return
        if target == self.STATE_THINKING and self._turn_worker and self._turn_worker.isRunning():
            self._style_thinking()
            return
        self._start_listening()

    def _start_listening(self):
        if not self._mic_allowed():
            return
        self._pcm_buffer = bytearray()
        self._heard_speech = False
        self._speech_started_at = 0.0
        self._last_loud_at = 0.0
        self._barge_started_at = 0.0
        self.partial_label.setText("")
        if not self._ensure_mic():
            return
        self._style_listening()
        self._vad_timer.start()
        self._record_timer.start(MAX_RECORDING_SECONDS * 1000)

    def _ensure_mic(self):
        if self._audio_source is not None:
            return True
        if self._start_qt_recording():
            return True
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy_voice_")
        os.close(fd)
        command = voice_client.system_record_command(wav_path, sample_rate=SAMPLE_RATE)
        if not command:
            try:
                os.remove(wav_path)
            except OSError:
                pass
            self._style_error("No microphone module found. In the Buddy folder run: pip install PySide6-Addons")
            return False
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
            return False
        return True

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
        chunk = bytes(self._audio_io_device.readAll())
        if self.state in (self.STATE_LISTENING, self.STATE_SPEAKING):
            self._pcm_buffer.extend(chunk)
        rms = _pcm_rms(chunk)
        level = min(1.0, rms / 4000.0)
        self.voice_animation.set_level(level)

    def _poll_vad(self):
        if self.state not in (self.STATE_LISTENING, self.STATE_SPEAKING):
            return
        rms = _pcm_rms(self._pcm_buffer)
        now = time.monotonic()
        if self.state == self.STATE_SPEAKING:
            if now - self._speaking_started_at < (IGNORE_ECHO_MS / 1000.0):
                return
            if rms >= BARGE_RMS:
                if not self._barge_started_at:
                    self._barge_started_at = now
                elif (now - self._barge_started_at) * 1000 >= BARGE_HOLD_MS:
                    self._interrupt_speaking()
            else:
                self._barge_started_at = 0.0
            return
        if rms >= SPEECH_RMS:
            if not self._heard_speech:
                self._heard_speech = True
                self._speech_started_at = now
                self.partial_label.setText("Heard you — keep talking")
            self._last_loud_at = now
            return
        if self._heard_speech and (now - self._last_loud_at) * 1000 >= SILENCE_MS:
            if (now - self._speech_started_at) * 1000 >= MIN_SPEECH_MS:
                self._finish_utterance()

    def _finish_utterance(self):
        self._record_timer.stop()
        self._vad_timer.stop()
        wav_path = self._capture_wav()
        if not wav_path:
            if self.state != self.STATE_ERROR:
                self._style_error("That was too short — try speaking a little longer.")
            return
        self._run_turn(wav_path)

    def _capture_wav(self):
        if self._audio_source is not None:
            actual_rate = self._audio_source.format().sampleRate()
            pcm = bytes(self._pcm_buffer)
            self._pcm_buffer = bytearray()
            if len(pcm) < SAMPLE_RATE:
                return None
            wav_bytes = _write_wav_header(len(pcm), sample_rate=actual_rate) + pcm
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="buddy_voice_")
            with os.fdopen(fd, "wb") as handle:
                handle.write(wav_bytes)
            return wav_path

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
            return None
        return wav_path

    def _run_turn(self, wav_path):
        self._style_thinking("Thinking")
        if self.conversation_id is None:
            try:
                from storage import db
                self.conversation_id = db.create_conversation(title="Voice chat", kind="voice")
            except Exception:
                self.conversation_id = None
        self._turn_worker = _VoiceTurnWorker(wav_path, self.message_history, self.conversation_id)
        worker = self._turn_worker
        self._turn_worker.stage.connect(self._style_thinking)
        self._turn_worker.user_text_ready.connect(self._on_user_text)
        self._turn_worker.reply_ready.connect(self._on_reply_ready)
        self._turn_worker.failed.connect(self._on_turn_failed)
        worker.finished.connect(lambda: self._on_turn_finished(worker))
        self._turn_worker.start()

    def _on_turn_finished(self, worker):
        if self._turn_worker is worker:
            self._turn_worker = None
        worker.deleteLater()

    def _cancel_turn(self):
        if self._turn_worker is not None and self._turn_worker.isRunning():
            self._turn_worker.cancel_event.set()

    def shutdown(self, timeout_ms=3000):
        """Stop voice resources before the page or QApplication is destroyed."""
        self._record_timer.stop()
        self._vad_timer.stop()
        self._halt_playback()
        self._stop_mic()
        worker = self._turn_worker
        if worker is not None and worker.isRunning():
            worker.cancel_event.set()
            worker.requestInterruption()
            worker.wait(timeout_ms)
        if worker is not None and not worker.isRunning():
            self._turn_worker = None
            worker.deleteLater()

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
            if state != QTextToSpeech.Speaking and self.state == self.STATE_SPEAKING:
                self._after_speech()
        except Exception:
            if self.state == self.STATE_SPEAKING:
                self._after_speech()

    def _on_say_finished(self, *args):
        if self.state == self.STATE_SPEAKING:
            self._after_speech()

    def _after_speech(self):
        self._pcm_buffer = bytearray()
        self._start_listening()

    def _halt_playback(self):
        if self._tts_engine is not None:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
        if self._say_process.state() != QProcess.NotRunning:
            self._say_process.kill()
            self._say_process.waitForFinished(400)

    def _stop_speaking(self):
        if self.state != self.STATE_SPEAKING:
            return
        self._halt_playback()
        self._pcm_buffer = bytearray()
        self._start_listening()

    def _interrupt_speaking(self):
        if self.state != self.STATE_SPEAKING:
            return
        self._halt_playback()
        self.partial_label.setText("Interrupted — listening")
        self._style_listening()
        self._heard_speech = True
        self._speech_started_at = time.monotonic()
        self._last_loud_at = time.monotonic()
        self._vad_timer.start()
        self._record_timer.start(MAX_RECORDING_SECONDS * 1000)

    def _speak(self, text):
        spoken = (text or "").strip()
        if not spoken:
            self._start_listening()
            return
        self._style_speaking()
        self._ensure_mic()
        engine = "system"
        try:
            from core.thinking import speaking_model
            engine = speaking_model()
        except Exception:
            engine = "system"
        if engine == "inworld":
            if self._speak_inworld(spoken):
                return
        command = voice_client.system_say_command(spoken)
        if command:
            self._say_process.start(command[0], command[1:])
            return
        if self._tts_engine is not None:
            self._tts_engine.say(spoken)
            return
        self._start_listening()

    def _speak_inworld(self, spoken):
        import shutil
        try:
            url = voice_client.synthesize_speech(spoken)
        except Exception:
            return False
        if not url:
            return False
        try:
            import requests
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            suffix = ".mp3" if "mpeg" in response.headers.get("content-type", "") or url.endswith(".mp3") else ".wav"
            handle, path = tempfile.mkstemp(prefix="buddy_tts_", suffix=suffix)
            os.close(handle)
            with open(path, "wb") as out:
                out.write(response.content)
            player = shutil.which("afplay") or shutil.which("ffplay") or shutil.which("mpg123")
            if not player:
                return False
            args = [path] if player.endswith("afplay") or player.endswith("mpg123") else ["-nodisp", "-autoexit", path]
            self._say_process.start(player, args)
            return True
        except Exception:
            return False

    def _on_user_text(self, text):
        self._last_user_text = text
        self._pending_user_text = text
        self.partial_label.setText("")
        self._add_transcript_line(text, is_user=True)

    def _on_reply_ready(self, reply_text):
        self._add_transcript_line(reply_text, is_user=False)
        self._persist_turn(self._last_user_text if hasattr(self, "_last_user_text") else "", reply_text)
        self._pending_user_text = ""
        self._speak(reply_text)

    def start_new_voice_chat(self):
        self._halt_playback()
        self._cancel_turn()
        self.conversation_id = None
        self.message_history = core.new_message_history() if hasattr(core, "new_message_history") else []
        self._pending_user_text = ""
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
        if self._turn_worker is not None:
            self._pending_user_text = self._turn_worker.preserved_user_text or self._pending_user_text
        self._style_error(message)

    def _end_chat(self):
        self._halt_playback()
        self._cancel_turn()
        self._stop_mic()
        self._style_idle()
        self.status_label.setText("Voice chat ended. It is saved in Library.")

    def _delete_chat(self):
        if self.conversation_id is None:
            self.start_new_voice_chat()
            return
        choice = QMessageBox.warning(
            self,
            "Delete voice chat",
            "Delete this saved voice conversation from Library?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if choice != QMessageBox.Yes:
            return
        try:
            core.delete_conversation(self.conversation_id)
        except Exception:
            pass
        self.start_new_voice_chat()

    def _stop_mic(self):
        self._vad_timer.stop()
        self._record_timer.stop()
        if self._audio_source is not None:
            try:
                self._audio_source.stop()
            except Exception:
                pass
            self._audio_source = None
            self._audio_io_device = None
        if self._record_process is not None:
            if self._record_process.state() != QProcess.NotRunning:
                self._record_process.kill()
            self._record_process = None

    def hideEvent(self, event):
        self._halt_playback()
        self._cancel_turn()
        self._stop_mic()
        super().hideEvent(event)
