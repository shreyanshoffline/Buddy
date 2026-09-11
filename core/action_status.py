"""Single action-status model for long Buddy work.

States: queued, working, waiting_for_permission, complete, cancelled, failed.
"""
from __future__ import annotations

import time


QUEUED = "queued"
WORKING = "working"
WAITING_FOR_PERMISSION = "waiting_for_permission"
COMPLETE = "complete"
CANCELLED = "cancelled"
FAILED = "failed"

VALID = {QUEUED, WORKING, WAITING_FOR_PERMISSION, COMPLETE, CANCELLED, FAILED}

LABELS = {
    QUEUED: "Queued",
    WORKING: "Working",
    WAITING_FOR_PERMISSION: "Waiting for permission",
    COMPLETE: "Complete",
    CANCELLED: "Cancelled",
    FAILED: "Failed",
}


class ActionRecord:
    def __init__(self, action_id, title, status=QUEUED, detail=""):
        self.action_id = action_id
        self.title = title
        self.status = status
        self.detail = detail
        self.created_at = time.time()
        self.updated_at = time.time()
        self.retryable = False
        self.payload = {}

    def as_dict(self):
        return {
            "action_id": self.action_id,
            "title": self.title,
            "status": self.status,
            "label": LABELS.get(self.status, self.status),
            "detail": self.detail,
            "retryable": self.retryable,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ActionStatusStore:
    def __init__(self):
        self._items = {}
        self._order = []

    def start(self, action_id, title, detail=""):
        record = ActionRecord(action_id=action_id, title=title, status=WORKING, detail=detail)
        self._items[action_id] = record
        self._order.append(action_id)
        return record

    def set_status(self, action_id, status, detail=None, retryable=None):
        if status not in VALID:
            raise ValueError("Unknown action status: %s" % status)
        record = self._items.get(action_id)
        if record is None:
            record = ActionRecord(action_id=action_id, title=action_id, status=status)
            self._items[action_id] = record
            self._order.append(action_id)
        record.status = status
        if detail is not None:
            record.detail = detail
        if retryable is not None:
            record.retryable = retryable
        record.updated_at = time.time()
        return record

    def fail(self, action_id, detail):
        return self.set_status(action_id, FAILED, detail=detail, retryable=True)

    def complete(self, action_id, detail=""):
        return self.set_status(action_id, COMPLETE, detail=detail, retryable=False)

    def cancel(self, action_id, detail="Cancelled"):
        return self.set_status(action_id, CANCELLED, detail=detail, retryable=True)

    def get(self, action_id):
        return self._items.get(action_id)

    def latest(self):
        if not self._order:
            return None
        return self._items.get(self._order[-1])


STORE = ActionStatusStore()
