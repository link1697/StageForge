# 技术设计文档：配置驱动的多智能体文字游戏运行时引擎 (Agentic Game Runtime Engine)

## 1. 架构目标与设计原则

该项目旨在构建一个轻量级、配置驱动的非对称多智能体游戏调度引擎（Agentic Game Runtime Engine），作为创作者剧本与底层 LLM 通信之间的中介层。

* **配置与代码彻底解耦**：游戏规则、角色设定、行动顺序均由声明式 YAML 文件定义，框架核心不包含任何特定游戏的硬编码逻辑。
* **确定性状态调度**：发言权轮转、回合步进与胜负检查由确定性状态机强制控制，不依赖大模型的自主判断。
* **类型安全与输入强校验**：基于 Pydantic V2 构建严格的 Schema 验证，在配置解析阶段拦截所有不合法定义。
* **低耦合模块化设计**：存储、调度、LLM 客户端各自独立，便于后续平滑扩展向量检索（RAG）、流式推送（SSE）与推理加速（SGLang）。

---

## 2. 系统架构与项目组织

### 2.1 数据流架构

┌─────────────────────────────────────────────────────────────┐
│ 1. Configuration Layer                                      │
│    creator_game.yaml  ──>  ConfigLoader (Pydantic V2)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Validated GameConfig
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Runtime Core (GameEngine)                                │
│    ├── TurnScheduler (管理 Round 步进与发言游标)             │
│    └── MemoryManager (滑动窗口对话历史维护)                 │
└──────────────┬──────────────────────────────┬───────────────┘
               │ Turn: Player                 │ Turn: AI Agent
               ▼                              ▼
┌─────────────────────────────┐┌──────────────────────────────┐
│ 3. CLI Input Handler        ││ 4. LLM Service Layer         │
│    stdin / Terminal Input   ││    ├── Prompt Assembler      │
│                             ││    ├── OpenAI/DeepSeek API   │
│                             ││    └── Retry & Timeout       │
└──────────────┬──────────────┘└──────────────┬───────────────┘
               │ Message Event                │ Message Event
               └──────────────┬───────────────┘
                              ▼
               ┌──────────────────────────────┐
               │ 5. Memory Append & Broadcast │
               └──────────────────────────────┘

### 2.2 推荐工程目录结构

agent_engine/
├── configs/
│   └── detective_mystery.yaml      # 示例剧本：庄园疑案
├── src/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py               # YAML 读取与异常处理
│   │   └── schema.py               # Pydantic 校验模型
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── runtime.py              # 引擎主循环
│   │   └── scheduler.py            # 轮次调度器
│   ├── memory/
│   │   ├── __init__.py
│   │   └── buffer.py               # 共享历史缓冲区与滑动窗口
│   └── llm/
│       ├── __init__.py
│       └── client.py               # LLM 客户端封装 (超时、重试)
├── tests/
│   ├── test_scheduler.py           # 调度器单元测试
│   └── test_config.py              # 配置解析测试
├── main.py                         # CLI 程序入口
├── pyproject.toml                  # 依赖管理
└── README.md                       # 项目说明与架构展示

---

## 3. 数据契约与 Schema 设计 (src/config/schema.py)

系统使用 Pydantic 定义核心数据模型，确保在配置阶段完成强类型检查。

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    id: str = Field(..., description="智能体唯一标识符，需与 turn_order 中的字符串匹配")
    name: str = Field(..., description="角色展示名称")
    role: str = Field(..., description="角色在游戏中的身份标签")
    system_prompt: str = Field(..., description="角色核心人设、已知秘密与行为指引")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

class GameConfig(BaseModel):
    name: str = Field(..., description="游戏/剧本名称")
    description: str = Field(..., description="游戏背景简介")
    max_rounds: int = Field(default=5, ge=1, description="最大对局轮数")
    turn_order: List[str] = Field(
        ..., 
        description="按顺序发言的 ID 列表。保留关键字 'player' 代表终端用户"
    )
    agents: List[AgentConfig] = Field(..., description="所有参与的 AI 角色配置")

class Message(BaseModel):
    sender_id: str
    sender_name: str
    content: str
    role: Literal["system", "user", "assistant"]
    round_idx: int

---

## 4. 核心模块详细设计

### 4.1 轮次调度器 (src/engine/scheduler.py)

负责状态管理，跟踪当前是谁的回合、当前进行到第几轮，并判定游戏是否达到终止阈值。

* 状态变量：
  * current_round: int（当前大轮次，初始为 1）
  * cursor: int（当前发言者在 turn_order 列表中的索引）
* 核心方法：
  * get_current_speaker() -> str：返回当前应该行动的角色 ID（如 "player" 或 "agent_butler"）。
  * advance() -> None：游标步进；当 cursor == len(turn_order) 时重置为 0，并将 current_round 递增。
  * is_terminated() -> bool：当 current_round > max_rounds 时返回 True。

### 4.2 记忆与上下文管理器 (src/memory/buffer.py)

维护全局共享的交互记录，提供 Prompt 格式化，并通过滑动窗口防止 Token 溢出。

* 存储结构：双向队列或列表 messages: List[Message]。
* 核心能力：
  * append(msg: Message)：持久化一条发言事件。
  * get_context_for_agent(agent_id: str, window_size: int = 10) -> List[dict]：
    1. 提取当前 Agent 的 system_prompt 作为第一条系统消息。
    2. 截取最近 window_size 条公开发言记录。
    3. 将记录格式化为 OpenAI API 所要求的消息序列：自身历史发言转换为 assistant，其余角色及玩家发言转换为包含其名称标签的 user 消息（如 "[老管家]: 我昨晚睡得很早..."）。

### 4.3 LLM 客户端层 (src/llm/client.py)

基于官方 openai SDK 实现兼容层，对请求提供超时熔断与容错保护。

* 配置要求：从环境变量读取 OPENAI_API_KEY 与 OPENAI_BASE_URL（原生适配 DeepSeek、Ollama 等提供商）。
* 接口规范：
class LLMClient:
    def __init__(self, model_name: str = "deepseek-chat", timeout: float = 15.0):
        ...
        
    def generate_response(
        self, 
        messages: List[dict], 
        temperature: float = 0.7
    ) -> str:
        """执行调用，捕获网络异常与超时，支持最大重试 2 次。"""
        ...

### 4.4 引擎主循环 (src/engine/runtime.py)

连接所有子系统的主控类，负责驱动游戏演进。

* 核心执行流逻辑：
def run(self):
    self._print_prologue()
    
    while not self.scheduler.is_terminated():
        current_id = self.scheduler.get_current_speaker()
        round_num = self.scheduler.current_round
        
        if current_id == "player":
            user_text = input(f"\n[第 {round_num} 轮 - 你的发言] > ")
            self.memory.append(Message(
                sender_id="player",
                sender_name="侦探(你)",
                content=user_text,
                role="user",
                round_idx=round_num
            ))
        else:
            agent = self.get_agent_config(current_id)
            print(f"\n[{agent.name} 正在思考...]")
            context = self.memory.get_context_for_agent(agent.id)
            reply = self.llm_client.generate_response(context, agent.temperature)
            print(f"[{agent.name}]: {reply}")
            self.memory.append(Message(
                sender_id=agent.id,
                sender_name=agent.name,
                content=reply,
                role="assistant",
                round_idx=round_num
            ))
        
        self.scheduler.advance()
        
    print("\n=== 对局达到最大轮次，游戏结束 ===")

---

## 5. 示例配置文件规范 (configs/detective_mystery.yaml)

用于验证引擎调度与角色性格隔离的初始剧本：

name: "庄园疑案：审讯室"
description: "老伯爵在书房被杀，怀表丢失。你在暴风雨夜将嫌疑最大的管家与园丁集中审讯。"
max_rounds: 4

turn_order:
  - "player"
  - "agent_butler"
  - "agent_gardener"

agents:
  - id: "agent_butler"
    name: "老管家"
    role: "目击证人"
    temperature: 0.5
    system_prompt: >
      你是服务庄园40年的老管家。你目击了园丁昨晚悄悄进入书房。
      你害怕引火上身，说话极为谨慎、注重礼节，但会不露痕迹地把嫌疑引向园丁。
      绝对不要直接承认自己擅离职守。

  - id: "agent_gardener"
    name: "年轻园丁"
    role: "嫌疑人"
    temperature: 0.8
    system_prompt: >
      你是年轻园丁。你昨晚确实去书房偷了金怀表，但你绝对没有杀人。
      管家在故意陷害你。你性格急躁，说话直接，会激烈反驳管家，并指出管家经常在深夜独自游荡。
      除非证据确凿，否则不要主动承认偷盗。

---

## 6. MVP 演进计划 (Roadmap)

1. Phase 1 (MVP - 当前)
   * 实现 YAML 规范解析、内存缓冲区与 Round-robin 调度器。
   * 跑通终端 CLI 下的 3 角色固定发言闭环。
2. Phase 2 (稳定性与可观测性)
   * 引入 OpenTelemetry / 日志中间件，记录每个回合的 Token 消耗与响应耗时。
   * 支持通过 JSON 文件进行对局状态持久化（Save/Load Checkpoint）。
3. Phase 3 (AI Infra & 应用升级)
   * 流式长连接 (Streaming)：LLMClient 改造为 Generator，输出对齐 SSE 协议。
   * 外挂记忆库 (RAG)：接入轻量 Chroma 向量存储，支持跨章节剧情检索与角色长期记忆回溯。
   * 高性能推理：接入 SGLang 推理后端，利用 RadixAttention 复用公共环境前缀的 KV Cache。