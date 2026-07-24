"""State machine runner."""


class StateMachineRunner:
    """Execute state machine."""

    def __init__(self, state_machine):
        self.state_machine = state_machine
        self.current_state = None

    def run(self, context):
        """Run the state machine."""
        pass
