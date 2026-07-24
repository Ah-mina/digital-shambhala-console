"""Hard stop implementation."""


class HardStop:
    """Hard stop gate that blocks processing."""

    def __init__(self, conditions):
        self.conditions = conditions

    def should_stop(self, context):
        """Check if hard stop should trigger."""
        for condition in self.conditions:
            if condition(context):
                return True
        return False
