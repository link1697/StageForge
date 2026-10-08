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
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web 互动前端服务器 (默认运行在 http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Web 服务监听主机 (默认: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web 服务监听端口 (默认: 8000)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 如果指定了 --web，启动 FastAPI Web 交互服务
    if args.web:
        import os
        import uvicorn
        os.environ["GAME_CONFIG"] = str(args.config)
        from src.api.server import app
        print(f"\n=======================================================")
        print(f" 🌐 正在启动游戏交互前端界面...")
        print(f" 📜 加载剧本配置: {args.config}")
        print(f" 🔗 请用浏览器打开: http://{args.host}:{args.port}")
        print(f"=======================================================\n")
        uvicorn.run(app, host=args.host, port=args.port)
        return

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
