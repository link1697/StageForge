import os
import time
from typing import List, Dict, Optional
from dotenv import load_dotenv
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError, RateLimitError

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

        # 兼容读取 OpenAI / DeepSeek / Google Gemini API Key
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or gemini_key
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")

        # 若是 Google Key (以 AIzaSy 开头或通过 GEMINI_API_KEY 传入)，自动路由到 Google 官方 OpenAI 兼容接口
        is_google_key = bool(
            (self.api_key and self.api_key.startswith("AIzaSy"))
            or (gemini_key and self.api_key == gemini_key)
        )
        if is_google_key and not self.base_url:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        default_model = "gemini-3.8-flash" if is_google_key else "deepseek-chat"
        self.model_name = (
            model_name
            or os.getenv("OPENAI_MODEL_NAME")
            or os.getenv("LLM_MODEL")
            or default_model
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
                    max_retries=0,
                )
        else:
            self.client = None

        # 备选降级模型列表（按轻量与独立配额优先级排序）
        self.fallback_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ]
        # 如果当前模型已经在备选列表中，排除它
        self.fallback_models = [m for m in self.fallback_models if m != self.model_name]

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
    ) -> str:
        """执行大模型对话请求，包含限额自动降级（换模型 -> 自动 Mock）"""
        if self.mock_mode:
            return self._generate_mock_response(messages)

        if not self.client:
            # 无 Client 时自动降级为 Mock
            return self._generate_mock_response(messages)

        # 尝试当前主模型及降级备用模型
        models_to_try = [self.model_name] + self.fallback_models

        for candidate_model in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    messages=messages,  # type: ignore
                    temperature=temperature,
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
                return "（无内容返回）"
            except RateLimitError as e:
                # 429 限额超限：记录警告，尝试下一个备选模型
                print(f"[LLM 自动降级] 模型 {candidate_model} 触发 429 限额 ({e})，正在尝试备用模型...")
                continue
            except (APITimeoutError, APIConnectionError, APIError) as e:
                print(f"[LLM 连接波动] 模型 {candidate_model} 出现网络异常 ({e})，尝试备选方案...")
                continue
            except Exception as e:
                print(f"[LLM 未知异常] {candidate_model} 失败: {e}")
                continue

        # 如果所有在线大模型均被限额或不可用，自动降级为智能本地推理 Mock 模式，确保游戏绝不崩溃
        print("[LLM 保底降级] 所有在线 API 配额均已耗尽，已自动无缝切换为内置剧情推演引擎 (Mock Mode)！")
        return self._generate_mock_response(messages)

    def _generate_mock_response(self, messages: List[Dict[str, str]]) -> str:
        """本地智能 Mock 模式响应生成器：根据角色人设、轮次与侦探提问动态生成心理博弈台词"""
        system_prompt = ""
        for m in messages:
            if m.get("role") == "system":
                system_prompt = m.get("content", "")
                break

        # 计算当前角色已经发言的次数（即当前轮次索引，0 为第 1 轮）
        turn_count = len([m for m in messages if m.get("role") == "assistant"])

        # 获取侦探/其他角色的最近发言
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        # 角色判断（根据 system_prompt 中定义的第一人称角色，避免正文提及对方导致误判）
        is_butler = "老管家" in system_prompt and "你是年轻园丁" not in system_prompt
        is_gardener = "年轻园丁" in system_prompt or ("园丁" in system_prompt and not is_butler)

        # 1. 老管家角色剧本分支
        if is_butler:
            if "怀表" in last_user_msg:
                return (
                    "回禀侦探阁下，那块金怀表是伯爵寸步不离的传家宝！"
                    "老朽昨晚巡视时，分明看见园丁从书房出来时右手紧紧捂着口袋，神色慌张。"
                    "阁下只要搜一搜园丁的房间，真相必定水落石出！"
                )
            if turn_count == 0:
                return (
                    "回禀侦探阁下。老朽昨晚一直在前厅打理银器与门窗。"
                    "大约在夜里十一点半左右，老朽在二楼走廊拐角，亲眼看见园丁鬼鬼祟祟地避开守卫，朝伯爵书房方向溜去！"
                    "风雨这么大，他不在温室看护花木，去主楼二楼做什么？老朽当时只觉得古怪，未料竟发生此等惨案……"
                )
            elif turn_count == 1:
                return (
                    "阁下明鉴！老朽服侍伯爵整整四十年，庄园就是老朽的家，老朽怎可能加害主人？"
                    "园丁指责老朽深夜游荡，纯属狗急跳墙、血口喷人！"
                    "老朽当时是在确认书房门窗是否关紧，隐约还听到里面有翻动物品的声音！"
                    "园丁最近在外面欠下大笔高利贷，这件事庄园上下皆知，他才最需要钱！"
                )
            elif turn_count == 2:
                return (
                    "侦探阁下，老朽对伯爵忠心耿耿，伯爵生前立有遗嘱，待老朽极为宽厚，老朽毫无杀人动机！"
                    "反观园丁，既有入室盗窃的动机，又有在场的时间证明。"
                    "至于书房被反锁的细节，老朽怀疑他是从阳台窗台翻入！请阁下千万莫被他的狡辩所蒙蔽！"
                )
            else:
                return (
                    "阁下，事实已然清晰。老朽已是风烛残年，无儿无女，绝不敢行此大逆不道之事。"
                    "凶手必是贪婪且心存侥幸之徒！请侦探阁下主持公道，严惩凶手，告慰伯爵在天之灵！"
                )

        # 2. 年轻园丁角色剧本分支
        if is_gardener:
            if "怀表" in last_user_msg or "金怀表" in last_user_msg:
                return (
                    "我……我……（园丁脸色瞬间惨白，冷汗直流）"
                    "好！我招了！我昨晚确实溜进书房顺走了金怀表，因为我欠了债急着用钱！"
                    "但我发誓我没杀人！我进去的时候伯爵就已经倒在血泊里了！人根本不是我杀的，是有人栽赃我！"
                )
            if turn_count == 0:
                return (
                    "放屁！老管家你少在这里血口喷人！"
                    "侦探先生，您别听这老家伙胡扯！昨晚暴风雨把温室的顶棚吹裂了，我一直在温室抢救名贵兰花，哪有空去书房！"
                    "倒是这个老头子，平日里仗着管家身份对大家指手画脚，深夜还总在走廊里游荡，谁知道他肚子里装了什么坏水！"
                )
            elif turn_count == 1:
                return (
                    "侦探先生，您要惩罚也得讲证据！我承认我后半夜为了避雨进过主楼，但我绝对没碰伯爵！"
                    "管家平日里总被伯爵挑刺训斥，上周伯爵还当众骂他老糊涂要换掉他，他才是怀恨在心的人！"
                    "还有，管家身上总是带着主楼所有房间的钥匙，书房门反锁了，除了有钥匙的人谁能进得去？！"
                )
            elif turn_count == 2:
                return (
                    "（园丁情绪激动，双拳紧握）侦探先生！我发誓绝对没有杀害伯爵！"
                    "就算现场有我的脚印，我也只是……只是路过二楼看了看！"
                    "你们为什么咬着我不放？管家刚才说他在前厅，可前厅的挂钟明明在案发时就停了，根本没人能证明他的不在场证明！"
                )
            else:
                return (
                    "侦探先生！我贪财、我手脚不干净，我愿意认盗窃罪坐牢！"
                    "但我真的没杀人啊！伯爵身上是钝器击打致死，而我昨晚随身只带了修枝剪！"
                    "管家从一开始就在把所有脏水往我身上引，他这是想借刀杀人灭我的口！请侦探大人明察啊！"
                )

        # 3. 通用备用剧本（针对其他剧本或未知角色）
        return (
            f"关于您提到的问题「{last_user_msg}」，作为当事人，我有必要如实向您陈述事实。"
            f"昨晚事发突然，但我所说的每一句话均属实情，请侦探阁下明察！"
        )

