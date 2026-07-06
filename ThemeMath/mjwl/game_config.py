"""把 mjwl_game_config.conf 导出成 Python 常量的兼容文件。

当前通用逻辑 slots_math.py 已经可以直接读取 mjwl_game_config.conf；
保留这个文件主要是为了兼容旧脚本里 import game_config 的写法。
"""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


# 当前主题的主配置文件路径。
CONFIG_PATH = Path(__file__).with_name("mjwl_game_config.conf")


def _load_main_config(path: Path = CONFIG_PATH):
    """读取 mjwl_game_config.conf 的 [MAIN] 配置段。"""

    parser = ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.optionxform = str
    read_files = parser.read(path, encoding="utf-8-sig")
    if not read_files:
        raise FileNotFoundError(f"config file not found: {path}")
    return parser["MAIN"]


def _int_list(value: str) -> list[int]:
    """把逗号分隔的配置值转成整数列表。"""

    return [int(item.strip()) for item in value.split(",") if item.strip()]


_MAIN = _load_main_config()

# 基础牌面和物件配置。
VERSION = int(_MAIN["VERSION"])
COL_COUNT = int(_MAIN["COL_COUNT"])
ROW_COUNT = int(_MAIN["ROW_COUNT"])
ITEM_COUNT = int(_MAIN["ITEM_COUNT"])
PRIZE_RATE = int(_MAIN.get("PRIZE_RATE", "1"))

USE_WILDS = _int_list(_MAIN["USE_WILDS"])
BASE_NUMS = _int_list(_MAIN["BASE_NUMS"])
# 每个物件在 1/2/3/4/5 连时的奖励表。
ITEM_PRIZES = [
    _int_list(_MAIN.get(f"ITEM_PRIZES_{item_id}", "0,0,0,0,0"))
    for item_id in range(ITEM_COUNT)
]

# 连线/ways 和 scatter 相关配置。
LINE_MODE = int(_MAIN["LINE_MODE"])
SCATTER_MODE = int(_MAIN["SCATTER_MODE"])
SCATTER_ID = int(_MAIN["SCATTER_ID"])
SCATTER_COLS = _int_list(_MAIN["SCATTER_COLS"])
SCATTER_SERIAL = int(_MAIN["SCATTER_SERIAL"])
SCATTER_MULTIPLES = _int_list(_MAIN["SCATTER_MULTIPLES"])
SCATTER_PRIZES = _int_list(_MAIN["SCATTER_PRIZES"])

# 普通游戏和免费游戏的无效格配置。
GRID_DISABLES = _int_list(_MAIN["GRID_DISABLES"])
GRID_DISABLES_FREE = _int_list(_MAIN["GRID_DISABLES_FREE"])

# 当前配置中 0 是 scatter，1 是 wild。
WILD_ID = 1
