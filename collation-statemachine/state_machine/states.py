"""State definitions."""


class State:
    """Base state class."""

    def __init__(self, name):
        self.name = name

    def enter(self, context):
        """Enter state."""
        pass

    def exit(self, context):
        """Exit state."""
        pass
