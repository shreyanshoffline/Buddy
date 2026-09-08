"""Dislike-reason popup shown when a user thumbs-down a response."""
from PySide6.QtWidgets import (
    QVBoxLayout, QPushButton, QFrame, QLabel,
    QHBoxLayout, QDialog, QButtonGroup, QRadioButton,
)
from PySide6.QtCore import Qt

class FeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Provide Feedback")
        self.setFixedSize(300, 200)

        layout = QVBoxLayout(self)

        label = QLabel("What was wrong with this response?")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.btn_group = QButtonGroup(self)
        reasons = ["Not helpful", "Inaccurate", "Too long", "Other"]
        for i, reason in enumerate(reasons):
            rb = QRadioButton(reason)
            self.btn_group.addButton(rb, i)
            layout.addWidget(rb)

        btn_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)