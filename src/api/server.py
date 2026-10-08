import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from src.config.loader import load_game_config, ConfigLoadError
from src.llm.client import LLMClient, LLMClientError
from src.engine.session import GameSession

app = FastAPI(title="Agentic Game Engine Web UI")

# 启用 CORS 跨域支持，防止隧道/外部域名请求 API 时被拦截
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 当前全局游戏会话（支持单机对局；若无则自动在首次启动时创建）
current_session: Optional[GameSession] = None
default_config_path = Path(os.environ.get("GAME_CONFIG", "configs/detective_mystery.yaml"))

# 挂载静态文件目录
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


from src.config.translator import translate_game_config

class StartGameRequest(BaseModel):
    config_path: Optional[str] = None
    mock_mode: bool = False
    model_name: Optional[str] = None
    lang: Optional[str] = "zh"


class SpeakRequest(BaseModel):
    message: str


class AccuseRequest(BaseModel):
    agent_id: str


class SetLanguageRequest(BaseModel):
    lang: str


from src.config.strings import (
    get_text,
    MSG_GAME_STARTED,
    MSG_LANGUAGE_UPDATED,
    MSG_INDEX_NOT_FOUND,
    ERROR_CONFIG_NOT_FOUND,
    ERROR_CONFIG_PARSE,
    ERROR_GAME_NOT_INIT,
    ERROR_SPEECH_EMPTY,
    ERROR_LLM_FAILED,
    ERROR_EXECUTION_FAILED,
)

def _get_lang() -> str:
    """Helper to detect current active session language."""
    global current_session
    if current_session and hasattr(current_session.config, "lang"):
        return current_session.config.lang
    return "zh"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail=get_text(MSG_INDEX_NOT_FOUND))
    return FileResponse(index_file)


@app.post("/api/game/start")
async def start_game(req: StartGameRequest):
    global current_session
    cfg_path = Path(req.config_path) if req.config_path else default_config_path
    target_lang = (req.lang or "zh").lower()

    if not cfg_path.exists():
        err_msg = get_text(ERROR_CONFIG_NOT_FOUND, lang=target_lang, path=str(cfg_path))
        raise HTTPException(status_code=400, detail=err_msg)

    try:
        config = load_game_config(cfg_path)
    except ConfigLoadError as e:
        err_msg = get_text(ERROR_CONFIG_PARSE, lang=target_lang, error=str(e))
        raise HTTPException(status_code=400, detail=err_msg)

    llm = LLMClient(
        model_name=req.model_name,
        mock_mode=req.mock_mode,
    )

    # 每次开局根据用户选择的语言自动翻译剧本设定与角色档案
    config = translate_game_config(config, target_lang=target_lang, llm_client=llm)

    current_session = GameSession(config=config, llm_client=llm)

    return {
        "status": "success",
        "message": get_text(MSG_GAME_STARTED, lang=target_lang),
        "state": current_session.get_state(),
    }


@app.get("/api/game/state")
async def get_game_state():
    global current_session
    if not current_session:
        return {"active": False, "state": None}
    return {
        "active": True,
        "state": current_session.get_state(),
    }


@app.post("/api/game/language")
async def set_language(req: SetLanguageRequest):
    """热切换当前对局语言，保留当前对局进度、轮次与对话历史"""
    global current_session
    norm_lang = (req.lang or "zh").lower()
    if current_session:
        current_session.update_language(norm_lang)
        return {
            "status": "success",
            "message": get_text(MSG_LANGUAGE_UPDATED, lang=norm_lang),
            "state": current_session.get_state(),
        }
    return {
        "status": "success",
        "message": get_text(MSG_LANGUAGE_UPDATED, lang=norm_lang),
        "state": None,
    }



@app.post("/api/game/speak")
async def speak(req: SpeakRequest):
    global current_session
    curr_lang = _get_lang()
    if not current_session:
        raise HTTPException(status_code=400, detail=get_text(ERROR_GAME_NOT_INIT, lang=curr_lang))

    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail=get_text(ERROR_SPEECH_EMPTY, lang=curr_lang))

    try:
        turns = current_session.player_speak(text)
        return {
            "status": "success",
            "turns": [t.model_dump() for t in turns],
            "state": current_session.get_state(),
        }
    except LLMClientError as e:
        raise HTTPException(status_code=500, detail=get_text(ERROR_LLM_FAILED, lang=curr_lang, error=str(e)))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=get_text(ERROR_EXECUTION_FAILED, lang=curr_lang, error=str(e)))


@app.post("/api/game/accuse")
async def accuse(req: AccuseRequest):
    global current_session
    curr_lang = _get_lang()
    if not current_session:
        raise HTTPException(status_code=400, detail=get_text(ERROR_GAME_NOT_INIT, lang=curr_lang))

    try:
        result = current_session.accuse(req.agent_id)
        return {
            "status": "success",
            "accusation": result,
            "state": current_session.get_state(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
