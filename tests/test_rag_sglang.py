import pytest
from src.config.schema import GameConfig, AgentConfig
from src.memory.rag import HybridRAGEngine, BM25Retriever, SimpleTokenizer
from src.engine.session import GameSession
from src.llm.client import LLMClient
from src.llm.sglang_client import SGLangClient


def test_tokenizer():
    tokenizer = SimpleTokenizer()
    tokens = tokenizer.tokenize("伯爵在暴风雨之夜被杀，怀表丢失。")
    assert len(tokens) > 0
    assert any("怀表" in t or "伯爵" in t for t in tokens)


def test_bm25_retriever():
    retriever = BM25Retriever()
    docs = [
        {"id": "doc_1", "content": "老伯爵的书房钥匙被藏在黑布袋中。"},
        {"id": "doc_2", "content": "温室的玻璃在暴风雨中被吹碎。"},
    ]
    retriever.index(docs)
    results = retriever.search("钥匙在哪里？", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "doc_1"


def test_hybrid_rag_engine():
    rag = HybridRAGEngine(collection_name="test_lore_suite")
    docs = [
        {"id": "watch_clue", "content": "金怀表的时间停在昨夜11点45分，表面沾有泥泞。"},
        {"id": "candlestick_clue", "content": "黄铜烛台重达2.4公斤，底座残留有血迹。"},
    ]
    rag.add_documents(docs)
    results = rag.retrieve("怀表几点停的？", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "watch_clue"
    assert "金怀表" in results[0]["content"]


def test_sglang_client_initialization():
    client = SGLangClient(base_url="http://127.0.0.1:30000/v1")
    assert client.base_url == "http://127.0.0.1:30000/v1"
    assert isinstance(client.is_available, bool)


def test_game_session_with_rag():
    cfg = GameConfig(
        name="测试剧本",
        description="测试描述",
        max_rounds=5,
        turn_order=["player", "agent_butler"],
        agents=[
            AgentConfig(
                id="agent_butler",
                name="管家",
                role="管家",
                system_prompt="你是管家",
            )
        ],
        world_lore=["黑石庄园建于19世纪初，主楼书房位于二楼尽头。"],
        clues=[{"id": "clock", "name": "挂钟", "detail": "停在11点45分", "location": "前厅"}],
    )
    llm = LLMClient(mock_mode=True)
    session = GameSession(config=cfg, llm_client=llm)

    # 验证 RAG 初始只索引常识，未搜查物证处于锁定状态（严防信息泄漏）
    assert session.rag is not None
    assert len(session.rag.memory_store) == 1
    assert session.clues_state["clock"]["status"] == "locked"

    # 执行搜查后，线索确凿并动态注入 RAG
    session.search_clue("clock")
    assert session.clues_state["clock"]["status"] == "discovered"
    assert len(session.rag.memory_store) == 2

    # 执行问话
    turns = session.player_speak("关于前厅的挂钟，你知道些什么？")
    assert len(turns) == 2
    assert turns[0].is_player is True
    assert turns[1].speaker_id == "agent_butler"

