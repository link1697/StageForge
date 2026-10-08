# StageForge

> **A high-concurrency, schema-driven multi-agent deduction runtime engine with Hybrid RAG & accelerated LLM serving.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)]()

StageForge is a modular, configuration-driven multi-agent deduction and interactive social deduction engine. It bridges dynamic narrative scenarios and large language model (LLM) orchestration, providing zero-code script extensibility, hybrid dense-sparse knowledge retrieval (RAG), high-performance prefix-cached serving (SGLang), and resilient multi-tier fallback architecture.

---

## ✨ Key Features

- 📄 **100% Schema-Driven Decoupling**: Narrative world-lore, suspect personas, dynamic clue distribution, round schedules, and avatar representations are fully parameterized via YAML with **Pydantic v2** validation. Zero hardcoding in engine core.
- 🔍 **Hybrid Retrieval-Augmented Generation (Hybrid RAG)**:
  - **Dense + Sparse Dual-Path Recall**: Combines **ChromaDB** vector search for semantic relevance and **BM25Plus** (with Jieba tokenizer) for precise keyword matching on forensic items, timestamps, and locations.
  - **Reciprocal Rank Fusion (RRF)**: Merges and reranks retrieved context to eliminate hallucinations in investigative deductions.
- ⚡ **High-Throughput Serving & Structured Decoding**:
  - **SGLang & RadixAttention**: Leverages prefix caching for long, shared world-lore prompts across suspects, reducing prompt prefill latency (TTFT) by over 60%.
  - **Constrained Decoding**: Supports JSON Schema and regex-guided generation for deterministic agent outputs and state transitions.
- 🛡️ **Fault-Tolerant Multi-Tier Fallback & Circuit Breaking**:
  - Seamlessly handles `HTTP 429` (Quota Exhaustion) and upstream timeouts via an automated fallback chain: **Local SGLang Cluster ➔ Primary Commercial LLM ➔ Backup Model Pool ➔ Offline Deterministic Simulation Engine**.
- ⚙️ **Deterministic Asymmetric State Machine (FSM)**:
  - Manages round-robin conversational turns, interrogation limits, accusation trials, and victory/defeat evaluations.
- 🧠 **Context Isolation & Perspective Transformation**:
  - Sliding-window dialog buffer that translates dialogue streams dynamically per agent perspective (`assistant` for self, named `user` for others).
- 🌐 **Modern Interactive Web UI & CLI**:
  - Full-featured dark-mode Web interface with real-time SSE streaming, character state inspectors, dynamic suspect tabs, and responsive layout.

---

## 🏗️ Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Configuration & Narrative Layer (Schema-Driven)                    │
│    configs/*.yaml ──> ConfigLoader (Pydantic v2 Validation)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Validated GameConfig
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. Runtime Core & State Orchestration (StageForge Engine)             │
│    ├── TurnScheduler (FSM, Turn advancement, Accusation Verdict)      │
│    ├── MemoryManager (Sliding window context & persona isolation)      │
│    └── HybridRAGEngine (BM25Plus + ChromaDB + Reciprocal Rank Fusion)  │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ Turn: Player (Detective)         │ Turn: Multi-Agent Suspect
                   ▼                                 ▼
┌───────────────────────────────────┐ ┌──────────────────────────────────┐
│ 3. Interactivity Layer            │ │ 4. Resilient LLM Serving Layer   │
│    ├── Web UI (FastAPI + SSE)     │ │    ├── SGLang (RadixAttention)   │
│    └── CLI Terminal Input         │ │    ├── Primary Cloud LLM API     │
│                                   │ │    ├── Fallback Pool (Gemini)    │
│                                   │ │    └── Mock Simulation Fallback  │
└──────────────────┬────────────────┘ └──────────────────┬───────────────┘
                   │ Event Broadcast                     │ Model Response
                   └────────────────┬────────────────────┘
                                    ▼
                   ┌─────────────────────────────────┐
                   │ 5. Memory Append & Event Stream │
                   └─────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
.
├── configs/                            # Scenario definitions (2, 6, 12 suspects)
│   ├── detective_mystery.yaml          # Manor Mystery (2 suspects: Butler & Gardener)
│   ├── snow_mansion_6suspects.yaml     # Snowbound Mansion (6 suspects)
│   └── orient_express_12suspects.yaml  # Express Murder (12 suspects)
├── src/
│   ├── config/                         # Schema validation & YAML loader
│   │   ├── loader.py
│   │   └── schema.py
│   ├── engine/                         # FSM runtime & turn scheduler
│   │   ├── runtime.py
│   │   ├── scheduler.py
│   │   └── session.py
│   ├── memory/                         # Dialog buffer & Hybrid RAG engine
│   │   ├── buffer.py
│   │   └── rag.py                      # ChromaDB + BM25Plus + RRF implementation
│   ├── llm/                            # LLM clients & multi-tier circuit breakers
│   │   ├── client.py                   # Multi-tier fallback pipeline
│   │   └── sglang_client.py            # SGLang RadixAttention client
│   └── web/                            # FastAPI backend application
│       └── app.py
├── static/                             # Web UI frontend (Vanilla JS & Modern CSS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/                              # Pytest test suite (23 tests passing)
│   ├── test_config.py
│   ├── test_memory.py
│   ├── test_rag_sglang.py
│   ├── test_runtime.py
│   ├── test_scheduler.py
│   └── test_session.py
├── main.py                             # Unified CLI & Web entry point
├── pyproject.toml                      # Project metadata & build specs
├── requirements.txt                    # Python dependencies
└── README.md
```

---

## 🚀 Quick Start

### 1. Prerequisites & Environment Setup

```bash
# Clone the repository
git clone https://github.com/link1697/StageForge.git
cd StageForge

# Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Model API Keys (Optional)

Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` with your API configuration (supports OpenAI, DeepSeek, Google Gemini, Ollama, etc.):
```env
# Primary LLM Configuration
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini

# Google Gemini (Optional Fallback / Primary)
GEMINI_API_KEY=your_gemini_key_here

# SGLang Local Server (Optional for extreme inference acceleration)
SGLANG_API_URL=http://localhost:30000
```

> **Note**: If no API keys are provided or quota runs out (`HTTP 429`), the built-in resilient fallback system will automatically kick in without crashing the game!

---

### 3. Launching StageForge

#### Option A: Web Interface (Recommended)
```bash
# Launch interactive Web UI on http://localhost:8000
python main.py --web

# Or specify a custom scenario
python main.py --web --config configs/snow_mansion_6suspects.yaml
```

#### Option B: Terminal CLI (Interactive Detective Mode)
```bash
# Run Manor Mystery scenario (2 suspects)
python main.py -c configs/detective_mystery.yaml

# Run Snowbound Mansion scenario (6 suspects)
python main.py -c configs/snow_mansion_6suspects.yaml

# Run offline with deterministic Mock engine (no API keys required)
python main.py --mock
```

#### CLI Parameters:
| Flag | Description | Default |
| :--- | :--- | :--- |
| `-c, --config` | Path to narrative scenario YAML | `configs/detective_mystery.yaml` |
| `--web` | Start FastAPI web server instead of CLI | `False` |
| `--host` | Web server bind address | `127.0.0.1` |
| `--port` | Web server port | `8000` |
| `--mock` | Force offline deterministic mock engine | `False` |
| `--model` | Temporarily override default LLM model name | Config default |
| `--window` | Sliding memory window size | `10` |

---

## 🧪 Testing

StageForge includes a comprehensive automated test suite with full coverage on schema validation, memory windows, turn schedulers, Hybrid RAG indexing, and SGLang fallback logic.

```bash
.venv/bin/pytest -v
```

Output:
```text
tests/test_config.py .......     [ 30%]
tests/test_memory.py ...         [ 43%]
tests/test_rag_sglang.py .....   [ 65%]
tests/test_runtime.py ...        [ 78%]
tests/test_scheduler.py ..       [ 86%]
tests/test_session.py ...        [100%]

======================== 23 passed in 5.72s ========================
```

---

## 📄 License

This project is open-sourced under the [MIT License](LICENSE).
