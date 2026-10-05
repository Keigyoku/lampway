"""A deterministic provider for tests and for running without any model."""


class ScriptedProvider:
    """Tests append scripted turns to ``script``; nothing here calls a network."""

    def __init__(self):
        self.script = []
