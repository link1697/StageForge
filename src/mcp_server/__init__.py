"""MCP Server & Client package for StageForge."""
from src.mcp_server.server import create_game_mcp_server
from src.mcp_server.client import GameMCPClient

__all__ = ["create_game_mcp_server", "GameMCPClient"]

