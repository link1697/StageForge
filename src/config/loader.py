from pathlib import Path
from typing import Union
import yaml
from pydantic import ValidationError

from src.config.schema import GameConfig


class ConfigLoadError(Exception):
    """配置加载异常"""
    pass


def load_game_config(config_path: Union[str, Path]) -> GameConfig:
    """从 YAML 文件读取并验证游戏配置"""
    path = Path(config_path)
    if not path.exists():
        raise ConfigLoadError(f"配置文件不存在: {path.resolve()}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"YAML 语法解析失败: {e}") from e
    except Exception as e:
        raise ConfigLoadError(f"读取配置文件失败: {e}") from e

    if not isinstance(raw_data, dict):
        raise ConfigLoadError("配置文件内容必须是一个 YAML 映射对象 (Mapping)")

    try:
        return GameConfig.model_validate(raw_data)
    except ValidationError as e:
        raise ConfigLoadError(f"配置验证失败:\n{e}") from e
