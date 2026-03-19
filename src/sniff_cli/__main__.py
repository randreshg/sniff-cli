"""Allow `python -m sniff_cli` as a fallback entry point."""

from sniff_cli.cli.main import main


if __name__ == "__main__":
    main()
