"""通用 Slots 数学逻辑。

这个文件尽量不绑定具体主题；主题只需要提供项目目录、game_config.conf
和 reel_config，就可以复用这里的 spin、ways 算奖和消除补牌辅助逻辑。
"""

import random
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SlotGameConfig:
    """从 game_config.conf 中读取出来的基础数学配置。"""

    project_dir: Path
    version: int
    col_count: int
    row_count: int
    item_count: int
    prize_rate: int
    use_wilds: list[int]
    base_nums: list[int]
    item_prizes: list[list[int]]
    line_mode: int
    line_rules: list[list[tuple[int, int]]]
    grid_disables: list[int]
    grid_disables_free: list[int]
    wild_id: int = 1


class SlotsGame:
    """通用 Slots 基础逻辑类。

    负责：
    1. 读取主题项目配置；
    2. 按 reel_config 生成牌面；
    3. 为消除玩法提供“从当前停轴上方继续取符号”的能力。

    具体算奖逻辑由 WaysGame、LinesGame、CountGame 等玩法类实现。
    """

    BET_UNIT = 10000
    DEFAULT_GAME_CONFIG_FILE = "game_config.conf"
    DEFAULT_REEL_CONFIG_DIR = "reel_config"
    SPIN_TYPES = ("normal", "special", "fix", "zero")

    # 配置文件解析结果会被缓存，避免大量模拟时重复读盘。
    _game_config_cache: dict[Path, SlotGameConfig] = {}
    _reel_config_cache: dict[tuple[Path, int, int], dict] = {}

    def __init__(
        self,
        base_bet: int = 10000,
        wild_id: int | None = None,
        project_dir: str | Path | None = None,
        game_config_file: str = DEFAULT_GAME_CONFIG_FILE,
        reel_config_dir: str = DEFAULT_REEL_CONFIG_DIR,
        reel_file_template: str | None = None,
    ):
        # project_dir 可以显式传入；不传时会尝试自动查找当前目录下唯一的项目。
        self.base_bet = base_bet
        self.project_dir = self._resolve_project_dir(project_dir, game_config_file)
        self.config = self._load_game_config(self.project_dir / game_config_file)
        self.reel_config_dir = self.project_dir / reel_config_dir
        self.reel_file_template = reel_file_template
        self.wild_id = self.config.wild_id if wild_id is None else wild_id
        self.last_win_items: list[dict] = []
        self.last_win_positions: list[tuple[int, int]] = []
        self.last_spin_info: dict = {}
        self.last_spin_state: dict = {}

    def spin(
        self,
        index: int,
        general_index: int,
        row: int,
        col: int,
        reel_config_dir: str | Path | None = None,
        reel_file_template: str | None = None,
    ) -> list[list[int]]:
        """按指定 reel_config 随机生成一个牌面。

        index 对应 reel_config 文件名末尾的数字；
        general_index 对应配置里的 GENERAL_1、GENERAL_2；
        reel_config_dir 不传时使用普通盘 reel_config，也可以传入 free_reel_config 等其他轴目录；
        返回值按列组织，即 board[col][row]。
        """

        if row <= 0 or col <= 0:
            raise ValueError("row and col must be positive")

        current_reel_config_dir = self._resolve_reel_config_dir(reel_config_dir)
        reel_config = self._load_reel_config(
            index,
            general_index,
            reel_config_dir=current_reel_config_dir,
            reel_file_template=reel_file_template,
        )
        reel_config_path = Path(reel_config["reel_config_path"])
        # BASE_RATE 的顺序是：正常盘、特殊盘、固定盘、0 几率盘。
        spin_type = self._choose_spin_type(reel_config["base_rate"])

        if spin_type == "normal":
            board_cols, spin_state = self._spin_from_rolls(reel_config["normal_rolls"], row, col)
        elif spin_type == "special":
            board_cols, spin_state = self._spin_from_rolls(reel_config["special_rolls"], row, col)
        elif spin_type == "fix":
            result = self._choose_result(reel_config["fix_results"], "FIX_RESULT")
            board_cols = self._split_result(result, row, col)
            spin_state = self._build_result_spin_state(board_cols, row, col, spin_type)
        elif spin_type == "zero":
            result = self._choose_result(reel_config["zero_results"], "ZERO_RESULT")
            board_cols = self._split_result(result, row, col)
            spin_state = self._build_result_spin_state(board_cols, row, col, spin_type)
        else:
            raise RuntimeError(f"unknown spin type: {spin_type}")

        # last_spin_state 用于消除玩法：后续补牌必须从这次停轴的上方继续取。
        self.last_spin_state = spin_state
        self.last_spin_info = {
            "project_dir": str(self.project_dir),
            "reel_config_dir": str(current_reel_config_dir),
            "reel_config_file": reel_config_path.name,
            "reel_config_index_fallback": not self._matches_reel_index(reel_config_path, index),
            "index": index,
            "requested_general_index": reel_config.get("requested_general_index", general_index),
            "general_index": reel_config.get("general_index", general_index),
            "general_index_fallback": reel_config.get("general_index_fallback", False),
            "spin_type": spin_type,
            "source_type": spin_state["source_type"],
            "top_indexes": spin_state["top_indexes"][:],
            "row": row,
            "col": col,
        }
        return board_cols

    @classmethod
    def _resolve_project_dir(cls, project_dir: str | Path | None, game_config_file: str) -> Path:
        """定位主题项目目录。"""

        base_dir = Path(__file__).resolve().parent
        if project_dir is not None:
            path = Path(project_dir)
            if not path.is_absolute():
                path = base_dir / path
            return path.resolve()

        direct_candidates = [base_dir, Path.cwd()]
        for candidate in direct_candidates:
            if (candidate / game_config_file).exists():
                return candidate.resolve()

        child_candidates = []
        for root in direct_candidates:
            if not root.exists():
                continue
            child_candidates.extend(
                child for child in root.iterdir() if child.is_dir() and (child / game_config_file).exists()
            )

        unique_candidates = sorted({candidate.resolve() for candidate in child_candidates})
        if len(unique_candidates) == 1:
            return unique_candidates[0]

        if not unique_candidates:
            raise FileNotFoundError(
                "game_config.conf not found. Pass project_dir, for example SlotsGame(project_dir='mahj3')."
            )
        raise ValueError("multiple project folders found. Pass project_dir explicitly.")

    @classmethod
    def _load_game_config(cls, path: Path) -> SlotGameConfig:
        """读取并缓存 game_config.conf。"""

        path = path.resolve()
        if path in cls._game_config_cache:
            return cls._game_config_cache[path]
        if not path.exists():
            raise FileNotFoundError(f"game config not found: {path}")

        parser = cls._read_config_file(path)
        if not parser.has_section("MAIN"):
            raise ValueError(f"{path.name} has no [MAIN] section")

        main = parser["MAIN"]
        item_count = int(main["ITEM_COUNT"])
        col_count = int(main["COL_COUNT"])
        row_count = int(main["ROW_COUNT"])
        wild_ids = cls._parse_int_list(main.get("WILD_ID", "1"))
        config = SlotGameConfig(
            project_dir=path.parent,
            version=int(main.get("VERSION", "0")),
            col_count=col_count,
            row_count=row_count,
            item_count=item_count,
            prize_rate=int(main.get("PRIZE_RATE", "1")),
            use_wilds=cls._parse_int_list(main.get("USE_WILDS", "")),
            base_nums=cls._parse_int_list(main.get("BASE_NUMS", "")),
            item_prizes=[
                cls._parse_int_list(main.get(f"ITEM_PRIZES_{item_id}", "0,0,0,0,0"))
                for item_id in range(item_count)
            ],
            line_mode=int(main.get("LINE_MODE", "1")),
            line_rules=cls._parse_line_rules(main, col_count=col_count, row_count=row_count),
            grid_disables=cls._parse_int_list(main.get("GRID_DISABLES", "")),
            grid_disables_free=cls._parse_int_list(main.get("GRID_DISABLES_FREE", "")),
            wild_id=wild_ids[0] if wild_ids else 1,
        )
        cls._game_config_cache[path] = config
        return config

    def _load_reel_config(
        self,
        index: int,
        general_index: int,
        reel_config_dir: str | Path | None = None,
        reel_file_template: str | None = None,
    ) -> dict:
        """读取并缓存指定 index/general 的 reel 配置。"""

        path = self._find_reel_config_path(
            index,
            reel_config_dir=reel_config_dir,
            reel_file_template=reel_file_template,
        )
        cache_key = (path.resolve(), general_index, self.config.col_count)
        if cache_key in self._reel_config_cache:
            return self._reel_config_cache[cache_key]

        parser = self._read_config_file(path)

        requested_section_name = f"GENERAL_{general_index}"
        section_name = requested_section_name
        actual_general_index = general_index
        if not parser.has_section(section_name):
            section_name = "GENERAL_1"
            actual_general_index = 1
            if not parser.has_section(section_name):
                raise ValueError(f"{path.name} has no section [{requested_section_name}] or [GENERAL_1]")

        section = parser[section_name]
        config = {
            "reel_config_path": str(path),
            "requested_general_index": general_index,
            "general_index": actual_general_index,
            "general_index_fallback": actual_general_index != general_index,
            "base_rate": self._parse_int_list(section.get("BASE_RATE", "")),
            "normal_rolls": self._collect_rolls(section, "NORMAL_ROLL_", col_count=self.config.col_count),
            "special_rolls": self._collect_rolls(section, "SP_ROLL_", col_count=self.config.col_count),
            "fix_results": self._collect_numbered_values(section, "FIX_RESULT_"),
            "zero_results": self._collect_numbered_values(section, "ZERO_RESULT_"),
        }
        if len(config["base_rate"]) < len(self.SPIN_TYPES):
            raise ValueError(f"{path.name} [{section_name}] BASE_RATE must contain 4 values")

        self._reel_config_cache[cache_key] = config
        return config

    def _find_reel_config_path(
        self,
        index: int,
        reel_config_dir: str | Path | None = None,
        reel_file_template: str | None = None,
    ) -> Path:
        """根据 index 自动匹配 reel_config 下对应的 .conf 文件。"""

        target_dir = self._resolve_reel_config_dir(reel_config_dir)
        target_template = self.reel_file_template if reel_file_template is None else reel_file_template

        if not target_dir.exists():
            raise FileNotFoundError(f"reel config dir not found: {target_dir}")

        if target_template:
            path = target_dir / target_template.format(index=index)
            if path.exists():
                return path

            fallback_path = target_dir / target_template.format(index=0)
            if index != 0 and fallback_path.exists():
                return fallback_path

            raise FileNotFoundError(f"reel config not found: {path}; fallback index 0 not found")

        matches = sorted(
            path for path in target_dir.glob("*.conf") if self._matches_reel_index(path, index)
        )
        if len(matches) == 1:
            return matches[0]
        if not matches:
            fallback_matches = sorted(
                path for path in target_dir.glob("*.conf") if self._matches_reel_index(path, 0)
            )
            if index != 0 and len(fallback_matches) == 1:
                return fallback_matches[0]
            if index != 0 and len(fallback_matches) > 1:
                names = ", ".join(path.name for path in fallback_matches)
                raise ValueError(f"multiple fallback reel configs match index 0: {names}")
            raise FileNotFoundError(f"no reel config ending with _{index}.conf or _0.conf in {target_dir}")
        names = ", ".join(path.name for path in matches)
        raise ValueError(f"multiple reel configs match index {index}: {names}")

    @staticmethod
    def _matches_reel_index(path: Path, index: int) -> bool:
        """判断配置文件名是否匹配指定 index。"""

        return path.stem == str(index) or path.stem.endswith(f"_{index}")

    def _resolve_reel_config_dir(self, reel_config_dir: str | Path | None = None) -> Path:
        """把 reel 配置目录解析成绝对路径；相对路径默认基于项目目录。"""

        if reel_config_dir is None:
            return self.reel_config_dir.resolve()

        path = Path(reel_config_dir)
        if not path.is_absolute():
            path = self.project_dir / path
        return path.resolve()

    @classmethod
    def _read_config_file(cls, path: Path) -> ConfigParser:
        """读取 ini 风格配置，并忽略三引号备注块。"""

        parser = ConfigParser(inline_comment_prefixes=("#", ";"))
        parser.optionxform = str
        text = path.read_text(encoding="utf-8-sig")
        parser.read_string(cls._strip_triple_quoted_blocks(text), source=str(path))
        return parser

    @staticmethod
    def _strip_triple_quoted_blocks(text: str) -> str:
        """过滤轴文件中用三引号包裹的统计备注，避免被 ConfigParser 当成 section。"""

        kept_lines = []
        in_quote_block = False
        for line in text.splitlines(keepends=True):
            if line.strip() == '"""':
                in_quote_block = not in_quote_block
                continue
            if not in_quote_block:
                kept_lines.append(line)
        return "".join(kept_lines)

    @classmethod
    def _choose_spin_type(cls, base_rate: list[int]) -> str:
        """按 BASE_RATE 权重选择本次使用哪类盘。"""

        rates = base_rate[: len(cls.SPIN_TYPES)]
        total_rate = sum(rates)
        if total_rate <= 0:
            raise ValueError("BASE_RATE total must be greater than 0")

        hit = random.randrange(total_rate)
        running_rate = 0
        for spin_type, rate in zip(cls.SPIN_TYPES, rates):
            running_rate += rate
            if hit < running_rate:
                return spin_type
        return cls.SPIN_TYPES[-1]

    @staticmethod
    def _spin_from_rolls(rolls: list[list[int]], row: int, col: int):
        """从正常盘/特殊盘 reel 中截取指定大小的牌面。"""

        if len(rolls) < col:
            raise ValueError(f"requested {col} columns but only {len(rolls)} rolls are configured")

        board_cols = []
        top_indexes = []
        for roll in rolls[:col]:
            if not roll:
                raise ValueError("roll config cannot be empty")

            start_index = random.randrange(len(roll))
            top_indexes.append(start_index)
            board_cols.append([roll[(start_index + offset) % len(roll)] for offset in range(row)])
        spin_state = {
            "source_type": "rolls",
            "columns": [list(roll) for roll in rolls[:col]],
            "top_indexes": top_indexes,
            "row": row,
            "col": col,
        }
        return board_cols, spin_state

    @staticmethod
    def _build_result_spin_state(board_cols: list[list[int]], row: int, col: int, spin_type: str) -> dict:
        """固定盘/0 几率盘没有真实 reel，因此用结果列本身作为循环补牌来源。"""

        return {
            "source_type": f"{spin_type}_result_cycle",
            "columns": [list(board_cols[col_index]) for col_index in range(col)],
            "top_indexes": [0 for _ in range(col)],
            "row": row,
            "col": col,
        }

    @staticmethod
    def clone_spin_state(spin_state: dict) -> dict:
        """复制停轴状态，避免消除流程修改原始 spin 记录。"""

        cloned_state = {
            "source_type": spin_state["source_type"],
            "columns": [list(col_items) for col_items in spin_state["columns"]],
            "top_indexes": list(spin_state["top_indexes"]),
            "row": spin_state["row"],
            "col": spin_state["col"],
        }
        for key, value in spin_state.items():
            if key in cloned_state or key == "columns" or key == "top_indexes":
                continue
            if isinstance(value, list):
                cloned_state[key] = list(value)
            else:
                cloned_state[key] = value
        return cloned_state

    @staticmethod
    def take_symbols_above(spin_state: dict, col_index: int, count: int) -> list[int]:
        """从指定列当前窗口上方继续取 count 个 symbol。"""

        if count <= 0:
            return []

        source = spin_state["columns"][col_index]
        if not source:
            raise ValueError("spin state source column cannot be empty")

        top_index = spin_state["top_indexes"][col_index]
        new_top_index = (top_index - count) % len(source)
        symbols = [source[(new_top_index + offset) % len(source)] for offset in range(count)]
        spin_state["top_indexes"][col_index] = new_top_index
        return symbols

    def _split_result(self, result: list[int], row: int, col: int) -> list[list[int]]:
        """把固定结果或 0 几率结果拆成 [列][行] 的牌面。"""

        need_count = row * col
        if len(result) < need_count:
            raise ValueError(f"result has {len(result)} items but {need_count} are required")

        source_rows = self.config.row_count
        source_cols = self.config.col_count
        source_count = source_rows * source_cols
        if row <= source_rows and col <= source_cols and len(result) >= source_count:
            return [result[src_col * source_rows : src_col * source_rows + row] for src_col in range(col)]

        return [result[src_col * row : (src_col + 1) * row] for src_col in range(col)]

    @staticmethod
    def _choose_result(results: list[list[int]], result_name: str) -> list[int]:
        """从 FIX_RESULT 或 ZERO_RESULT 中随机取一条。"""

        if not results:
            raise ValueError(f"{result_name} is empty")
        return random.choice(results)

    @classmethod
    def _collect_rolls(cls, section, prefix: str, col_count: int) -> list[list[int]]:
        """收集 NORMAL_ROLL_n 或 SP_ROLL_n。"""

        rolls = []
        for col_index in range(1, col_count + 1):
            key = f"{prefix}{col_index}"
            if key not in section:
                break
            rolls.append(cls._parse_int_list(section[key]))
        return rolls

    @classmethod
    def _collect_numbered_values(cls, section, prefix: str) -> list[list[int]]:
        """按编号顺序收集 FIX_RESULT_n / ZERO_RESULT_n。"""

        values = []
        for key in section:
            if not key.startswith(prefix):
                continue

            suffix = key[len(prefix) :]
            if not suffix.isdigit():
                continue
            values.append((int(suffix), cls._parse_int_list(section[key])))

        values.sort(key=lambda item: item[0])
        return [value for _, value in values]

    @staticmethod
    def _parse_int_list(value: str) -> list[int]:
        """把逗号分隔的配置值转成整数列表。"""

        return [int(item.strip()) for item in value.split(",") if item.strip()]

    @classmethod
    def _parse_line_rules(cls, section, col_count: int, row_count: int) -> list[list[tuple[int, int]]]:
        """读取固定线规则，并把配置里的格子编号转成 (col, row) 坐标。"""

        raw_rules = cls._collect_line_rule_values(section)
        if not raw_rules:
            return []

        flat_count = col_count * row_count
        zero_based = any(index == 0 for rule in raw_rules for index in rule)
        line_rules = []
        for rule_index, rule in enumerate(raw_rules):
            if len(rule) != col_count:
                raise ValueError(f"LINE_RULES_{rule_index} length must be COL_COUNT={col_count}")

            positions = []
            for item_index in rule:
                flat_index = item_index if zero_based else item_index - 1
                if flat_index < 0 or flat_index >= flat_count:
                    raise ValueError(
                        f"LINE_RULES_{rule_index} contains out-of-range cell index: {item_index}"
                    )
                positions.append((flat_index // row_count, flat_index % row_count))
            line_rules.append(positions)
        return line_rules

    @classmethod
    def _collect_line_rule_values(cls, section) -> list[list[int]]:
        """按编号顺序收集 LINE_RULES_n / Line_Rules_n。"""

        rule_count = int(section.get("RULE_COUNT", "0") or 0)
        prefixes = ("LINE_RULES_", "Line_Rules_", "LINE_RULE_", "Line_Rule_")
        if rule_count > 0:
            rules = []
            for rule_index in range(rule_count):
                key = cls._find_first_section_key(section, [f"{prefix}{rule_index}" for prefix in prefixes])
                if key is None:
                    raise ValueError(f"missing LINE_RULES_{rule_index}")
                rules.append(cls._parse_int_list(section[key]))
            return rules

        values = []
        for key in section:
            for prefix in prefixes:
                if not key.startswith(prefix):
                    continue

                suffix = key[len(prefix) :]
                if suffix.isdigit():
                    values.append((int(suffix), cls._parse_int_list(section[key])))
                break

        values.sort(key=lambda item: item[0])
        return [value for _, value in values]

    @staticmethod
    def _find_first_section_key(section, keys: list[str]) -> str | None:
        """返回 section 中第一个存在的 key。"""

        for key in keys:
            if key in section:
                return key
        return None

    def _count_col_matches(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        col: int,
        item_id: int,
        row_count: int,
    ) -> int:
        """统计某列中指定 symbol 的命中数量。"""

        return len(self._get_col_match_positions(board_cols, grid_disables, col, item_id, row_count))

    def _get_col_match_positions(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        col: int,
        item_id: int,
        row_count: int,
    ) -> list[tuple[int, int]]:
        """返回某列中指定 symbol 的命中坐标，wild 按 USE_WILDS 参与替代。"""

        positions = []
        use_wild = self._get_or_default(self.config.use_wilds, item_id, 0) == 1
        for row in range(row_count):
            if col >= len(board_cols) or row >= len(board_cols[col]):
                continue
            if self._is_disabled(grid_disables, col, row, row_count):
                continue

            cell_item = board_cols[col][row]
            if cell_item == item_id or (use_wild and cell_item == self.wild_id):
                positions.append((col, row))
        return positions

    def _normalize_item_list(self, item_list, row: int | None = None, col: int | None = None):
        """把外部传入的牌面统一转换成 [列][行]。"""

        config = self.config
        if self._is_2d(item_list):
            return self._normalize_2d_item_list(item_list, row=row, col=col)

        flat_items = list(item_list)
        if row is not None or col is not None:
            if row is None or col is None:
                raise ValueError("row and col must be passed together for flat item_list")
            expected_count = row * col
            if len(flat_items) != expected_count:
                raise ValueError(f"item_list length must be {expected_count}")
            return self._split_flat_items(flat_items, row, col), col, row

        full_count = config.col_count * config.row_count
        if len(flat_items) == full_count:
            return self._split_flat_items(flat_items, config.row_count, config.col_count), config.col_count, config.row_count

        enabled_count = sum(1 for disabled in config.grid_disables if disabled == 0)
        if len(flat_items) != enabled_count:
            raise ValueError(f"item_list length must be {full_count} or {enabled_count}")

        board_cols = [[] for _ in range(config.col_count)]
        item_index = 0
        for col_index in range(config.col_count):
            for row_index in range(config.row_count):
                if self._is_disabled(config.grid_disables, col_index, row_index, config.row_count):
                    continue
                board_cols[col_index].append(flat_items[item_index])
                item_index += 1
        return board_cols, config.col_count, self._get_board_row_count(board_cols)

    def _normalize_2d_item_list(self, item_list, row: int | None = None, col: int | None = None):
        """处理二维牌面，兼容 [列][行] 和 [行][列] 两种形状。"""

        config = self.config
        rows = [list(items) for items in item_list]
        if not rows:
            raise ValueError("item_list cannot be empty")

        if row is not None or col is not None:
            if row is None or col is None:
                raise ValueError("row and col must be passed together for 2d item_list")
            if len(rows) == col and all(len(col_items) <= row for col_items in rows):
                return rows, col, row
            if len(rows) == col and all(len(col_items) == row for col_items in rows):
                return rows, col, row
            if len(rows) == row and all(len(row_items) == col for row_items in rows):
                return [[rows[row_index][col_index] for row_index in range(row)] for col_index in range(col)], col, row
            raise ValueError("2d item_list shape does not match row and col")

        if len(rows) == config.col_count:
            row_count = self._get_board_row_count(rows)
            return rows, config.col_count, row_count

        if len(rows) == config.row_count:
            col_count = len(rows[0])
            if not all(len(row_items) == col_count for row_items in rows):
                raise ValueError("2d item_list rows must have the same length")
            return (
                [[rows[row_index][col_index] for row_index in range(config.row_count)] for col_index in range(col_count)],
                col_count,
                config.row_count,
            )

        row_count = len(rows[0])
        if not all(len(col_items) == row_count for col_items in rows):
            raise ValueError("2d item_list must be rectangular")
        return rows, len(rows), row_count

    @staticmethod
    def _get_board_row_count(board_cols: list[list[int | None]]) -> int:
        """返回变长列牌面的最大列高。"""

        return max((len(col_items) for col_items in board_cols), default=0)

    def _get_grid_disables(self, free_game: bool, col_count: int, row_count: int) -> list[int]:
        """获取当前牌面需要使用的无效格配置。"""

        config = self.config
        if col_count != config.col_count or row_count != config.row_count:
            return [0] * (col_count * row_count)

        grid_disables = config.grid_disables_free if free_game else config.grid_disables
        if not grid_disables:
            return [0] * (col_count * row_count)
        return grid_disables

    @staticmethod
    def _split_flat_items(flat_items: list[int], row: int, col: int) -> list[list[int]]:
        """把一维列表按列优先拆成二维牌面。"""

        return [flat_items[col_index * row : (col_index + 1) * row] for col_index in range(col)]

    @staticmethod
    def _is_2d(item_list) -> bool:
        """判断输入是否是二维列表/元组。"""

        return bool(item_list) and all(isinstance(item, (list, tuple)) for item in item_list)

    @staticmethod
    def _is_disabled(grid_disables: list[int], col: int, row: int, row_count: int) -> bool:
        """判断指定格子是否是配置中的无效格。"""

        index = col * row_count + row
        return index < len(grid_disables) and grid_disables[index] == 1

    @staticmethod
    def _get_or_default(values, index: int, default: int) -> int:
        """安全读取列表值，越界时返回默认值。"""

        if 0 <= index < len(values):
            return values[index]
        return default


class WaysGame(SlotsGame):
    """通用 ways 玩法计算类。"""

    def cal_item_list(
        self,
        item_list,
        return_detail: bool = False,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ):
        """计算 ways 牌面的总赢钱。

        item_list 支持：
        1. 一维列表，按列优先排列；
        2. 只传有效格子的一维列表；
        3. 二维列表，支持 [列][行] 或 [行][列]。
        """

        config = self.config
        if config.line_mode not in (1, 2, 3):
            raise NotImplementedError("WaysGame only supports LINE_MODE=1, 2, or 3")

        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)

        total_win = 0
        win_items = []
        # 对每个 symbol 单独计算 ways；中奖明细里会带出命中坐标。
        for item_id in range(config.item_count):
            item_wins = self._cal_one_item(board_cols, grid_disables, item_id, col_count, row_count)
            for item_win in item_wins:
                total_win += item_win["win"]
                win_items.append(item_win)

        win_positions = sorted({position for item in win_items for position in item["positions"]})
        self.last_win_items = win_items
        self.last_win_positions = win_positions
        if return_detail:
            return {"total_win": total_win, "items": win_items, "win_positions": win_positions}
        return total_win

    def _cal_one_item(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        item_id: int,
        col_count: int,
        row_count: int,
    ):
        """计算单个 symbol 在当前牌面上的 ways 中奖信息。"""

        config = self.config
        if config.line_mode == 1:
            return self._cal_one_item_direction(
                board_cols,
                grid_disables,
                item_id,
                range(col_count),
                row_count,
                direction="left",
            )
        if config.line_mode == 2:
            return self._cal_one_item_direction(
                board_cols,
                grid_disables,
                item_id,
                range(col_count - 1, -1, -1),
                row_count,
                direction="right",
            )

        wins = []
        wins.extend(
            self._cal_one_item_direction(
                board_cols,
                grid_disables,
                item_id,
                range(col_count),
                row_count,
                direction="left",
            )
        )
        wins.extend(
            self._cal_one_item_direction(
                board_cols,
                grid_disables,
                item_id,
                range(col_count - 1, -1, -1),
                row_count,
                direction="right",
            )
        )
        return wins

    def _cal_one_item_direction(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        item_id: int,
        col_indexes,
        row_count: int,
        direction: str,
    ) -> list[dict]:
        """计算单个 symbol 沿指定方向连续命中的 ways 中奖信息。"""

        config = self.config
        base_num = self._get_or_default(config.base_nums, item_id, 0)
        if base_num <= 0:
            return []

        counts = []
        positions_by_col = []
        hit_cols = []
        # 从指定起点开始连续命中，一旦某列没有命中就停止。
        for col in col_indexes:
            match_positions = self._get_col_match_positions(board_cols, grid_disables, col, item_id, row_count)
            if not match_positions:
                break
            counts.append(len(match_positions))
            positions_by_col.append(match_positions)
            hit_cols.append(col)

        hit_num = len(counts)
        if hit_num < base_num:
            return []

        prize = self._get_or_default(config.item_prizes[item_id], hit_num - 1, 0)
        if prize <= 0:
            return []

        ways = 1
        for count in counts:
            ways *= count

        # 配置中的奖值以 BET_UNIT 为倍率基准，最终再按 PRIZE_RATE 修正。
        win = self.base_bet * prize * ways // self.BET_UNIT // max(config.prize_rate, 1)
        positions = [position for col_positions in positions_by_col for position in col_positions]
        return [
            {
                "item_id": item_id,
                "hit_num": hit_num,
                "counts": counts,
                "positions_by_col": positions_by_col,
                "positions": positions,
                "ways": ways,
                "prize": prize,
                "win": win,
                "direction": direction,
                "columns": hit_cols,
            }
        ]


class LinesGame(SlotsGame):
    """通用固定线玩法计算类。"""

    def cal_item_list(
        self,
        item_list,
        return_detail: bool = False,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ):
        """按 game_config.conf 中的 LINE_RULES_n 计算固定线赢钱。"""

        config = self.config
        if config.line_mode not in (1, 2, 3):
            raise NotImplementedError("LinesGame only supports LINE_MODE=1, 2, or 3")
        if not config.line_rules:
            raise ValueError("LinesGame requires LINE_RULES_n in game_config.conf")

        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        if col_count != config.col_count or row_count != config.row_count:
            raise ValueError("LinesGame board size must match COL_COUNT and ROW_COUNT")

        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        total_win = 0
        win_items = []
        for line_index, line_rule in enumerate(config.line_rules):
            for direction, ordered_positions in self._iter_line_directions(line_rule):
                line_win = self._cal_one_line_direction(
                    board_cols,
                    grid_disables,
                    line_index=line_index,
                    ordered_positions=ordered_positions,
                    row_count=row_count,
                    direction=direction,
                )
                if line_win is None:
                    continue
                total_win += line_win["win"]
                win_items.append(line_win)

        win_positions = sorted({position for item in win_items for position in item["positions"]})
        self.last_win_items = win_items
        self.last_win_positions = win_positions
        if return_detail:
            return {"total_win": total_win, "items": win_items, "win_positions": win_positions}
        return total_win

    def _iter_line_directions(self, line_rule: list[tuple[int, int]]):
        """按 LINE_MODE 返回当前线需要计算的方向。"""

        line_mode = self.config.line_mode
        if line_mode == 1:
            yield "left", line_rule
        elif line_mode == 2:
            yield "right", list(reversed(line_rule))
        else:
            yield "left", line_rule
            yield "right", list(reversed(line_rule))

    def _cal_one_line_direction(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        line_index: int,
        ordered_positions: list[tuple[int, int]],
        row_count: int,
        direction: str,
    ) -> dict | None:
        """计算一条固定线在指定方向上的中奖。"""

        item_id = self._get_line_target_item(board_cols, grid_disables, ordered_positions, row_count)
        if item_id is None:
            return None

        config = self.config
        base_num = self._get_or_default(config.base_nums, item_id, 0)
        if base_num <= 0:
            return None

        use_wild = self._get_or_default(config.use_wilds, item_id, 0) == 1
        hit_positions = []
        hit_symbols = []
        for col, row in ordered_positions:
            cell_item = self._get_line_cell(board_cols, grid_disables, col, row, row_count)
            if cell_item is None:
                break
            if cell_item == item_id or (use_wild and cell_item == self.wild_id):
                hit_positions.append((col, row))
                hit_symbols.append(cell_item)
                continue
            break

        hit_num = len(hit_positions)
        if hit_num < base_num:
            return None

        prize = self._get_or_default(config.item_prizes[item_id], hit_num - 1, 0)
        if prize <= 0:
            return None

        win = self.base_bet * prize // self.BET_UNIT // max(config.prize_rate, 1)
        return {
            "line_index": line_index,
            "item_id": item_id,
            "hit_num": hit_num,
            "positions": hit_positions,
            "symbols": hit_symbols,
            "prize": prize,
            "win": win,
            "direction": direction,
        }

    def _get_line_target_item(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        ordered_positions: list[tuple[int, int]],
        row_count: int,
    ) -> int | None:
        """确定一条线当前方向的目标 symbol；起始 wild 使用后续首个非 wild。"""

        has_wild = False
        for col, row in ordered_positions:
            cell_item = self._get_line_cell(board_cols, grid_disables, col, row, row_count)
            if cell_item is None:
                return None
            if cell_item == self.wild_id:
                has_wild = True
                continue
            return cell_item

        return self.wild_id if has_wild else None

    def _get_line_cell(
        self,
        board_cols: list[list[int | None]],
        grid_disables: list[int],
        col: int,
        row: int,
        row_count: int,
    ) -> int | None:
        """读取固定线上的一个格子；无效格或越界返回 None。"""

        if self._is_disabled(grid_disables, col, row, row_count):
            return None
        if col < 0 or col >= len(board_cols):
            return None
        if row < 0 or row >= len(board_cols[col]):
            return None
        return board_cols[col][row]


class CountGame(SlotsGame):
    """通用按 symbol 数量算奖的玩法计算类。"""

    def cal_item_list(
        self,
        item_list,
        return_detail: bool = False,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ):
        """按牌面上每种 symbol 的数量计算赢钱。"""

        config = self.config
        if config.line_mode != 4:
            raise NotImplementedError("CountGame only supports LINE_MODE=4")

        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        positions_by_item: dict[int, list[tuple[int, int]]] = {
            item_id: [] for item_id in range(config.item_count)
        }

        for col_index in range(col_count):
            for row_index in range(min(row_count, len(board_cols[col_index]))):
                if self._is_disabled(grid_disables, col_index, row_index, row_count):
                    continue

                item_id = board_cols[col_index][row_index]
                if item_id is None or item_id < 0 or item_id >= config.item_count:
                    continue
                positions_by_item[item_id].append((col_index, row_index))

        total_win = 0
        win_items = []
        for item_id, positions in positions_by_item.items():
            count = len(positions)
            base_num = self._get_or_default(config.base_nums, item_id, 0)
            if count < base_num or base_num <= 0:
                continue

            prize = self._get_or_default(config.item_prizes[item_id], count - 1, 0)
            if prize <= 0:
                continue

            win = self.base_bet * prize // self.BET_UNIT // max(config.prize_rate, 1)
            win_item = {
                "item_id": item_id,
                "count": count,
                "hit_num": count,
                "positions": positions,
                "prize": prize,
                "win": win,
            }
            total_win += win
            win_items.append(win_item)

        win_positions = sorted({position for item in win_items for position in item["positions"]})
        self.last_win_items = win_items
        self.last_win_positions = win_positions
        if return_detail:
            return {"total_win": total_win, "items": win_items, "win_positions": win_positions}
        return total_win
