#!/usr/bin/env python3
"""Agentic Game Runtime Engine CLI Entrypoint."""

import argparse
import sys
from pathlib import Path

from src.config.loader import load_game_config, ConfigLoadError
from src.llm.client import LLMClient, LLMClientError
from src.engine.runtime import GameRuntime


def parse_args():
    parser = argparse.ArgumentParser(
        description="Agentic Game Runtime Engine - 配置驱动的多智能体文字游戏运行时引擎"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="configs/detective_mystery.yaml",
        help="游戏剧本配置文件路径 (默认: configs/detective_mystery.yaml)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="开启本地 Mock 模式（无需 API Key，用于快速测试状态机与流程）",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定大模型名称（覆盖环境变量中的设置，如 deepseek-chat, gpt-4o 等）",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=10,
        help="记忆缓冲区的滑动窗口大小 (默认: 10)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. 加载配置
    config_file = Path(args.config)
    try:
        config = load_game_config(config_file)
    except ConfigLoadError as e:
        print(f"[错误] 加载配置文件失败:\n{e}", file=sys.stderr)
        sys.exit(1)

    # 2. 初始化 LLM 客户端
    llm_client = LLMClient(
        model_name=args.model,
        mock_mode=args.mock,
    )

    # 3. 初始化并运行引擎
    runtime = GameRuntime(
        config=config,
        llm_client=llm_client,
        window_size=args.window,
    )

    try:
        runtime.run()
    except LLMClientError as e:
        print(f"\n[LLM 运行时异常] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[系统异常] 发生未捕获错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
