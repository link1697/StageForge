import os
import time
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

# 尝试自动加载当前目录或父目录的 .env 文件
load_dotenv()


class LLMClientError(Exception):
    """LLM 调用相关异常"""
    pass


class LLMClient:
    """基于 OpenAI 兼容协议的 LLM 客户端封装（支持 DeepSeek / Ollama / OpenAI）"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        mock_mode: bool = False,
    ):
        self.mock_mode = mock_mode
        self.timeout = timeout
        self.max_retries = max_retries

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model_name = (
            model_name
            or os.getenv("OPENAI_MODEL_NAME")
            or os.getenv("LLM_MODEL")
            or "deepseek-chat"
        )

        if not self.mock_mode:
            # 如果没有配置 API Key，且未显式指定 mock 模式，允许通过环境变量设定模拟模式
            if not self.api_key:
                if os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes"):
                    self.mock_mode = True
                else:
                    self.client = None
            else:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
        else:
            self.client = None

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
    ) -> str:
        """执行大模型对话请求，包含异常重试与超时保护"""
        if self.mock_mode:
            return self._generate_mock_response(messages)

        if not self.client:
            raise LLMClientError(
                "未检测到 OPENAI_API_KEY 环境变量！\n"
                "请在 .env 文件或环境中配置 OPENAI_API_KEY（以及可选的 OPENAI_BASE_URL），\n"
                "或启动时开启模拟模式 (--mock) 进行体验。"
            )

        last_exception = None
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,  # type: ignore
                    temperature=temperature,
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
                return "（无内容返回）"
            except (APITimeoutError, APIConnectionError, APIError) as e:
                last_exception = e
                if attempt <= self.max_retries:
                    time.sleep(1.0 * attempt)
                else:
                    break
            except Exception as e:
                raise LLMClientError(f"LLM 调用发生未知错误: {e}") from e

        raise LLMClientError(
            f"LLM 请求在重试 {self.max_retries} 次后失败: {last_exception}"
        )

    def _generate_mock_response(self, messages: List[Dict[str, str]]) -> str:
        """本地 Mock 模式响应生成器（方便无需 API Key 时进行流程测试）"""
        # 获取最后一条发言内容
        last_user_msg = "..."
        for m in reversed(messages):
            if m["role"] == "user":
                last_user_msg = m["content"]
                break

        return f"【模拟回复】我对「{last_user_msg}」深感疑虑，请侦探阁下明察秋毫！"
