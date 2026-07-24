"""State transition logic."""


class Transition:
    """State transition."""

    def __init__(self, from_state, to_state, condition=None):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition

    def can_transition(self, context):
        """Check if transition is allowed."""
        if self.condition is None:
            return True
        return self.condition(context)
