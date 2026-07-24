# Skill Documentation

This document describes the skill system used in the collation state machine.

## Overview

Skills are modular components that can be combined to create complex workflows.

## Available Skills

### Gate Skills

- **Hard Stops**: Block processing based on critical conditions
- **Syllable Checks**: Validate syllable patterns
- **Gate Checks**: General gate validation framework

### Grading Skills

- **Grade Contract**: Contract-based grading system
- **Adjudication Router**: Route to appropriate adjudication logic

### Mount Skills

- **Resolution**: Resolve external dependencies

## Configuration

Skills are configured through state machine definitions. See state_machine/ for examples.

## Extending Skills

To create a new skill:

1. Create a new module in the appropriate directory
2. Implement the skill interface
3. Register with the skill manager
4. Add tests in tests/

## Best Practices

- Keep skills focused and single-purpose
- Document side effects and dependencies
- Implement comprehensive error handling
- Add unit tests for each skill
