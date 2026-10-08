import pytest
import asyncio
from pathlib import Path
from src.config.loader import load_game_config
from src.mcp_server.server import create_game_mcp_server
from src.mcp_server.client import GameMCPClient
from src.engine.session import GameSession


@pytest.mark.anyio
async def test_mcp_server_and_tools():
    """验证 MCP Server 正确加载并暴露标准 Tools 与 Resources"""
    cfg_path = Path("configs/detective_mystery.yaml")
    config = load_game_config(cfg_path)
    server = create_game_mcp_server(config)

    # 1. 工具列表校验
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "inspect_clue" in tool_names
    assert "query_manor_lore" in tool_names
    assert "check_alibi_timeline" in tool_names

    # 2. 调用 inspect_clue 工具测试物证检索
    res_clue = await server.call_tool("inspect_clue", {"clue_id_or_keyword": "怀表"})
    assert "pocket_watch" in str(res_clue)

    # 3. 调用 check_alibi_timeline 测试角色时间线
    res_alibi = await server.call_tool("check_alibi_timeline", {"suspect_id": "agent_butler"})
    assert "理查德" in str(res_alibi) or "Richard" in str(res_alibi)


@pytest.mark.anyio
async def test_mcp_client_integration():
    """验证 GameMCPClient 高级封装与 Prompt 生成"""
    cfg_path = Path("configs/detective_mystery.yaml")
    config = load_game_config(cfg_path)
    server = create_game_mcp_server(config)
    client = GameMCPClient(server)

    tools = await client.list_tools()
    assert len(tools) == 3

    # 测试客户端直接调用工具
    clue_text = await client.call_tool("inspect_clue", {"clue_id_or_keyword": "candlestick"})
    assert "candlestick" in clue_text or "烛台" in clue_text

    # 测试中英文 Prompt 格式化
    prompt_zh = client.get_tools_prompt_description(tools, lang="zh")
    assert "inspect_clue" in prompt_zh
    assert "MCP" in prompt_zh

    prompt_en = client.get_tools_prompt_description(tools, lang="en")
    assert "inspect_clue" in prompt_en
    assert "MCP" in prompt_en


def test_session_mcp_initialization():
    """验证 GameSession 内部自动启动并注入 MCP 协议环境"""
    cfg_path = Path("configs/detective_mystery.yaml")
    config = load_game_config(cfg_path)
    session = GameSession(config=config)

    assert hasattr(session, "mcp_server")
    assert hasattr(session, "mcp_client")
    assert session.mcp_server.name.startswith("StageForge-")
