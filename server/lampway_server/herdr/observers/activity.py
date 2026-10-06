"""One session's activity state, driven by native events: idle | working | waiting, the unread answer, and the acknowledgement rule (only the focused, subscribed cockpit window can mark an
answer seen, and only with the CURRENT completion version; the Blender panel and tools never do)."""


class SessionActivity:
    def __init__(self):
        self.activity = "idle"
        self.unread = False
        self.completion_version = 0
        self.last_completed_id = None
        self.preview = ""
        self.attention = ""
        self.status = "running"

    def apply(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "turn-started":
            self.activity, self.attention = "working", ""
        elif kind == "turn-interrupted":
            self.activity = "idle"
        elif kind == "attention":
            self.activity, self.attention = "waiting", ev.get("text", "")
        elif kind == "turn-completed":
            self.activity = "idle"
            if ev.get("id") is not None and ev.get("id") == self.last_completed_id:
                return
            self.last_completed_id = ev.get("id")
            self.unread = True
            self.completion_version += 1
            self.preview = ev.get("preview", "")

    def seen(self, version: int, focused: bool, subscribed: bool) -> bool:
        if not (focused and subscribed) or version != self.completion_version:
            return False
        self.unread = False
        return True

    def peek(self) -> dict:
        return {"activity": self.activity, "unread": self.unread, "completion_version": self.completion_version, "preview": self.preview, "attention": self.attention}

    def to_dict(self) -> dict:
        return {**self.peek(), "last_completed_id": self.last_completed_id, "status": self.status}

    @classmethod
    def restore(cls, d: dict) -> "SessionActivity":
        s = cls()
        s.unread, s.completion_version, s.last_completed_id, s.preview = bool(d.get("unread")), int(d.get("completion_version", 0)), d.get("last_completed_id"), d.get("preview", "")
        s.activity, s.status = "idle", "stopped"                           # a restored session has no live process and nobody is working
        return s
