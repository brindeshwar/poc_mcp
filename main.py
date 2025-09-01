from dotenv import load_dotenv
import os

load_dotenv()

from MCP.tools.meeting_tools import app as listenloom_mcp_server

server = listenloom_mcp_server


def main():
    print("Hello from poc-mcp! (This message is from your main() function).")
    print("To start the MCP server, you MUST use the command: `mcp run main:server --port 8001`.")
    print("This main() function does not start the MCP server itself.")


# This block ensures that if you run `python main.py` directly,
# your `def main()` function is called.
if __name__ == "__main__":
    main()
    