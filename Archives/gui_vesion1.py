import sys
import random
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QLinearGradient, QPalette, QBrush, QColor, QFont

from core import process_message, new_message_history


class BuddyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Buddy")
        self.resize(600, 700)

        self.message_history = new_message_history()

        self._build_background()
        self._build_ui()

    def _build_background(self):
        # Soft white -> light blue diagonal gradient, similar to the Gemini screenshot
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#fdfeff"))
        gradient.setColorAt(0.6, QColor("#eaf3fd"))
        gradient.setColorAt(1.0, QColor("#dceafc"))
        palette = self.palette()
        palette.setBrush(QPalette.Window, QBrush(gradient))
        self.setAutoFillBackground(True)
        self.setPalette(palette)

    def resizeEvent(self, event):
        self._build_background()
        super().resizeEvent(event)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(24)
        self.greetings = [
            "Hi Shrey, what's on your mind?", 
            "Hi, How can I help you Shrey?", 
            "Lets dive in, Shrey", 
            "Where should we start, Shrey?", 
            "What's on the agenda today, Shrey?",
            "Welcome back, Shrey"
        ]
        self.greeting_choice = random.choice(self.greetings)

        # Greeting
        self.greeting = QLabel(self.greeting_choice)
        self.greeting.setAlignment(Qt.AlignCenter)
        self.greeting.setStyleSheet("""
            QLabel {
                color: #2b2b2b;
                font-size: 28px;
                font-weight: 500;
                background: transparent;
            }
        """)
        greeting_font = QFont("SF Pro Display", 22)
        self.greeting.setFont(greeting_font)

        # Chat display (hidden until first message, keeps that "clean start" feel)
        self.display = QTextEdit()
        self.display.setReadOnly(True)
        self.display.setVisible(False)
        self.display.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.55);
                border: none;
                border-radius: 18px;
                padding: 16px;
                font-size: 14px;
                color: #222;
            }
        """)

        # Rounded pill input bar, styled like the screenshot
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(0)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask Buddy")
        self.input_box.returnPressed.connect(self.handle_send)
        self.input_box.setFixedHeight(56)
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: white;
                border: none;
                border-radius: 28px;
                padding-left: 24px;
                padding-right: 90px;
                font-size: 16px;
                color: #333;
            }
        """)

        self.send_button = QPushButton("➤")
        self.send_button.setFixedSize(40, 40)
        self.send_button.clicked.connect(self.handle_send)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: #2b7ff0;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #1c6ad9;
            }
        """)

        # Overlay the send button on top of the input pill, right-aligned
        input_container = QWidget()
        input_container.setFixedHeight(56)
        overlay_layout = QHBoxLayout(input_container)
        overlay_layout.setContentsMargins(0, 0, 8, 0)
        overlay_layout.addWidget(self.input_box)
        self.input_box.setParent(input_container)
        self.send_button.setParent(input_container)

        def position_send_button():
            self.send_button.move(
                input_container.width() - self.send_button.width() - 8,
                (input_container.height() - self.send_button.height()) // 2
            )
        input_container.resizeEvent = lambda e: (self.input_box.resize(input_container.size()), position_send_button())

        layout.addStretch(1)
        layout.addWidget(self.greeting)
        layout.addWidget(self.display, stretch=1)
        layout.addWidget(input_container)
        layout.addStretch(2)

        self.setLayout(layout)

    def handle_send(self):
        user_text = self.input_box.text().strip()
        if not user_text:
            return

        if not self.display.isVisible():
            self.greeting.hide()
            self.display.setVisible(True)

        self.input_box.clear()
        self.display.append(f"<b>You:</b> {user_text}")
        self.display.append("<i>Buddy is thinking...</i>")
        QApplication.processEvents()

        reply = process_message(user_text, self.message_history)

        current = self.display.toPlainText()
        self.display.setText(current.rsplit("\nBuddy is thinking...", 1)[0])
        self.display.append(f"<b>Buddy:</b> {reply}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BuddyWindow()
    window.show()
    sys.exit(app.exec())