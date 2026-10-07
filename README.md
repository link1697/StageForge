# Agentic Game Runtime Engine (多智能体文字游戏运行时引擎)

轻量级、配置驱动的非对称多智能体文字游戏调度引擎，作为创作者剧本与底层 LLM 通信之间的中介层。

---

## ✨ 核心特性

- 📄 **配置与代码彻底解耦**：游戏规则、角色人设、轮次顺序完全由 YAML 声明，核心引擎零硬编码。
- ⚙️ **确定性状态调度**：基于确定的状态机控制发言顺序（Round-Robin）与胜负回合步进，不依赖大模型的自主判断。
- 🛡️ **严格数据契约**：基于 Pydantic V2 实现配置加载阶段的 Schema 强校验，及时捕获非法角色引用和配置错误。
- 🧠 **上下文隔离与格式化**：内置基于滑动窗口的历史对话管理器，自动针对不同 Agent 组装专用 Prompt（自身发言映射为 `assistant`，他人发言映射为带名字前缀的 `user` 消息）。
- 🔌 **兼容 OpenAI / DeepSeek / Ollama**：标准 OpenAI 协议封装，自带重试、超时与无依赖本地 Mock 测试模式。

---

## 🏗️ 架构概览

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Configuration Layer                                      │
│    configs/*.yaml  ──>  ConfigLoader (Pydantic V2)          │
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
```

---

## 📁 目录结构

```text
.
├── configs/
│   └── detective_mystery.yaml      # 示例剧本：庄园疑案
├── src/
│   ├── config/                     # 配置加载与 Pydantic 校验模型
│   │   ├── loader.py
│   │   └── schema.py
│   ├── engine/                     # 状态机与主运行时
│   │   ├── runtime.py
│   │   └── scheduler.py
│   ├── memory/                     # 记忆与上下文窗口管理
│   │   └── buffer.py
│   └── llm/                        # OpenAI 兼容客户端封装
│       └── client.py
├── tests/                          # 自动化单元测试
│   ├── test_config.py
│   ├── test_memory.py
│   └── test_scheduler.py
├── main.py                         # 终端运行入口
├── pyproject.toml                  # 项目依赖与配置
├── requirements.txt
└── README.md
```

---

## 🚀 快速开始

### 1. 准备 Python 虚拟环境与依赖

```bash
# 激活项目环境
source .venv/bin/activate

# 或安装依赖
pip install -r requirements.txt
```

### 2. 配置大模型 API（可选）

复制配置文件模板：
```bash
cp .env.example .env
```
在 `.env` 中填写你的 API Key 与 Base URL（支持 DeepSeek / OpenAI / Ollama 等）：
```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL_NAME=deepseek-chat
```

### 3. 运行游戏

#### 方案 A：快速体验（本地 Mock 模式，无需 API Key）
```bash
python main.py --mock
```

#### 方案 B：真实大模型对战
```bash
python main.py -c configs/detective_mystery.yaml
```

CLI 命令行参数说明：
- `-c, --config`: 指定剧本配置文件路径（默认为 `configs/detective_mystery.yaml`）
- `--mock`: 启用本地模拟回答模式
- `--model`: 临时覆盖指定模型名（例如 `--model gpt-4o`）
- `--window`: 记忆滑动窗口大小（默认为 `10`）

---

## 🧪 运行单元测试

```bash
pytest -v
```
覆盖配置加载解析、Schema 强校验、状态机轮次推进及上下文多角色 Prompt 转换。
