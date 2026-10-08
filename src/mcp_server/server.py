"""Model Context Protocol (MCP) Server for StageForge Game Engine.

Exposes game world state, crime scene archives, and clue evidence database
as standard MCP Tools and Resources for AI Agents to inspect dynamically.
Built on MCP 2.x standard MCPServer.
"""

from typing import Dict, Any, List, Optional
import json
from mcp.server.mcpserver import MCPServer
from src.config.schema import GameConfig


def create_game_mcp_server(config: GameConfig, session_ref: Optional[Any] = None) -> MCPServer:
    """Creates and configures an MCP server exposing case resources and tools."""
    mcp_app = MCPServer(f"StageForge-{config.name}")

    # =========================================================================
    # MCP Resources: 静态或半静态案情档案数据 (Resources)
    # =========================================================================

    @mcp_app.resource("case://brief")
    def get_case_brief() -> str:
        """Resource: Returns the official case dossier and incident summary."""
        return json.dumps({
            "name": config.name,
            "case_name": config.case_name or config.name,
            "case_brief": config.case_brief or config.description,
            "current_language": getattr(config, "lang", "zh"),
        }, ensure_ascii=False, indent=2)

    @mcp_app.resource("case://suspects")
    def get_suspects_profile() -> str:
        """Resource: Returns public profiles of all suspects involved."""
        profiles = [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role,
                "description": a.description,
            }
            for a in config.agents
        ]
        return json.dumps(profiles, ensure_ascii=False, indent=2)

    # =========================================================================
    # MCP Tools: 动态物证与案发环境查询工具 (Tools)
    # =========================================================================

    @mcp_app.tool()
    def inspect_clue(clue_id_or_keyword: str) -> str:
        """Inspect a specific physical evidence clue in the manor by ID or keyword.

        Args:
            clue_id_or_keyword: Evidence identifier (e.g. 'pocket_watch', 'candlestick') or keyword (e.g. '怀表', '烛台')
        """
        clues = getattr(config, "clues", []) or []
        keyword = clue_id_or_keyword.lower()
        matched = []
        for c in clues:
            cid = str(c.get("id", "")).lower()
            name = str(c.get("name", "")).lower()
            detail = str(c.get("detail", "")).lower()
            location = str(c.get("location", "")).lower()
            if keyword in cid or keyword in name or keyword in detail or keyword in location:
                matched.append(c)

        if not matched:
            return f"No physical evidence found matching keyword '{clue_id_or_keyword}'."
        return json.dumps(matched, ensure_ascii=False, indent=2)

    @mcp_app.tool()
    def query_manor_lore(topic: str) -> str:
        """Query manor history, architectural blueprint, or household rules by topic.

        Args:
            topic: Query topic keyword (e.g. '钥匙', '作案时间', '温室', '二楼书房')
        """
        world_lore = getattr(config, "world_lore", []) or []
        keyword = topic.lower()
        matched = [lore for lore in world_lore if keyword in lore.lower()]

        if not matched:
            return "No specific manor lore record found for this topic."
        return json.dumps(matched, ensure_ascii=False, indent=2)

    @mcp_app.tool()
    def check_alibi_timeline(suspect_id: str) -> str:
        """Check known statements and timeline alibis for a suspect.

        Args:
            suspect_id: Agent identifier (e.g. 'agent_butler', 'agent_gardener')
        """
        agent = config.get_agent(suspect_id)
        if not agent:
            return f"Suspect '{suspect_id}' does not exist in this case."

        return json.dumps({
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "claimed_alibi": agent.description,
        }, ensure_ascii=False, indent=2)

    return mcp_app
