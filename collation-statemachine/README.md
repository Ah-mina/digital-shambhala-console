# Collation State Machine

A sophisticated state machine implementation for managing complex workflows with support for gates, grading, and state transitions.

## Overview

This module provides:

- **State Management**: Define and manage states with complex transition logic
- **Gates**: Implement hard stops and other validation gates
- **Grading**: Contract-based grading and adjudication
- **Mounts**: Resolution and mounting of external systems

## Quick Start

```bash
python run_agent.py
```

## Directory Structure

- `gates/` - Gate implementations (hard stops, syllable checks, etc.)
- `grading/` - Grading logic and contracts
- `mounts/` - External system integrations
- `state_machine/` - Core state machine implementation
- `tests/` - Test suite
- `data/` - Data files (precedents, etc.)

## Documentation

- See `SKILL.md` for skill documentation
- See `操作手册_白话版.md` for user manual (Chinese)
- See `映射审计表.md` for mapping audit table (Chinese)
- See `CLI_README.md` for CLI usage

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

## License

See repository root for license information.
