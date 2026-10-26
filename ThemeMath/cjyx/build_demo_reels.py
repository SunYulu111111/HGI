"""按 model_linesgame 协议生成机制验收轴带，不代表正式数值方案。"""

from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
import random


def _validate_column(Column: list[int], Mode: str) -> None:
    if len(Column) != 5 or any(type(Symbol) is not int or not 0 <= Symbol <= 12 for Symbol in Column):
        raise ValueError("盘面每列必须为五个合法图标")
    Specials = [Row for Row, Symbol in enumerate(Column) if Symbol == 1]
    Scatters = [Row for Row, Symbol in enumerate(Column) if Symbol == 0]
    if len(Specials) > 1 or len(Scatters) > 1:
        raise ValueError("每列最多一个特殊 Wild 和一个 Scatter")
    if Specials:
        Position = Specials[0]
        if Scatters and Scatters[0] > Position:
            raise ValueError("Scatter 不得在特殊 Wild 下方")
        if Column[Position + 1:].count(2) > 1:
            raise ValueError("特殊 Wild 下方最多一个普通 Wild")
    elif Mode == "SuperFree":
        Candidates = range(5) if not Scatters else range(min(Scatters[0] + 1, 4), 5)
        if any(Column[Row + 1:].count(2) > 1 for Row in Candidates):
            raise ValueError("超级免费存在无法合法补入特殊 Wild 的候选位置")


def _validate_reels(Reels: list[list[int]], Mode: str) -> None:
    if len(Reels) != 5:
        raise ValueError("循环轴带必须为五列")
    for Reel in Reels:
        if not 5 <= len(Reel) <= 200:
            raise ValueError("循环轴带每列须为五至二百个图标")
        if len(",".join(map(str, Reel))) > 500:
            raise ValueError("单列滚轮字符串不得超过五百字符")
        for Start in range(len(Reel)):
            _validate_column([Reel[(Start + Row) % len(Reel)] for Row in range(5)], Mode)


def _validate_board(Board: list[int], Mode: str, PayLines: list[list[int]], Zero: bool = False) -> None:
    if len(Board) != 25:
        raise ValueError("固定盘及零盘必须为二十五格")
    for Column in range(5):
        _validate_column(Board[Column * 5:Column * 5 + 5], Mode)
    if Zero:
        if any(Symbol < 3 for Symbol in Board):
            raise ValueError("验收用零奖盘只使用普通图标")
        if any(Board[Line[0]] == Board[Line[1]] == Board[Line[2]] for Line in PayLines):
            raise ValueError("验收用零奖盘不得形成任何三连或以上赔付")


def _parse_config(Text: str) -> ConfigParser:
    Parser = ConfigParser(interpolation=None, inline_comment_prefixes=("#", ";"))
    Parser.optionxform = str
    Parser.read_string(Text)
    return Parser


def _payload(Parser: ConfigParser) -> tuple:
    return tuple(
        (Section, tuple(sorted((Key, Value) for Key, Value in Parser[Section].items() if not (Section == "MAIN" and Key == "VERSION"))))
        for Section in Parser.sections()
    )


def _versioned_text(Output: Path, Content: str, SourceRoot: Path, Relative: Path, ForceIncrement: bool = False) -> tuple[str, bool]:
    Reference = Output if Output.exists() else SourceRoot / Relative
    Previous = _parse_config(Reference.read_text(encoding="utf-8-sig")) if Reference.exists() else None
    Current = _parse_config(Content)
    Changed = Previous is None or _payload(Previous) != _payload(Current)
    PreviousVersion = int(Previous["MAIN"]["VERSION"]) if Previous is not None else 100
    Version = PreviousVersion + int(Changed or ForceIncrement)
    return Content.replace("VERSION=0\n", f"VERSION={Version}\n", 1), Changed


def build_reels(OutputDir: str | Path | None = None, Seed: int = 20261026) -> list[Path]:
    """生成五份配置；轴内容变化时同步递增 ex 和对应 main 版本。"""
    if type(Seed) is not int:
        raise ValueError("Seed 必须是整数")
    Root = Path(OutputDir) if OutputDir is not None else Path(__file__).resolve().parent
    SourceRoot = Path(__file__).resolve().parent
    Parser = _parse_config((SourceRoot / "special/cjyx_game_config.conf").read_text(encoding="utf-8-sig"))
    Main = Parser["MAIN"]
    PayLines = [[int(Value) for Value in Main[f"LINE_RULES_{Index}"].split(",")] for Index in range(int(Main["RULE_COUNT"]))]
    ZeroBoard = [int(Value) for Value in Main["INIT_ROLLER_ICON_0"].split(",")]
    Rng = random.Random(Seed)
    Pending = {}
    ChangedModes = {}
    ExFiles = []
    for Mode, Folder, Name in (
        ("Main", "reel_config", "cjyx_rand_ex_0.conf"),
        ("Free", "free_reel_config", "cjyx_free_rand_ex_0.conf"),
        ("SuperFree", "free_reel_config", "cjyx_super_free_rand_ex_0.conf"),
    ):
        Reels = []
        for Column in range(5):
            Reel = [Rng.randrange(3, 13) for _ in range(200)]
            for Position in range(2, 200, 100):
                Reel[Position] = 0
            SpecialPositions = range(30, 200, 100) if Mode == "Main" else range(10, 200, 40)
            WildPositions = range(32, 200, 100) if Mode == "Main" else range(12, 200, 20)
            for Position in SpecialPositions:
                Reel[Position] = 1
            for Position in WildPositions:
                Reel[Position] = 2
            Reels.append(Reel)
        _validate_reels(Reels, Mode)
        _validate_board(ZeroBoard, Mode, PayLines, Zero=True)
        Lines = ["[MAIN]", "VERSION=0", "", "[GENERAL_1]", "#正常、特殊、固定、零盘的相对权重。", "BASE_RATE=10000,0,0,0", "#验证轴带每列二百个图标，正常与特殊盘使用同一分布。"]
        for Prefix in ("NORMAL_ROLL", "SP_ROLL"):
            for Column, Reel in enumerate(Reels, 1):
                Lines.append(f"{Prefix}_{Column}=" + ",".join(map(str, Reel)))
        Lines += ["#固定与零盘均采用普通图标零奖初盘，按列读取二十五格，保留列内顺序。", "FIX_DISORDER=0", "FIX_NUM=1", "FIX_RESULT_1=" + ",".join(map(str, ZeroBoard)), "ZERO_DISORDER=0", "ZERO_NUM=1", "ZERO_RESULT_1=" + ",".join(map(str, ZeroBoard))]
        Relative = Path(Folder) / Name
        Output = Root / Relative
        Pending[Output], ChangedModes[Mode] = _versioned_text(Output, "\n".join(Lines) + "\n", SourceRoot, Relative)
        ExFiles.append(Output)
    MainFiles = []
    for Folder, Name, Modes in (
        ("reel_config", "cjyx_rand_main.conf", ("Main",)),
        ("free_reel_config", "cjyx_free_rand_main.conf", ("Free", "SuperFree")),
    ):
        Relative = Path(Folder) / Name
        Output = Root / Relative
        Content = "[MAIN]\nVERSION=0\nCOL_COUNT=5\nROW_COUNT=5\nITEM_COUNT=13\nITEM_COM_COUNT=1\n"
        Pending[Output], Changed = _versioned_text(Output, Content, SourceRoot, Relative, ForceIncrement=any(ChangedModes[Mode] for Mode in Modes))
        MainFiles.append(Output)
    for Output, Content in Pending.items():
        Output.parent.mkdir(parents=True, exist_ok=True)
        Output.write_text(Content, encoding="utf-8")
    return MainFiles + ExFiles


if __name__ == "__main__":
    for Output in build_reels():
        print(Output)
