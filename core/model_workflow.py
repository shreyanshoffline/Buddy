"""The small, backend-owned model workflow shown by the configuration canvas.

Keeping the pieces here means the diagram is not a fake drawing: the same
field names are used by the runtime router and by the draggable UI nodes.
"""
import json

from storage import db


from core.model_config import load_model_config


WORKFLOW_ZONES = (
    {
        "id": "input",
        "title": "User input & context",
        "description": "What Buddy can use before it starts work.",
        "rect": (-760, -710, 1520, 330),
        "color": "#e9f5ff",
    },
    {
        "id": "workflow",
        "title": "Main workflow",
        "description": "Buddy picks the right model and worker for the task.",
        "rect": (-760, -330, 1120, 1080),
        "color": "#f2eeff",
    },
    {
        "id": "tools",
        "title": "Tools zone",
        "description": "A worker asks a connected tool to act, then gets its result.",
        "rect": (410, -330, 350, 850),
        "color": "#fff5e3",
    },
    {
        "id": "output",
        "title": "Model output",
        "description": "The finished answer, image, or action comes back to your chat.",
        "rect": (-430, 820, 860, 245),
        "color": "#e9f9f1",
    },
)


WORKFLOW_NODES = (
    {
        "id": "input",
        "title": "Chat message",
        "description": "Your typed message or voice transcript.",
        "kind": "input",
        "model_field": None,
        "position": (-115, -610),
    },
    {
        "id": "context",
        "title": "Chat history & RAG",
        "description": "Relevant past chats and saved memory.",
        "kind": "context",
        "model_field": None,
        "position": (-480, -450),
    },
    {
        "id": "attachments",
        "title": "Files, images & audio",
        "description": "Attachments and any extracted content.",
        "kind": "input",
        "model_field": None,
        "position": (-115, -450),
    },
    {
        "id": "instructions",
        "title": "Buddy instructions",
        "description": "Your preferences, safety rules, and permissions.",
        "kind": "context",
        "model_field": None,
        "position": (250, -450),
    },
    {
        "id": "chat",
        "title": "Chat model",
        "description": "Handles a quick answer or passes deeper work onward.",
        "kind": "model",
        "model_field": "chat",
        "position": (-115, -275),
    },
    {
        "id": "manager",
        "title": "Manager",
        "description": "Plans work and chooses the right worker.",
        "kind": "manager",
        "model_field": "manager",
        "position": (-115, -60),
    },
    {
        "id": "easy",
        "title": "Easy worker",
        "description": "Short, simple work.",
        "kind": "worker",
        "model_field": "easy",
        "position": (-480, 190),
    },
    {
        "id": "medium",
        "title": "Medium worker",
        "description": "Everyday multi-step work.",
        "kind": "worker",
        "model_field": "medium",
        "position": (-115, 190),
    },
    {
        "id": "hard",
        "title": "Hard worker",
        "description": "Long or complex work.",
        "kind": "worker",
        "model_field": "hard",
        "position": (250, 190),
    },
    {
        "id": "tool_call",
        "title": "Tool call",
        "description": "A worker asks a connected app or Buddy tool to act.",
        "kind": "tool",
        "model_field": None,
        "position": (470, 65),
    },
    {
        "id": "tool_output",
        "title": "Tool output",
        "description": "The safe result returns to the worker.",
        "kind": "tool",
        "model_field": None,
        "position": (470, 310),
    },
    {
        "id": "image_create",
        "title": "Create image",
        "description": "Makes a new image from a prompt.",
        "kind": "image",
        "model_field": "image_create",
        "position": (-300, 585),
    },
    {
        "id": "image_edit",
        "title": "Edit image",
        "description": "Changes an image you attached.",
        "kind": "image",
        "model_field": "image_edit",
        "position": (70, 585),
    },
    {
        "id": "output",
        "title": "Model output",
        "description": "Reply, image, or completed action appears in your chat.",
        "kind": "output",
        "model_field": None,
        "position": (-115, 875),
    },
)


# These lines mirror the real stages in core.agent. A rejected worker task is
# the path that returns to the manager for a corrected plan; tool output goes
# back to the worker that requested it.
WORKFLOW_CONNECTIONS = (
    {"source": "input", "target": "chat", "label": "message", "kind": "main"},
    {"source": "context", "target": "chat", "label": "context", "kind": "context"},
    {"source": "attachments", "target": "chat", "label": "content", "kind": "context"},
    {"source": "instructions", "target": "chat", "label": "rules", "kind": "context"},
    {"source": "chat", "target": "manager", "label": "needs work", "kind": "main"},
    {"source": "manager", "target": "easy", "label": "easy", "kind": "main"},
    {"source": "manager", "target": "medium", "label": "medium", "kind": "main"},
    {"source": "manager", "target": "hard", "label": "hard", "kind": "main"},
    {"source": "easy", "target": "tool_call", "label": "may use tool", "kind": "tool"},
    {"source": "medium", "target": "tool_call", "label": "may use tool", "kind": "tool"},
    {"source": "hard", "target": "tool_call", "label": "may use tool", "kind": "tool"},
    {"source": "tool_call", "target": "tool_output", "label": "runs", "kind": "tool"},
    {"source": "tool_output", "target": "medium", "label": "result", "kind": "return", "bidirectional": True},
    {"source": "easy", "target": "manager", "label": "needs a new plan", "kind": "return", "bidirectional": True},
    {"source": "medium", "target": "manager", "label": "needs a new plan", "kind": "return", "bidirectional": True},
    {"source": "hard", "target": "manager", "label": "needs a new plan", "kind": "return", "bidirectional": True},
    {"source": "manager", "target": "image_create", "label": "create", "kind": "main"},
    {"source": "manager", "target": "image_edit", "label": "edit", "kind": "main"},
    {"source": "easy", "target": "output", "label": "answer", "kind": "main"},
    {"source": "medium", "target": "output", "label": "answer", "kind": "main"},
    {"source": "hard", "target": "output", "label": "answer", "kind": "main"},
    {"source": "image_create", "target": "output", "label": "image", "kind": "main"},
    {"source": "image_edit", "target": "output", "label": "image", "kind": "main"},
)

DEFAULT_WORKFLOW_LAYOUT = {
    node["id"]: list(node["position"])
    for node in WORKFLOW_NODES
}


def load_workflow_layout():
    raw = (db.get_profile() or {}).get("workflow_layout_json") or ""
    try:
        saved = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        saved = {}
    layout = {key: list(value) for key, value in DEFAULT_WORKFLOW_LAYOUT.items()}
    if isinstance(saved, dict):
        for key in layout:
            value = saved.get(key)
            if isinstance(value, (list, tuple)) and len(value) == 2:
                try:
                    layout[key] = [float(value[0]), float(value[1])]
                except (TypeError, ValueError):
                    pass
    return layout


def save_workflow_layout(layout):
    current = load_workflow_layout()
    for key in current:
        value = (layout or {}).get(key)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                current[key] = [round(float(value[0]), 1), round(float(value[1]), 1)]
            except (TypeError, ValueError):
                pass
    db.update_profile(workflow_layout_json=json.dumps(current, sort_keys=True))
    return current


def workflow_snapshot():
    """Return the nodes with the model currently used by the runtime."""
    config = load_model_config()
    layout = load_workflow_layout()
    snapshot = []
    for node in WORKFLOW_NODES:
        item = dict(node)
        field = item.get("model_field")
        item["model"] = config.get(field) if field else None
        item["position"] = tuple(layout.get(item["id"], item["position"]))
        snapshot.append(item)
    return snapshot
