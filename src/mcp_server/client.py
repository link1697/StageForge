"""MCP Client for StageForge AI Agents.

Enables agents to query tools and resources from an in-process or network-accessible
Model Context Protocol (MCP) server.
"""

from typing import Dict, Any, List, Optional
import json
import logging
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)


class GameMCPClient:
    """In-process and protocol-compliant MCP Client for AI Agents.

    Provides high-level helpers for Agents to discover tools, inspect schemas,
    and execute tool calls dynamically.
    """

    def __init__(self, mcp_server: MCPServer):
        self.server = mcp_server
        self._tools_cache: Optional[List[Dict[str, Any]]] = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return list of available MCP tools and their descriptions."""
        if self._tools_cache is not None:
            return self._tools_cache

        tools = await self.server.list_tools()
        formatted = []
        for t in tools:
            formatted.append({
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema if hasattr(t, "inputSchema") else {},
            })
        self._tools_cache = formatted
        return formatted

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call an MCP tool by name with arguments and return text result."""
        try:
            result = await self.server.call_tool(name, arguments)
            # Extract text content from MCP result
            if hasattr(result, "content") and result.content:
                parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
            if hasattr(result, "structured_content") and result.structured_content:
                return json.dumps(result.structured_content, ensure_ascii=False)
            return str(result)
        except Exception as e:
            logger.error("Error invoking MCP tool %s: %s", name, e)
            return f"Error executing tool '{name}': {e}"

    def get_tools_prompt_description(self, tools: List[Dict[str, Any]], lang: str = "zh") -> str:
        """Format tools description into prompt section for LLMs to generate tool calls."""
        if not tools:
            return ""

        if lang.startswith("en"):
            lines = [
                "【Available MCP Inspection Tools】:",
                "You have access to the following environment tools to query facts before answering:",
            ]
            for t in tools:
                lines.append(f"- `{t['name']}`: {t['description']}")
            lines.append(
                "If you need to query evidence or verify facts, you may think about them, but answer naturally in character."
            )
        else:
            lines = [
                "【可用的 MCP 探案与物证环境工具】:",
                "作为剧本中的角色，你具备查询庄园物证档案与环境情报的权限：",
            ]
            for t in tools:
                lines.append(f"- `{t['name']}`: {t['description']}")
            lines.append("你的回答应基于真实的庄园案情事实与物证，不可胡乱编造未发生的事实。")

        return "\n".join(lines)
