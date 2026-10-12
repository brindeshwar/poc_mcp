"""Convenience entry point: `uv run python main.py` starts the MCP server (same as `uv run meeting-hub`)."""

from meeting_hub.server import main

if __name__ == "__main__":
    main()
