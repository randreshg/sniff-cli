"""Allow `python -m dekk` as a fallback entry point."""

from dekk.cli.main import main


if __name__ == "__main__":
    main()
