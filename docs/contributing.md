# Contributing to dekk

Thank you for your interest in contributing to dekk!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/randreshg/dekk.git
cd dekk
```

2. Create a virtual environment:
```bash
python -m venv .venv
```

macOS/Linux activation:
```bash
source .venv/bin/activate
```

PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

Command Prompt:
```bat
.venv\Scripts\activate.bat
```

3. Install in development mode:
```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
dekk test

# Run with coverage
dekk test -- --cov=dekk --cov-report=html

# Run specific test file
dekk test tests/test_detect.py
```

## Code Quality

We use ruff for linting and formatting, and mypy for type checking:

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy src/dekk
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Run code quality checks
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to your fork (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## Code Style

- Follow PEP 8
- Use type hints for all functions
- Write docstrings for public APIs
- Keep functions focused and small
- Prefer dataclasses for data structures

## Questions?

Open an issue or start a discussion on GitHub!
