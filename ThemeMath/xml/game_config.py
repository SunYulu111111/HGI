"""将 special/xml_game_config.conf 导出为 Python 常量。"""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent / "special" / "xml_game_config.conf"


def _load_main_config(path: Path = CONFIG_PATH):
    parser = ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.optionxform = str
    if not parser.read(path, encoding="utf-8-sig"):
        raise FileNotFoundError(f"config file not found: {path}")
    if not parser.has_section("MAIN"):
        raise ValueError(f"{path} has no [MAIN] section")
    return parser["MAIN"]


def _int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


_MAIN = _load_main_config()

VERSION = int(_MAIN["VERSION"])
COL_COUNT = int(_MAIN["COL_COUNT"])
ROW_COUNT = int(_MAIN["ROW_COUNT"])
ITEM_COUNT = int(_MAIN["ITEM_COUNT"])
PRIZE_RATE = int(_MAIN.get("PRIZE_RATE", "1"))
BASE_BET = int(_MAIN["BaseBet"])
LINE_MODE = int(_MAIN["LINE_MODE"])
SCATTER_MODE = int(_MAIN["SCATTER_MODE"])
SCATTER_ID = int(_MAIN["SCATTER_ID"])

# XML 使用单值 ITEM_PRIZE_N；保持 ITEM_PRIZES 的嵌套列表兼容形状。
ITEM_PRIZE_BY_SYMBOL = {
    symbol_id: int(_MAIN.get(f"ITEM_PRIZE_{symbol_id}", "0"))
    for symbol_id in range(ITEM_COUNT)
}
ITEM_PRIZES = [
    [ITEM_PRIZE_BY_SYMBOL[symbol_id]]
    for symbol_id in range(ITEM_COUNT)
]

# XML 的自定义水果机逻辑不依赖以下标准字段，导出安全默认值供旧脚本读取。
USE_WILDS = _int_list(_MAIN.get("USE_WILDS", ",".join(["0"] * ITEM_COUNT)))
BASE_NUMS = _int_list(_MAIN.get("BASE_NUMS", ",".join(["0"] * ITEM_COUNT)))
SCATTER_COLS = _int_list(_MAIN.get("SCATTER_COLS", ",".join(["1"] * COL_COUNT)))
SCATTER_SERIAL = int(_MAIN.get("SCATTER_SERIAL", "0"))
SCATTER_MULTIPLES = _int_list(
    _MAIN.get("SCATTER_MULTIPLES", ",".join(["0"] * (COL_COUNT * ROW_COUNT)))
)
SCATTER_PRIZES = _int_list(
    _MAIN.get("SCATTER_PRIZES", ",".join(["0"] * (COL_COUNT * ROW_COUNT)))
)
GRID_DISABLES = _int_list(
    _MAIN.get("GRID_DISABLES", ",".join(["0"] * (COL_COUNT * ROW_COUNT)))
)
GRID_DISABLES_FREE = _int_list(
    _MAIN.get("GRID_DISABLES_FREE", ",".join(["0"] * (COL_COUNT * ROW_COUNT)))
)
WILD_ID = 1
