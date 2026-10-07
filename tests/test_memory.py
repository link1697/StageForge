from src.config.schema import Message
from src.memory.buffer import MemoryBuffer


def test_memory_append_and_clear():
    buf = MemoryBuffer()
    assert len(buf) == 0

    msg = Message(
        sender_id="player",
        sender_name="侦探",
        content="你在哪里？",
        role="user",
        round_idx=1,
    )
    buf.append(msg)
    assert len(buf) == 1
    assert buf.messages[0].content == "你在哪里？"

    buf.clear()
    assert len(buf) == 0


def test_context_formatting_for_agent():
    buf = MemoryBuffer()
    buf.append(
        Message(
            sender_id="player",
            sender_name="侦探",
            content="管家，昨晚你在哪？",
            role="user",
            round_idx=1,
        )
    )
    buf.append(
        Message(
            sender_id="agent_butler",
            sender_name="老管家",
            content="我一直在大厅值班。",
            role="assistant",
            round_idx=1,
        )
    )
    buf.append(
        Message(
            sender_id="agent_gardener",
            sender_name="年轻园丁",
            content="胡说，我看到你进了书房！",
            role="assistant",
            round_idx=1,
        )
    )

    # 针对 agent_butler 组装上下文
    butler_context = buf.get_context_for_agent(
        agent_id="agent_butler",
        system_prompt="你是老管家...",
        window_size=10,
    )

    assert len(butler_context) == 4
    # 1. system prompt
    assert butler_context[0] == {"role": "system", "content": "你是老管家..."}
    # 2. player's message (as user role)
    assert butler_context[1] == {"role": "user", "content": "[侦探]: 管家，昨晚你在哪？"}
    # 3. butler's own message (as assistant role)
    assert butler_context[2] == {"role": "assistant", "content": "我一直在大厅值班。"}
    # 4. gardener's message (as user role with speaker prefix)
    assert butler_context[3] == {"role": "user", "content": "[年轻园丁]: 胡说，我看到你进了书房！"}


def test_sliding_window():
    buf = MemoryBuffer()
    for i in range(15):
        buf.append(
            Message(
                sender_id="player",
                sender_name="侦探",
                content=f"问题 {i}",
                role="user",
                round_idx=i,
            )
        )

    # 窗口大小为 5
    context = buf.get_context_for_agent(
        agent_id="agent_butler",
        system_prompt="系统提示",
        window_size=5,
    )

    # 1 条 system + 5 条历史 = 6 条
    assert len(context) == 6
    assert context[0]["role"] == "system"
    assert context[1]["content"] == "[侦探]: 问题 10"
    assert context[-1]["content"] == "[侦探]: 问题 14"
