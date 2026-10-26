"""超级英雄的固定线判奖、Wild 处理和免费游戏会话。"""

from __future__ import annotations

from itertools import permutations
from pathlib import Path
import random
import re
import sys
import threading


RootDir = Path(__file__).resolve().parent.parent
if str(RootDir) not in sys.path:
    sys.path.insert(0, str(RootDir))

from slots_math import LinesGame


RandomLock = threading.RLock()


class ThemeMath(LinesGame):
    """复用 LinesGame 的配置、四类出盘和基础判线，处理本主题特色。"""

    SPECIAL_CONFIG_DIR = "special"
    DEFAULT_GAME_CONFIG_FILE = "special/cjyx_game_config.conf"
    FREE_REEL_CONFIG_DIR = "free_reel_config"
    SuperFreeReelConfigDir = "free_reel_config"
    MainReelFileTemplate = "cjyx_rand_ex_{index}.conf"
    FreeReelFileTemplate = "cjyx_free_rand_ex_{index}.conf"
    SuperFreeReelFileTemplate = "cjyx_super_free_rand_ex_{index}.conf"

    def __init__(self, base_bet=100000, **kwargs):
        base_bet = kwargs.pop("BaseBet", base_bet)
        ProjectDir = kwargs.pop("ProjectDir", kwargs.pop("project_dir", Path(__file__).resolve().parent))
        GameConfigFile = kwargs.pop("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        Seed = kwargs.pop("Seed", None)
        if Seed is not None and type(Seed) is not int:
            raise ValueError("Seed 必须为整数或 None")
        ServerConfigFile = kwargs.pop("ServerConfigFile", "special/cjyx_game_server.conf")
        kwargs.setdefault("reel_file_template", self.MainReelFileTemplate)
        super().__init__(base_bet=base_bet, project_dir=ProjectDir, game_config_file=GameConfigFile, **kwargs)
        self.game_config_file = GameConfigFile
        self.ProjectDir = self.project_dir
        self.Rng = random.Random(Seed)
        self.ValidatedReelConfigs = set()
        Server = self._read_config_file(self.project_dir / ServerConfigFile)
        self._require_fields(Server, "System Base Info", ("BetScopes", "BetPerReel"))
        self._require_fields(Server, "Game Info", (
            "GameId", "OrdinarySymbolIds", "InitialFreeSpins", "RetriggerFreeSpins",
            "FreeSpinLimit", "FusionMultipliers",
        ))
        Info = Server["Game Info"]
        BetScopes = self._parse_int_list(Server["System Base Info"]["BetScopes"])
        BetPerReel = self._parse_int_list(Server["System Base Info"]["BetPerReel"])
        if not BetScopes or len(BetScopes) != len(BetPerReel):
            raise ValueError("BetScopes 和 BetPerReel 须按同一押注档位逐项对应")
        for Value in BetScopes + BetPerReel:
            self._positive_integer(Value, "押注档位系数")
        if any(Value != 1 for Value in BetPerReel):
            raise ValueError("超级英雄的 BetPerReel 各档须为 1，奖表按总投注计奖")
        self.GameInfo = {
            "GameId": int(Info["GameId"]), "Columns": self.config.col_count,
            "Rows": self.config.row_count, "ScatterId": 0,
            "SpecialWildId": self.wild_id, "WildId": 2,
            "OrdinarySymbolIds": self._parse_int_list(Info["OrdinarySymbolIds"]),
            "BetLevels": [self.BET_UNIT * PerReel * Scope for PerReel, Scope in zip(BetPerReel, BetScopes)],
            "PayScale": self.BET_UNIT * self.config.prize_rate,
            "PayLines": [[Column * self.config.row_count + Row for Column, Row in Line] for Line in self.config.line_rules],
            "PayTable": [{"SymbolId": Symbol, "Pays": [0] + list(self.config.item_prizes[Symbol])} for Symbol in range(1, self.config.item_count)],
        }
        for Name in ("InitialFreeSpins", "RetriggerFreeSpins", "FreeSpinLimit"):
            self.GameInfo[Name] = int(Info[Name])
        self.GameInfo["FusionMultipliers"] = self._parse_int_list(Info["FusionMultipliers"])
        WeightFields = ("MainFusionWeights", "FreeFusionWeights", "SuperFreeFusionWeights", "SuperFreeWildFillWeights")
        if any(Name in Info for Name in WeightFields):
            raise ValueError("融合与补入权重须配置在对应 TYPE 数字段，不得放在 [Game Info]")
        self.TypeConfigs = {}
        for Section in Server.sections():
            if not Section.isdigit():
                continue
            TypeIndex = int(Section)
            if TypeIndex in self.TypeConfigs:
                raise ValueError(f"TYPE {TypeIndex} 的配置段不得重复")
            self._require_fields(Server, Section, WeightFields)
            self.TypeConfigs[TypeIndex] = {Name: self._parse_int_list(Server[Section][Name]) for Name in WeightFields}
        if 0 not in self.TypeConfigs:
            raise ValueError("cjyx_game_server.conf 缺少默认 TYPE 参数段 [0]")
        self.GameInfo.update(self.TypeConfigs[0])
        # TYPE 0 与固定盘验收使用同一份参数，避免产生两套权重来源。
        self.TypeConfigs[0] = self.GameInfo
        self.CurrentType = 0
        self.FreeType = None
        self.Config = {"GameInfo": self.GameInfo, "ReelSets": []}
        self._validate_base_protocol()
        self._validate_config()
        if type(base_bet) is not int or base_bet not in self.GameInfo["BetLevels"]:
            raise ValueError("base_bet 必须为配置中的投注档位")
        self.PayTable = {Entry["SymbolId"]: Entry["Pays"] for Entry in self.GameInfo["PayTable"]}
        self._validate_reel_files()
        self.Mode = "Main"
        self.FreeSpinsRemaining = 0
        self.FreeSpinsPlayed = 0
        self.FreeSpinsAwarded = 0
        self.FreeTotalWin = 0
        self.ActivatedColumns = set()
        self.last_ng_result = {}
        self.last_fg_result = {}

    @property
    def BaseBet(self):
        return self.base_bet

    @BaseBet.setter
    def BaseBet(self, Value):
        if type(Value) is not int or Value not in self.GameInfo["BetLevels"]:
            raise ValueError("BaseBet 必须为配置中的投注档位")
        self.base_bet = Value

    @staticmethod
    def _require_fields(Parser, Section, Names):
        if not Parser.has_section(Section):
            raise ValueError(f"配置缺少 [{Section}] 段")
        Missing = [Name for Name in Names if Name not in Parser[Section]]
        if Missing:
            raise ValueError(f"[{Section}] 缺少字段：{', '.join(Missing)}")

    def _validate_base_protocol(self):
        Main = self._read_config_file(self.project_dir / self.game_config_file)["MAIN"]
        self.scatter_id = int(Main.get("SCATTER_ID", "0"))
        self.scatter_cols = self._parse_int_list(Main.get("SCATTER_COLS", ""))
        self.scatter_multiples = self._parse_int_list(Main.get("SCATTER_MULTIPLES", ""))
        if self.config.prize_rate != 1:
            raise ValueError("超级英雄 PRIZE_RATE 须为 1")
        if int(Main.get("RULE_COUNT", "0")) != 19:
            raise ValueError("RULE_COUNT 须为 19")
        if self.scatter_id != 0 or int(Main.get("SCATTER_MODE", "1")) != 1:
            raise ValueError("Scatter 须使用图标 0 和 SCATTER_MODE=1")
        if self.scatter_cols != [1] * 5 or int(Main.get("SCATTER_SERIAL", "0")) != 0:
            raise ValueError("Scatter 须检查全部五列且不要求连续列")
        for Name in ("SCATTER_MULTIPLES", "SCATTER_PRIZES"):
            if Name in Main and self._parse_int_list(Main[Name]) != [0] * 25:
                raise ValueError(f"{Name} 须为 25 个 0；免费奖励由特色流程处理")

    @staticmethod
    def _positive_integer(Value, Name, AllowZero=False):
        if type(Value) is not int or Value < (0 if AllowZero else 1):
            raise ValueError(f"{Name} 必须为{'非负' if AllowZero else '正'}整数")

    @classmethod
    def _validate_weights(cls, Weights, Size, Name):
        if not isinstance(Weights, list) or len(Weights) != Size:
            raise ValueError(f"{Name} 必须包含 {Size} 项")
        for Weight in Weights:
            cls._positive_integer(Weight, Name, AllowZero=True)
        if sum(Weights) == 0:
            raise ValueError(f"{Name} 权重之和必须大于 0")

    def _validate_config(self):
        try:
            Info = self.Config["GameInfo"]
            if Info["GameId"] != 373:
                raise ValueError("GameId 须为超级英雄的游戏 ID 373")
            for Name, Expected in (("Columns", 5), ("Rows", 5), ("ScatterId", 0), ("SpecialWildId", 1), ("WildId", 2)):
                if type(Info[Name]) is not int or Info[Name] != Expected:
                    raise ValueError(f"{Name} 必须为 {Expected}")
            if Info["OrdinarySymbolIds"] != list(range(3, 13)):
                raise ValueError("OrdinarySymbolIds 必须依次为 3 至 12")
            self._positive_integer(Info["PayScale"], "PayScale")
            Levels = Info["BetLevels"]
            if not isinstance(Levels, list) or not Levels or len(set(Levels)) != len(Levels):
                raise ValueError("BetLevels 必须为非空且不重复的档位数组")
            for Value in Levels:
                self._positive_integer(Value, "BetLevels")
            Lines = Info["PayLines"]
            if not isinstance(Lines, list) or len(Lines) != 19:
                raise ValueError("PayLines 必须包含 19 条固定线")
            for Line in Lines:
                if not isinstance(Line, list) or len(Line) != 5:
                    raise ValueError("每条赔付线必须包含 5 个位置")
                for Column, Position in enumerate(Line):
                    if type(Position) is not int or Position // 5 != Column or not 0 <= Position < 25:
                        raise ValueError("PayLines 位置必须从左至右且每列一个")
            if len({tuple(Line) for Line in Lines}) != 19:
                raise ValueError("PayLines 不得重复")
            Entries = Info["PayTable"]
            if not isinstance(Entries, list) or len(Entries) != 12:
                raise ValueError("PayTable 必须包含图标 1 至 12")
            Symbols = []
            for Entry in Entries:
                Symbol = Entry["SymbolId"]
                if type(Symbol) is not int:
                    raise ValueError("SymbolId 必须为整数")
                Symbols.append(Symbol)
                Pays = Entry["Pays"]
                if not isinstance(Pays, list) or len(Pays) != 6:
                    raise ValueError("Pays 按连数 0 至 5 配置，共 6 项")
                for Pay in Pays:
                    self._positive_integer(Pay, "Pays", AllowZero=True)
                    if any((Bet * Pay) % Info["PayScale"] for Bet in Levels):
                        raise ValueError("奖表与投注档位必须产生整数奖励")
                if Pays[:3] != [0, 0, 0]:
                    raise ValueError("起奖连数不得小于 3")
                if Symbol in (1, 2) and (Pays[3:5] != [0, 0] or Pays[5] != 25 * Info["PayScale"]):
                    raise ValueError("Wild 自身仅五连赔付总投注的 25 倍")
            if sorted(Symbols) != list(range(1, 13)):
                raise ValueError("PayTable 必须无重复且覆盖图标 1 至 12")
            for Name in ("InitialFreeSpins", "RetriggerFreeSpins", "FreeSpinLimit"):
                self._positive_integer(Info[Name], Name)
            if Info["InitialFreeSpins"] >= Info["FreeSpinLimit"]:
                raise ValueError("初始免费次数必须小于免费次数控制界限")
            Multipliers = Info["FusionMultipliers"]
            if not isinstance(Multipliers, list) or not Multipliers or len(set(Multipliers)) != len(Multipliers):
                raise ValueError("FusionMultipliers 必须非空且不重复")
            for Multiple in Multipliers:
                self._positive_integer(Multiple, "FusionMultipliers")
                if Multiple < 2:
                    raise ValueError("融合倍数必须至少为 2")
            for TypeIndex, TypeConfig in self.TypeConfigs.items():
                for Mode in ("Main", "Free", "SuperFree"):
                    self._validate_weights(TypeConfig[Mode + "FusionWeights"], len(Multipliers), f"TYPE {TypeIndex} {Mode}FusionWeights")
                self._validate_weights(TypeConfig["SuperFreeWildFillWeights"], 25, f"TYPE {TypeIndex} SuperFreeWildFillWeights")
                # 任意 Scatter 高度的最小非空候选集合仅含底行。
                if any(TypeConfig["SuperFreeWildFillWeights"][Position] <= 0 for Position in (4, 9, 14, 19, 24)):
                    raise ValueError(f"TYPE {TypeIndex} SuperFreeWildFillWeights 的每列底行权重必须大于 0")
            if self.config.line_mode != 2 or self.config.item_count != 13 or self.config.wild_id != 1:
                raise ValueError("基础配置须为 13 图标、左到右 Lines 和通用 Wild ID 1")
            if self.config.base_nums != [0, 5, 5] + [3] * 10:
                raise ValueError("BASE_NUMS 须保持普通图标三连和 Wild 五连起奖")
            if self.config.use_wilds != [0, 0, 0] + [1] * 10:
                raise ValueError("USE_WILDS 须禁用 Scatter 和 Wild 自身替代，并启用普通图标替代")
            if any(self.config.grid_disables) or any(self.config.grid_disables_free):
                raise ValueError("本机台 25 格均参与判奖")
        except (KeyError, TypeError) as Error:
            raise ValueError(f"数学配置缺项或类型错误：{Error}") from Error

    @staticmethod
    def _validate_column(Column, Mode):
        if len(Column) != 5 or any(type(Symbol) is not int or not 0 <= Symbol <= 12 for Symbol in Column):
            raise ValueError("盘面每列须为 5 个 0 至 12 的图标 ID")
        Specials = [Row for Row, Symbol in enumerate(Column) if Symbol == 1]
        Scatters = [Row for Row, Symbol in enumerate(Column) if Symbol == 0]
        if len(Specials) > 1 or len(Scatters) > 1:
            raise ValueError("每列最多一个特殊 Wild 和一个 Scatter")
        if Specials:
            Position = Specials[0]
            if Scatters and Scatters[0] > Position:
                raise ValueError("Scatter 不得位于特殊 Wild 下方")
            if Column[Position + 1:].count(2) > 1:
                raise ValueError("特殊 Wild 下方最多一个普通 Wild")
        elif Mode == "SuperFree":
            # 验证所有合法候选，抽取时仍只按 Scatter 限制位置。
            Candidates = range(5) if not Scatters else range(min(Scatters[0] + 1, 4), 5)
            if any(Column[Row + 1:].count(2) > 1 for Row in Candidates):
                raise ValueError("超级免费任一候选补入特殊 Wild 后，其下方最多一个普通 Wild")

    def _validate_reels(self, Reels, Mode):
        if not isinstance(Reels, list) or len(Reels) != 5:
            raise ValueError("轴带必须为 5 列")
        for Reel in Reels:
            if not isinstance(Reel, list) or not 5 <= len(Reel) <= 200:
                raise ValueError("每列循环轴带须包含 5 至 200 个图标")
            if len(",".join(map(str, Reel)).encode("utf-8")) > 500:
                raise ValueError("单条滚轮字符串不得超过 500 字节")
            for Start in range(len(Reel)):
                Window = [Reel[(Start + Offset) % len(Reel)] for Offset in range(5)]
                self._validate_column(Window, Mode)

    def _normalize_board(self, Board, Mode):
        if Mode not in ("Main", "Free", "SuperFree"):
            raise ValueError("Mode 必须为 Main、Free 或 SuperFree")
        if not isinstance(Board, (list, tuple)):
            raise ValueError("Board 必须为 25 个图标或 5 列各 5 格")
        if len(Board) == 5 and all(isinstance(Column, (list, tuple)) for Column in Board):
            if any(len(Column) != 5 for Column in Board):
                raise ValueError("Board 每列必须为 5 格")
            Result = [Symbol for Column in Board for Symbol in Column]
        elif len(Board) == 25:
            Result = list(Board)
        else:
            raise ValueError("Board 必须为 25 个图标或 5 列各 5 格")
        for Column in range(5):
            self._validate_column(Result[Column * 5:Column * 5 + 5], Mode)
        return Result

    def _mode_reels(self, Mode):
        if Mode == "Main":
            return self.reel_config_dir, self.reel_file_template
        if Mode == "Free":
            return self.FREE_REEL_CONFIG_DIR, self.FreeReelFileTemplate
        if Mode == "SuperFree":
            return self.SuperFreeReelConfigDir, self.SuperFreeReelFileTemplate
        raise ValueError("非法游戏模式")

    def _validate_reel_files(self):
        TypesByMode = {}
        for Mode in ("Main", "Free", "SuperFree"):
            TypesByMode[Mode] = set()
            Directory, Template = self._mode_reels(Mode)
            Directory = self._resolve_reel_config_dir(Directory)
            Pattern = Template.replace("{index}", "*")
            Files = sorted(Directory.glob(Pattern))
            if not Files:
                raise ValueError(f"{Mode} 缺少模板轴带 {Pattern}")
            for File in Files:
                Match = re.search(r"_(\d+)\.conf$", File.name)
                if not Match:
                    continue
                Index = int(Match.group(1))
                self._type_config(Index)
                TypesByMode[Mode].add(Index)
                Parser = self._read_config_file(File)
                Generals = [int(Section[8:]) for Section in Parser.sections() if re.fullmatch(r"GENERAL_\d+", Section)]
                if not Generals:
                    raise ValueError(f"{File.name} 没有 GENERAL 配置")
                for General in Generals:
                    Loaded = self._load_reel_config(Index, General, reel_config_dir=Directory, reel_file_template=Template)
                    self._validate_loaded_reel(Loaded, Mode)
                    self.Config["ReelSets"].append({"Mode": Mode, "Index": Index, "GeneralIndex": General, "Path": str(File.relative_to(self.project_dir))})
        if not TypesByMode["Main"] or any(Types != TypesByMode["Main"] for Types in TypesByMode.values()):
            raise ValueError("每个 TYPE 必须同时配置主游戏、普通免费和超级免费轴带")

    def _type_config(self, TypeIndex):
        if TypeIndex not in self.TypeConfigs:
            raise ValueError(f"cjyx_game_server.conf 缺少 TYPE 参数段 [{TypeIndex}]")
        return self.TypeConfigs[TypeIndex]

    @staticmethod
    def _loaded_type(Loaded):
        Match = re.search(r"(?:^|_)(\d+)\.conf$", Path(Loaded["reel_config_path"]).name)
        if Match is None:
            raise ValueError("轴带文件名须包含 TYPE 索引")
        return int(Match.group(1))

    def _validate_loaded_reel(self, Loaded, Mode):
        Key = (id(Loaded), Mode)
        if Key in self.ValidatedReelConfigs:
            return
        Rates = Loaded["base_rate"]
        if len(Rates) != 4 or any(type(Rate) is not int or Rate < 0 for Rate in Rates) or sum(Rates) <= 0:
            raise ValueError("BASE_RATE 必须为四项非负权重且总和为正")
        Source = self._read_config_file(Path(Loaded["reel_config_path"]))[f"GENERAL_{Loaded['general_index']}"]
        for Name, Value in Source.items():
            if re.fullmatch(r"(?:NORMAL|SP)_ROLL_\d+", Name) and len(Value.encode("utf-8")) > 500:
                raise ValueError(f"{Name} 的滚轮字符串不得超过 500 字节")
        self._validate_reels(Loaded["normal_rolls"], Mode)
        if Loaded["special_rolls"] or Rates[1]:
            self._validate_reels(Loaded["special_rolls"], Mode)
        for Kind, RateIndex, DisorderName in (("fix", 2, "FixDisorder"), ("zero", 3, "ZeroDisorder")):
            Results = Loaded[Kind + "_results"]
            if Rates[RateIndex] and not Results:
                raise ValueError(f"{Kind.upper()} 出盘权重为正时须配置结果")
            for Result in Results:
                if len(Result) != 25:
                    raise ValueError(f"{Kind.upper()}_RESULT 必须包含 25 个图标")
                Flat = self._normalize_board(Result, Mode)
                if Loaded[DisorderName]:
                    for Column in range(5):
                        for Permutation in set(permutations(Flat[Column * 5:Column * 5 + 5])):
                            self._validate_column(Permutation, Mode)
        self.ValidatedReelConfigs.add(Key)

    def _draw_board(self, Mode, Index, GeneralIndex, Board, ReelFileTemplate=None, LockedType=None):
        self._positive_integer(Index, "index", AllowZero=True)
        self._positive_integer(GeneralIndex, "general_index", AllowZero=True)
        Directory, Template = self._mode_reels(Mode)
        Template = ReelFileTemplate or Template
        Loaded = self._load_reel_config(Index, GeneralIndex, reel_config_dir=Directory, reel_file_template=Template)
        self._validate_loaded_reel(Loaded, Mode)
        TypeIndex = self._loaded_type(Loaded)
        self._type_config(TypeIndex)
        if LockedType is not None and TypeIndex != LockedType:
            raise ValueError(f"本轮免费须沿用 TYPE {LockedType}，当前请求解析为 TYPE {TypeIndex}")
        if Board is not None:
            self.last_spin_info = {"Source": "FixedBoard", "Mode": Mode, "TypeIndex": TypeIndex, "index": Index, "requested_general_index": GeneralIndex, "general_index": Loaded["general_index"], "general_index_fallback": Loaded["general_index_fallback"], "reel_config_index_fallback": TypeIndex != Index, "reel_config_file": Path(Loaded["reel_config_path"]).name, "spin_type": "fix", "source_type": "FixedBoard", "row": 5, "col": 5}
            self.last_spin_state = {}
            return self._normalize_board(Board, Mode), dict(self.last_spin_info)
        # 继承 spin 使用模块 random；临时安装本实例状态并完整恢复调用方状态。
        with RandomLock:
            GlobalState = random.getstate()
            random.setstate(self.Rng.getstate())
            try:
                Columns = self.spin(index=Index, general_index=GeneralIndex, row=5, col=5, reel_config_dir=Directory, reel_file_template=Template)
            finally:
                self.Rng.setstate(random.getstate())
                random.setstate(GlobalState)
        SpinInfo = dict(self.last_spin_info)
        SpinInfo.update({"Source": "Reels", "Mode": Mode, "TypeIndex": TypeIndex})
        return self._normalize_board(Columns, Mode), SpinInfo

    def _weighted_choice(self, Values, Weights):
        Total = sum(Weights)
        if Total <= 0:
            raise ValueError("候选位置权重之和必须大于 0")
        Draw = self.Rng.randrange(Total)
        for Value, Weight in zip(Values, Weights):
            Draw -= Weight
            if Draw < 0:
                return Value
        raise RuntimeError("权重抽取未命中")

    def _replace_scatter(self, Board, Count, Reason, Replacements):
        Positions = [Position for Position, Symbol in enumerate(Board) if Symbol == 0]
        for Position in self.Rng.sample(Positions, Count):
            Symbol = self.Rng.choice(self.GameInfo["OrdinarySymbolIds"])
            Board[Position] = Symbol
            Replacements.append({"Position": Position, "OriginalSymbolId": 0, "SymbolId": Symbol, "Reason": Reason})

    def cal_item_list(self, item_list, return_detail=False, free_game=False, row=None, col=None):
        """基础固定线判奖；统一两种 Wild，不执行延展、融合或次数处理。"""
        Columns, ColCount, RowCount = self._normalize_item_list(item_list, row=row, col=col)
        if ColCount != 5 or RowCount != 5 or any(len(Column) != 5 for Column in Columns):
            raise ValueError("盘面须为 5 列 5 行")
        if any(type(Symbol) is not int or not 0 <= Symbol <= 12 for Column in Columns for Symbol in Column):
            raise ValueError("盘面图标 ID 须为 0 至 12")
        Mapped = [[1 if Symbol == 2 else Symbol for Symbol in Column] for Column in Columns]
        Result = super().cal_item_list(Mapped, return_detail=return_detail, free_game=free_game, row=5, col=5)
        if return_detail:
            for Item in Result["items"]:
                Item["symbols"] = [Columns[Column][Row] for Column, Row in Item["positions"]]
        return Result

    def check_win_free(self, item_list, row=None, col=None, free_game=False):
        """查询已处理盘面是否触发免费奖励或升级，不抽样、不修改会话。"""
        Columns, ColCount, RowCount = self._normalize_item_list(item_list, row=row, col=col)
        if ColCount != 5 or RowCount != 5 or any(len(Column) != 5 for Column in Columns):
            raise ValueError("盘面须为 5 列 5 行")
        ScatterCount = sum(Symbol == self.scatter_id for Column in Columns for Symbol in Column)
        return ScatterCount in (3, 4)

    def _line_wins(self, Board, Mode="Main"):
        Columns = [Board[Column * 5:Column * 5 + 5] for Column in range(5)]
        BaseResult = self.cal_item_list(Columns, return_detail=True, free_game=Mode != "Main", row=5, col=5)
        Items = []
        for Item in BaseResult["items"]:
            Positions = [Column * 5 + Row for Column, Row in Item["positions"]]
            Items.append({"LineId": Item["line_index"] + 1, "SymbolId": Item["item_id"], "Count": Item["hit_num"], "Positions": Positions, "BaseWin": Item["win"], "Multiplier": 1, "BasePrize": Item["prize"], "Symbols": [Board[Position] for Position in Positions], "Direction": Item["direction"]})
        return Items

    def _evaluate_board(self, Board, Mode, Played, Remaining, ActivatedColumns, ReturnDetail, TypeIndex=0):
        Working = self._normalize_board(Board, Mode)
        TypeConfig = self._type_config(TypeIndex)
        Replacements = []
        Activated = set(ActivatedColumns) if Mode == "SuperFree" else set()
        if any(type(Column) is not int or not 0 <= Column < 5 for Column in Activated):
            raise ValueError("ActivatedColumns 必须为 0 至 4 的列索引")
        if Mode == "SuperFree":
            for Column in sorted(Activated):
                Start = Column * 5
                Positions = list(range(Start, Start + 5))
                if any(Working[Position] == 1 for Position in Positions):
                    continue
                Scatter = next((Position for Position in Positions if Working[Position] == 0), None)
                if Scatter == Start + 4:
                    Position = Scatter
                else:
                    Candidates = Positions if Scatter is None else list(range(Scatter + 1, Start + 5))
                    Weights = [TypeConfig["SuperFreeWildFillWeights"][Position] for Position in Candidates]
                    Position = self._weighted_choice(Candidates, Weights)
                OriginalSymbol = Working[Position]
                Working[Position] = 1
                Replacements.append({"Position": Position, "OriginalSymbolId": OriginalSymbol, "SymbolId": 1, "Reason": "ActivatedColumn"})
        ScatterCount = Working.count(0)
        ScatterLimit = 3 if Mode == "SuperFree" else 4
        if ScatterCount > ScatterLimit:
            self._replace_scatter(Working, ScatterCount - ScatterLimit, "ScatterLimit", Replacements)
            ScatterCount = ScatterLimit
        if Mode != "Main" and ScatterCount in (3, 4):
            PredictedRemaining = Remaining + self.GameInfo["RetriggerFreeSpins"] if ScatterCount == 3 else max(Remaining, self.GameInfo["InitialFreeSpins"])
            if PredictedRemaining >= self.GameInfo["FreeSpinLimit"] or Played + PredictedRemaining >= self.GameInfo["FreeSpinLimit"]:
                self._replace_scatter(Working, ScatterCount - 2, "FreeSpinLimit", Replacements)
                ScatterCount = 2
        if Mode == "SuperFree":
            Activated.update(Position // 5 for Position, Symbol in enumerate(Working) if Symbol == 1)
        SpecialPositions = [Position for Position, Symbol in enumerate(Working) if Symbol == 1]
        Temporary = list(Working)
        Ranges = {}
        for Position in SpecialPositions:
            Positions = list(range(Position, (Position // 5 + 1) * 5))
            Ranges[Position] = Positions
            for Target in Positions:
                Temporary[Target] = 1
        PreviewItems = self._line_wins(Temporary, Mode)
        WinningPositions = {Position for Item in PreviewItems for Position in Item["Positions"]}
        Final = list(Working)
        WildFeatures = []
        for Position in SpecialPositions:
            Positions = Ranges[Position]
            Extended = len(Positions) > 1 and bool(WinningPositions.intersection(Positions))
            Multiplier = 0
            if Extended:
                if any(Working[Target] == 2 for Target in Positions[1:]):
                    Multiplier = self._weighted_choice(self.GameInfo["FusionMultipliers"], TypeConfig[Mode + "FusionWeights"])
                for Target in Positions:
                    Final[Target] = 1
            WildFeatures.append({"Column": Position // 5, "Position": Position, "Extended": Extended, "Multiplier": Multiplier, "Positions": Positions if Extended else [Position]})
        Items = self._line_wins(Final, Mode)
        UltimateHit = False
        for Item in Items:
            Positions = set(Item["Positions"])
            Multiplier = sum(Feature["Multiplier"] for Feature in WildFeatures if Feature["Multiplier"] and Positions.intersection(Feature["Positions"]))
            Item["Multiplier"] = Multiplier or 1
            Item["Win"] = Item["BaseWin"] * Item["Multiplier"]
            if Item["SymbolId"] in (1, 2) and Item["Count"] == 5 and Multiplier > 100:
                UltimateHit = True
        return {"Mode": Mode, "NextMode": Mode, "TypeIndex": TypeIndex, "TotalWin": sum(Item["Win"] for Item in Items), "ScatterCount": ScatterCount, "AwardedFreeSpins": 0, "FreeSpinsRemaining": Remaining, "FreeSpinsPlayed": Played, "FreeSpinsAwarded": self.FreeSpinsAwarded, "FreeTotalWin": self.FreeTotalWin, "Upgraded": False, "UltimateHit": UltimateHit, "ActivatedColumns": sorted(Activated), "Board": Working, "FinalBoard": Final, "WinItems": Items if ReturnDetail else [], "WildFeatures": WildFeatures if ReturnDetail else [], "Replacements": Replacements, "SpinInfo": {}}

    def _add_template_result(self, Result, ReturnDetail):
        Items = []
        for Item in Result["WinItems"]:
            Positions = [(Position // 5, Position % 5) for Position in Item["Positions"]]
            Items.append({"line_index": Item["LineId"] - 1, "item_id": Item["SymbolId"], "hit_num": Item["Count"], "positions": Positions, "symbols": list(Item["Symbols"]), "prize": Item["BasePrize"], "win": Item["Win"], "direction": Item["Direction"], "Multiplier": Item["Multiplier"]})
        Result.update({"item_list": [Result["Board"][Column * 5:Column * 5 + 5] for Column in range(5)], "total_win": Result["TotalWin"], "line_win": Result["TotalWin"], "win_items": Items if ReturnDetail else [], "win_positions": sorted({Position for Item in Items for Position in Item["positions"]}), "win_free": self.check_win_free(Result["Board"], row=5, col=5, free_game=Result["Mode"] != "Main"), "spin_info": Result["SpinInfo"], "free_game": Result["Mode"] != "Main"})
        self.last_win_items = Result["win_items"]
        self.last_win_positions = Result["win_positions"]
        if Result["Mode"] == "Main":
            self.last_ng_result = Result
        else:
            self.last_fg_result = Result
        return Result

    @staticmethod
    def _spin_arguments(index, general_index, return_detail, kwargs):
        Index = kwargs.pop("Index", index)
        GeneralIndex = kwargs.pop("GeneralIndex", general_index)
        ReturnDetail = kwargs.pop("ReturnDetail", return_detail)
        if kwargs:
            raise TypeError(f"不支持的参数：{', '.join(kwargs)}")
        return Index, GeneralIndex, ReturnDetail

    def evaluate(self, item_list=None, row=None, col=None, return_detail=True, free_game=False, Board=None, Mode=None, **kwargs):
        """按模板接口处理固定盘，不推进会话；免费计数视为本手已消耗状态。"""
        ReturnDetail = kwargs.pop("ReturnDetail", return_detail)
        if kwargs:
            raise TypeError(f"不支持的参数：{', '.join(kwargs)}")
        if row not in (None, 5) or col not in (None, 5):
            raise ValueError("盘面须为 5 列 5 行")
        if item_list is not None and Board is not None:
            raise TypeError("item_list 和 Board 不得同时提供")
        Source = Board if Board is not None else item_list
        CurrentMode = Mode if Mode is not None else (self.Mode if free_game and self.Mode != "Main" else "Free" if free_game else "Main")
        Result = self._evaluate_board(Source, CurrentMode, self.FreeSpinsPlayed, self.FreeSpinsRemaining, self.ActivatedColumns, True, TypeIndex=self.CurrentType)
        Result["SpinInfo"] = {"Source": "FixedBoard", "Mode": CurrentMode}
        self._add_template_result(Result, ReturnDetail)
        if not ReturnDetail:
            Result["WinItems"] = []
            Result["WildFeatures"] = []
        return Result

    def start_free(self, Mode="Free", FreeSpins=10):
        if self.Mode != "Main" or self.FreeSpinsRemaining:
            raise RuntimeError("免费游戏进行中，不能覆盖已有会话")
        if Mode not in ("Free", "SuperFree"):
            raise ValueError("免费模式必须为 Free 或 SuperFree")
        self._positive_integer(FreeSpins, "FreeSpins")
        if FreeSpins >= self.GameInfo["FreeSpinLimit"]:
            raise ValueError("初始免费次数必须小于次数控制界限")
        self.Mode = Mode
        self.FreeSpinsRemaining = FreeSpins
        self.FreeSpinsPlayed = 0
        self.FreeSpinsAwarded = FreeSpins
        self.FreeTotalWin = 0
        self.ActivatedColumns = set()
        self.FreeType = self.CurrentType

    def ng_spin(self, index=0, general_index=1, return_detail=False, Board=None, reel_file_template=None, **kwargs):
        Index, GeneralIndex, ReturnDetail = self._spin_arguments(index, general_index, return_detail, kwargs)
        if self.Mode != "Main" or self.FreeSpinsRemaining:
            raise RuntimeError("须先完成正在进行的免费游戏")
        Drawn, SpinInfo = self._draw_board("Main", Index, GeneralIndex, Board, reel_file_template)
        TypeIndex = SpinInfo["TypeIndex"]
        Result = self._evaluate_board(Drawn, "Main", 0, 0, set(), True, TypeIndex=TypeIndex)
        self.CurrentType = TypeIndex
        self.FreeType = None
        self.FreeSpinsRemaining = self.FreeSpinsPlayed = self.FreeSpinsAwarded = self.FreeTotalWin = 0
        self.ActivatedColumns = set()
        ScatterCount = Result["ScatterCount"]
        if ScatterCount >= 3:
            self.start_free("SuperFree" if ScatterCount == 4 else "Free", self.GameInfo["InitialFreeSpins"])
            Result["AwardedFreeSpins"] = self.FreeSpinsRemaining
        self._add_state(Result)
        Result["SpinInfo"] = SpinInfo
        self._add_template_result(Result, ReturnDetail)
        if not ReturnDetail:
            Result["WinItems"] = []
            Result["WildFeatures"] = []
        return Result

    def fg_spin(self, index=0, general_index=1, return_detail=False, Board=None, reel_file_template=None, **kwargs):
        Index, GeneralIndex, ReturnDetail = self._spin_arguments(index, general_index, return_detail, kwargs)
        if self.Mode not in ("Free", "SuperFree") or self.FreeSpinsRemaining <= 0:
            raise RuntimeError("当前没有可执行的免费次数")
        CurrentMode = self.Mode
        Drawn, SpinInfo = self._draw_board(CurrentMode, Index, GeneralIndex, Board, reel_file_template, LockedType=self.FreeType)
        Played, Remaining = self.FreeSpinsPlayed + 1, self.FreeSpinsRemaining - 1
        Result = self._evaluate_board(Drawn, CurrentMode, Played, Remaining, self.ActivatedColumns, True, TypeIndex=self.FreeType)
        Awarded = 0
        if Result["ScatterCount"] == 3:
            Awarded = self.GameInfo["RetriggerFreeSpins"]
        elif CurrentMode == "Free" and Result["ScatterCount"] == 4:
            Awarded = max(0, self.GameInfo["InitialFreeSpins"] - Remaining)
            self.Mode = "SuperFree"
            self.ActivatedColumns = set()
            Result["Upgraded"] = True
        # 再触发也需要提交本手新增的超级免费激活列。
        if CurrentMode == "SuperFree":
            self.ActivatedColumns = set(Result["ActivatedColumns"])
        self.FreeSpinsPlayed = Played
        self.FreeSpinsRemaining = Remaining + Awarded
        self.FreeSpinsAwarded += Awarded
        self.FreeTotalWin += Result["TotalWin"]
        Result["AwardedFreeSpins"] = Awarded
        if self.FreeSpinsRemaining == 0:
            self.Mode = "Main"
            self.ActivatedColumns = set()
            self.FreeType = None
        self._add_state(Result)
        Result["SpinInfo"] = SpinInfo
        self._add_template_result(Result, ReturnDetail)
        if not ReturnDetail:
            Result["WinItems"] = []
            Result["WildFeatures"] = []
        return Result

    def _add_state(self, Result):
        Result.update({"NextMode": self.Mode, "FreeSpinsRemaining": self.FreeSpinsRemaining, "FreeSpinsPlayed": self.FreeSpinsPlayed, "FreeSpinsAwarded": self.FreeSpinsAwarded, "FreeTotalWin": self.FreeTotalWin, "ActivatedColumns": sorted(self.ActivatedColumns)})

    def play_round(self, ReturnDetail=False, Index=0, GeneralIndex=1, FreeGeneralIndex=None, MainReelFileTemplate=None, FreeReelFileTemplate=None, SuperFreeReelFileTemplate=None):
        """完成一次付费旋转及其触发的全部免费旋转。"""
        FreeGeneralIndex = GeneralIndex if FreeGeneralIndex is None else FreeGeneralIndex
        Main = self.ng_spin(index=Index, general_index=GeneralIndex, return_detail=ReturnDetail, reel_file_template=MainReelFileTemplate)
        Result = {"MainWin": Main["TotalWin"], "FreeWin": 0, "SuperFreeWin": 0, "TotalWin": Main["TotalWin"], "FreeSpins": 0, "FreeTriggers": int(Main["NextMode"] == "Free"), "SuperFreeTriggers": int(Main["NextMode"] == "SuperFree"), "Retriggers": 0, "Upgrades": 0, "UltimateHits": int(Main["UltimateHit"]), "UltimateWin": Main["TotalWin"] if Main["UltimateHit"] else 0, "SpinCount": 1, "MainHit": int(Main["TotalWin"] > 0), "FreeHits": 0, "SuperFreeSpins": 0, "NormalFreeSpins": 0, "SuperFreeHits": 0, "FreeSpinsAwarded": Main["AwardedFreeSpins"]}
        Spins = [Main] if ReturnDetail else []
        while self.FreeSpinsRemaining:
            Template = SuperFreeReelFileTemplate if self.Mode == "SuperFree" else FreeReelFileTemplate
            Spin = self.fg_spin(index=Index, general_index=FreeGeneralIndex, return_detail=ReturnDetail, reel_file_template=Template)
            IsSuper = Spin["Mode"] == "SuperFree"
            Result["SuperFreeWin" if IsSuper else "FreeWin"] += Spin["TotalWin"]
            Result["TotalWin"] += Spin["TotalWin"]
            Result["FreeSpins"] += 1
            Result["SuperFreeSpins"] += int(IsSuper)
            Result["NormalFreeSpins"] += int(not IsSuper)
            Result["SuperFreeHits" if IsSuper else "FreeHits"] += int(Spin["TotalWin"] > 0)
            Result["Retriggers"] += int(Spin["ScatterCount"] == 3)
            Result["Upgrades"] += int(Spin["Upgraded"])
            Result["UltimateHits"] += int(Spin["UltimateHit"])
            Result["UltimateWin"] += Spin["TotalWin"] if Spin["UltimateHit"] else 0
            Result["SpinCount"] += 1
            Result["FreeSpinsAwarded"] += Spin["AwardedFreeSpins"]
            if ReturnDetail:
                Spins.append(Spin)
        if ReturnDetail:
            Result["Spins"] = Spins
        return Result
