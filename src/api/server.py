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
default_config_path = Path("configs/detective_mystery.yaml")

# 挂载静态文件目录
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


class StartGameRequest(BaseModel):
    config_path: Optional[str] = "configs/detective_mystery.yaml"
    mock_mode: bool = False
    model_name: Optional[str] = None


class SpeakRequest(BaseModel):
    message: str


class AccuseRequest(BaseModel):
    agent_id: str


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="前端 index.html 尚未创建")
    return FileResponse(index_file)


@app.post("/api/game/start")
async def start_game(req: StartGameRequest):
    global current_session
    cfg_path = Path(req.config_path or default_config_path)
    if not cfg_path.exists():
        raise HTTPException(status_code=400, detail=f"配置文件不存在: {cfg_path}")

    try:
        config = load_game_config(cfg_path)
    except ConfigLoadError as e:
        raise HTTPException(status_code=400, detail=f"配置文件解析错误: {e}")

    llm = LLMClient(
        model_name=req.model_name,
        mock_mode=req.mock_mode,
    )
    current_session = GameSession(config=config, llm_client=llm)

    return {
        "status": "success",
        "message": "游戏已启动",
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


@app.post("/api/game/speak")
async def speak(req: SpeakRequest):
    global current_session
    if not current_session:
        raise HTTPException(status_code=400, detail="游戏尚未初始化，请先启动对局")

    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="发言内容不能为空")

    try:
        turns = current_session.player_speak(text)
        return {
            "status": "success",
            "turns": [t.model_dump() for t in turns],
            "state": current_session.get_state(),
        }
    except LLMClientError as e:
        raise HTTPException(status_code=500, detail=f"LLM 调用异常: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行异常: {e}")


@app.post("/api/game/accuse")
async def accuse(req: AccuseRequest):
    global current_session
    if not current_session:
        raise HTTPException(status_code=400, detail="游戏尚未初始化")

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
