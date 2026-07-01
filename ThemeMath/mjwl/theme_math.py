"""当前主题数学入口。

ThemeMath 继承通用 WaysGame，负责串起本主题自己的流程：
普通 spin、金色 symbol、ways 算奖、消除补牌、free 选择和 free spin。
"""

import ast
from pathlib import Path
import random
import sys
from configparser import ConfigParser


# 直接运行当前主题 simulation.py 时，Python 默认只把主题目录加到 sys.path。
# 这里把项目根目录加入搜索路径，才能导入上一层的 slots_math.py。
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import WaysGame


class ThemeMath(WaysGame):
    """当前主题的数学封装。"""

    # 配置里的 GoldSymbolWeight 对应第 2、3、4 列，内部下标是 1、2、3。
    GOLD_COLUMNS = (1, 2, 3)
    GOLD_BASE = 10000
    GOLD_SYMBOL_OFFSET = 100
    SCATTER_ID = 0
    FREE_BASE_SCATTER_COUNT = 3
    FREE_REEL_CONFIG_DIR = "free_reel_config"
    RANDOM_CHOOSE_INDEX = 5

    def __init__(self, base_bet: int = 10000, **kwargs):
        # 默认项目目录就是当前 theme_math.py 所在的主题文件夹。
        project_dir = kwargs.pop("project_dir", Path(__file__).resolve().parent)
        game_config_file = kwargs.get("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        self.game_server_config_file = kwargs.pop("game_server_config_file", "game_server.conf")
        super().__init__(base_bet=base_bet, project_dir=project_dir, **kwargs)
        self.game_config_file = game_config_file
        self.game_server_config = self._load_game_server_config(self.project_dir / self.game_server_config_file)
        self.win_box_level_up_rates, self.win_box_level_multipliers = self.load_win_box_level_config()
        self.base_win_multipliers = self.win_box_level_multipliers[0]
        (
            self.free_count_list,
            self.free_multi_list,
            self.free_random_count_weights,
            self.free_random_multi_weights,
        ) = self.load_free_choice_config()
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

    def ng_spin(
        self,
        index: int,
        general_index: int,
        choose_index: int = 1,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        """普通游戏 spin，并执行完整消除流程。"""

        return self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            choose_index=choose_index,
            reel_config_dir=None,
            free_game=False,
            free_choice=None,
            return_detail=return_detail,
            max_cascades=max_cascades,
        )

    def fg_spin(
        self,
        index: int,
        general_index: int | None = None,
        choose_index: int = 1,
        free_choice: dict | None = None,
        free_general_index: int | None = None,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        """免费游戏 spin，读取 free_reel_config 并执行完整消除算奖流程。"""

        active_free_choice = self.normalize_free_choice(free_choice) if free_choice is not None else None
        if active_free_choice is None:
            active_free_choice = self.get_free_choice(choose_index)
        if free_general_index is None:
            free_general_index = active_free_choice["free_index"] if general_index is None else general_index

        result = self._spin_and_evaluate(
            index=index,
            general_index=free_general_index,
            choose_index=choose_index,
            reel_config_dir=self.FREE_REEL_CONFIG_DIR,
            free_game=True,
            free_choice=active_free_choice,
            return_detail=return_detail,
            max_cascades=max_cascades,
        )
        self.last_fg_result = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        choose_index: int,
        reel_config_dir,
        free_game: bool,
        free_choice: dict | None,
        return_detail: bool,
        max_cascades: int,
    ) -> dict:
        """按指定轴目录 spin，并套用主题的金色 symbol 和消除算奖。"""

        source_row = self.config.row_count
        col = self.config.col_count

        game_server_section = self.get_game_server_section(index)
        max_round_num = self.get_max_round_num(free_game=free_game)
        active_free_choice = self.normalize_free_choice(free_choice) if free_game else None
        if free_game and active_free_choice is None:
            active_free_choice = self.get_free_choice(choose_index)
        if free_game:
            win_multiplier_index = active_free_choice.get("free_index", 1) if active_free_choice else 1
            win_multipliers = list(active_free_choice["multipliers"]) if active_free_choice else list(self.free_multi_list[0])
            gold_weight_index = general_index
        else:
            win_multiplier_index, win_multipliers = self.choose_base_win_multipliers()
            gold_weight_index = None
        use_level_up_gold_weights = not free_game and win_multiplier_index > 1
        if use_level_up_gold_weights:
            gold_weights = self.get_level_up_gold_symbol_weights(game_server_section)
        else:
            gold_weights = self.get_gold_symbol_weights(
                game_server_section,
                free_game=free_game,
                free_general_index=gold_weight_index,
            )

        item_list = self.spin(
            index=index,
            general_index=general_index,
            row=source_row,
            col=col,
            reel_config_dir=reel_config_dir,
        )
        item_list = self.build_effective_board(item_list, free_game=free_game)
        self.align_last_spin_state_to_effective_grid(free_game=free_game)

        row = self._get_board_row_count(item_list)
        col = len(item_list)
        item_list = self.apply_gold_symbols(
            item_list,
            gold_weights=gold_weights,
            row=row,
            col=col,
            free_game=free_game,
        )

        # 保存初始 spin 信息和停轴状态，后续补牌都基于这一次停轴。
        spin_info = self.last_spin_info.copy()
        spin_info["free_game"] = free_game
        spin_info["source_row"] = source_row
        spin_info["row"] = row
        spin_info["col"] = col
        spin_info["col_heights"] = [len(col_items) for col_items in item_list]
        spin_info["choose_index"] = choose_index
        spin_info["win_multiplier_index"] = win_multiplier_index
        spin_info["win_multipliers"] = list(win_multipliers)
        spin_info["gold_weight_type"] = "level_up" if use_level_up_gold_weights else "normal"
        spin_info["gold_weights"] = list(gold_weights)
        spin_state = self.clone_spin_state(self.last_spin_state)
        return self.evaluate_cascades(
            item_list=item_list,
            gold_weights=gold_weights,
            row=row,
            col=col,
            spin_info=spin_info,
            spin_state=spin_state,
            choose_index=choose_index,
            free_choice=active_free_choice,
            return_detail=return_detail,
            max_cascades=max_cascades,
            free_game=free_game,
            max_round_num=max_round_num,
            win_multipliers=win_multipliers,
        )

    def get_free_choice(self, choose_index: int = 1) -> dict:
        """把玩家选择转成 free 次数和 free 消除倍数。"""

        if choose_index == self.RANDOM_CHOOSE_INDEX:
            times_index = self.weighted_random_index(self.free_random_count_weights)
            multiplier_index = self.weighted_random_index(self.free_random_multi_weights)
        elif 1 <= choose_index <= len(self.free_count_list):
            times_index = choose_index - 1
            multiplier_index = choose_index - 1
        else:
            raise ValueError(f"choose_index must be 1-{self.RANDOM_CHOOSE_INDEX}, got {choose_index}")

        return {
            "choose_index": choose_index,
            "times_index": times_index,
            "multiplier_index": multiplier_index,
            "free_index": multiplier_index + 1,
            "free_times": self.free_count_list[times_index],
            "free_count_max": self.free_count_list[times_index],
            "multipliers": list(self.free_multi_list[multiplier_index]),
        }

    def normalize_free_choice(self, free_choice: dict | None) -> dict | None:
        """复制外部传入的 free 选择，避免模拟过程修改原始对象。"""

        if free_choice is None:
            return None
        free_times = int(free_choice.get("free_count_max", free_choice.get("free_times", 0)))
        multipliers = free_choice.get("multipliers", free_choice.get("free_multi_list", []))
        if isinstance(multipliers, str):
            multipliers = self._parse_config_int_list(multipliers, "free_choice multipliers")
        if not multipliers:
            raise ValueError("free_choice multipliers cannot be empty")
        return {
            "choose_index": free_choice.get("choose_index", 1),
            "times_index": free_choice.get("times_index", 0),
            "multiplier_index": free_choice.get("multiplier_index", 0),
            "free_times": free_times,
            "free_count_max": free_times,
            "multipliers": list(multipliers),
            "free_index": int(free_choice.get("free_index", int(free_choice.get("multiplier_index", 0)) + 1)),
        }

    def build_effective_board(self, item_list, free_game: bool = False) -> list[list[int]]:
        """把原始 5x6 牌面按 GRID_DISABLES 裁成真正参与计算的 45554 牌面。"""

        board = self._clone_board(item_list)
        source_row = self.config.row_count
        col = self.config.col_count
        if len(board) != col or any(len(col_items) < source_row for col_items in board):
            return board

        enabled_rows_by_col = self.get_enabled_rows_by_col(free_game=free_game, row=source_row, col=col)
        if all(len(enabled_rows) == source_row for enabled_rows in enabled_rows_by_col):
            return board

        return [
            [board[col_index][row_index] for row_index in enabled_rows_by_col[col_index]]
            for col_index in range(col)
        ]

    def align_last_spin_state_to_effective_grid(self, free_game: bool = False):
        """把停轴顶部调整到有效牌面的顶部，保证补牌从 45554 上方继续落下。"""

        spin_state = self.last_spin_state
        source_row = self.config.row_count
        col = self.config.col_count
        if spin_state.get("row") != source_row or spin_state.get("col") != col:
            return

        enabled_rows_by_col = self.get_enabled_rows_by_col(free_game=free_game, row=source_row, col=col)
        col_heights = [len(enabled_rows) for enabled_rows in enabled_rows_by_col]
        for col_index, enabled_rows in enumerate(enabled_rows_by_col):
            if not enabled_rows:
                continue

            first_enabled_row = enabled_rows[0]
            source_col = spin_state["columns"][col_index]
            if source_col:
                spin_state["top_indexes"][col_index] = (
                    spin_state["top_indexes"][col_index] + first_enabled_row
                ) % len(source_col)

        spin_state["source_row"] = source_row
        spin_state["row"] = max(col_heights, default=0)
        spin_state["col_heights"] = col_heights

    def get_enabled_rows_by_col(
        self,
        free_game: bool = False,
        row: int | None = None,
        col: int | None = None,
    ) -> list[list[int]]:
        """按 GRID_DISABLES 返回每列有效的原始行下标。"""

        row_count = self.config.row_count if row is None else row
        col_count = self.config.col_count if col is None else col
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        return [
            [
                row_index
                for row_index in range(row_count)
                if not self._is_disabled(grid_disables, col_index, row_index, row_count)
            ]
            for col_index in range(col_count)
        ]

    def get_active_rows_for_col(
        self,
        item_list,
        col_index: int,
        row: int,
        col: int,
        free_game: bool = False,
    ) -> list[int]:
        """返回当前牌面某列真正参与计算的行下标。"""

        if col_index >= col or col_index >= len(item_list):
            return []

        grid_disables = self._get_grid_disables(free_game, col, row)
        return [
            row_index
            for row_index in range(min(row, len(item_list[col_index])))
            if not self._is_disabled(grid_disables, col_index, row_index, row)
        ]

    def iter_active_positions(self, item_list, row: int, col: int, free_game: bool = False):
        """遍历当前牌面中真正参与计算的坐标。"""

        for col_index in range(col):
            for row_index in self.get_active_rows_for_col(item_list, col_index, row, col, free_game=free_game):
                yield col_index, row_index

    def evaluate(self, item_list, row, col, return_detail: bool = True, free_game: bool = False):
        """只计算当前牌面这一轮的中奖，不做消除和补牌。"""

        item_list = self.build_effective_board(item_list, free_game=free_game)
        row = self._get_board_row_count(item_list)
        col = len(item_list)
        # 牌面中 100+symbol_id 表示金色 symbol；算奖时先还原为原 symbol。
        evaluate_item_list = self._build_evaluate_board(item_list)
        win_result = self.cal_item_list(
            evaluate_item_list,
            return_detail=True,
            free_game=free_game,
            row=row,
            col=col,
        )

        self.last_ng_result = {
            "item_list": item_list,
            "total_win": win_result["total_win"],
            "win_items": win_result["items"],
            "win_positions": win_result["win_positions"],
            "spin_info": self.last_spin_info,
        }
        return self.last_ng_result

    def evaluate_cascades(
        self,
        item_list,
        gold_weights,
        row: int,
        col: int,
        spin_info: dict,
        spin_state: dict,
        choose_index: int = 1,
        free_choice: dict | None = None,
        return_detail: bool = False,
        max_cascades: int = 100,
        free_game: bool = False,
        max_round_num: int | None = None,
        win_multipliers: list[int] | tuple[int, ...] | None = None,
    ) -> dict:
        """循环执行“算奖 -> 消除 -> 下落补牌”，直到没有新的中奖。"""

        total_win = 0
        rounds = []
        all_win_items = []
        board = self.build_effective_board(item_list, free_game=free_game)
        item_list = self._clone_board(board)
        row = self._get_board_row_count(board)
        col = len(board)
        round_limit = self.get_max_round_num(free_game=free_game) if max_round_num is None else max_round_num
        active_free_choice = self.normalize_free_choice(free_choice)

        for cascade_index in range(1, max_cascades + 1):
            round_info = self.evaluate(board, row=row, col=col, return_detail=True, free_game=free_game)
            win_positions = round_info["win_positions"]
            if round_info["total_win"] <= 0 or not win_positions:
                break

            reached_round_limit = round_limit > 0 and cascade_index >= round_limit
            win_multiplier = self.get_cascade_win_multiplier(
                cascade_index,
                free_game=free_game,
                win_multipliers=win_multipliers,
                free_multipliers=active_free_choice["multipliers"] if active_free_choice else None,
            )
            raw_total_win = round_info["total_win"]
            round_total_win = raw_total_win * win_multiplier
            round_win_items = self.apply_win_multiplier(round_info["win_items"], win_multiplier)
            total_win += round_total_win
            all_win_items.extend(round_win_items)

            next_board, drop_info = self.drop_new_items(
                item_list=board,
                win_positions=win_positions,
                gold_weights=gold_weights,
                row=row,
                col=col,
                spin_state=spin_state,
                free_game=free_game,
            )
            rounds.append(
                {
                    "cascade_index": cascade_index,
                    "item_list": round_info["item_list"],
                    "total_win": round_total_win,
                    "raw_total_win": raw_total_win,
                    "win_multiplier": win_multiplier,
                    "win_items": round_win_items,
                    "win_positions": win_positions,
                    "drop_info": drop_info,
                    "next_item_list": next_board,
                    "round_limit_reached": reached_round_limit,
                }
            )
            board = next_board
            if reached_round_limit:
                break
        else:
            raise RuntimeError(f"cascade exceeded max_cascades={max_cascades}")

        scatter_count = self.count_scatter(board, row=row, col=col, free_game=free_game)
        is_trigger_free = scatter_count >= self.FREE_BASE_SCATTER_COUNT
        if is_trigger_free and active_free_choice is None:
            active_free_choice = self.get_free_choice(choose_index)
        free_times = active_free_choice["free_times"] if is_trigger_free and active_free_choice else 0

        self.last_spin_info = spin_info
        self.last_spin_state = spin_state
        self.last_ng_result = {
            "item_list": item_list,
            "final_item_list": board,
            "total_win": total_win,
            "cascade_count": len(rounds),
            "max_round_num": round_limit,
            "scatter_count": scatter_count,
            "is_trigger_free": is_trigger_free,
            "free_times": free_times,
            "free_choice": active_free_choice if is_trigger_free or free_game else None,
            "win_items": all_win_items if return_detail else [],
            "rounds": rounds if return_detail else [],
            "spin_info": spin_info,
            "final_top_indexes": spin_state["top_indexes"][:],
        }
        return self.last_ng_result

    def get_cascade_win_multiplier(
        self,
        cascade_index: int,
        free_game: bool = False,
        free_multipliers: list[int] | tuple[int, ...] | None = None,
        win_multipliers: list[int] | tuple[int, ...] | None = None,
    ) -> int:
        """获取当前消除轮次的赢钱倍数。"""

        if cascade_index <= 0:
            raise ValueError("cascade_index must be positive")

        if win_multipliers is not None:
            multipliers = list(win_multipliers)
        elif free_game:
            multipliers = list(free_multipliers or self.free_multi_list[0])
        else:
            multipliers = list(self.base_win_multipliers)
        return self._get_or_default(multipliers, cascade_index - 1, multipliers[-1])

    @staticmethod
    def apply_win_multiplier(win_items, win_multiplier: int) -> list[dict]:
        """复制中奖明细并把每个 item 的赢钱按消除倍数放大。"""

        multiplied_items = []
        for win_item in win_items:
            item = win_item.copy()
            item["raw_win"] = item["win"]
            item["win_multiplier"] = win_multiplier
            item["win"] = item["win"] * win_multiplier
            multiplied_items.append(item)
        return multiplied_items

    def get_max_round_num(self, free_game: bool = False) -> int:
        """读取当前模式允许的最大连续消除次数；配置为 0 时不限制。"""

        if not self.game_server_config.has_section("Game Info"):
            return 0

        key = "FreeMaxRoundNum" if free_game else "MainMaxRoundNum"
        value = self.game_server_config["Game Info"].get(key, "0")
        return int(value.strip() or 0)

    def drop_new_items(
        self,
        item_list,
        win_positions,
        gold_weights,
        row: int,
        col: int,
        spin_state: dict,
        free_game: bool = False,
    ):
        """消除中奖格，让上方 symbol 下落，并从原停轴上方补新 symbol。"""

        board = self._clone_board(item_list)
        remove_positions = {tuple(position) for position in win_positions}
        actual_remove_positions = set()
        for position in remove_positions:
            col_index, row_index = position
            if self.is_gold_symbol(board[col_index][row_index]):
                # 金色 symbol 第一次被消除时不离开牌面，而是变成 wild，等待第二次消除。
                board[col_index][row_index] = self.wild_id
            else:
                actual_remove_positions.add(position)

        refill_items = []
        for col_index in range(col):
            valid_rows = self.get_active_rows_for_col(board, col_index, row, col, free_game=free_game)
            survivors = [
                board[col_index][row_index]
                for row_index in valid_rows
                if (col_index, row_index) not in actual_remove_positions
            ]
            need_count = len(valid_rows) - len(survivors)
            top_index_before = spin_state["top_indexes"][col_index]
            new_items = self.take_symbols_above(spin_state, col_index, need_count)
            new_items = [
                self.apply_gold_to_symbol(
                    new_item,
                    col_index,
                    row_index,
                    gold_weights,
                    free_game=free_game,
                )
                for new_item, row_index in zip(new_items, valid_rows[:need_count])
            ]
            top_index_after = spin_state["top_indexes"][col_index]
            new_values = new_items + survivors

            for value_index, row_index in enumerate(valid_rows):
                board[col_index][row_index] = new_values[value_index]

            refill_items.append(
                {
                    "col": col_index,
                    "rows": valid_rows[:need_count],
                    "items": new_items,
                    "top_index_before": top_index_before,
                    "top_index_after": top_index_after,
                }
            )

        drop_info = {
            "remove_positions": sorted(remove_positions),
            "source_type": spin_state["source_type"],
            "refill_items": refill_items,
        }
        return board, drop_info

    def _load_game_server_config(self, path: Path) -> ConfigParser:
        """读取 game server 配置，用于金色 symbol 等服务器侧权重。"""

        parser = ConfigParser(inline_comment_prefixes=("#", ";"))
        parser.optionxform = str
        parser.read(path, encoding="utf-8-sig")
        return parser

    def load_free_choice_config(self) -> tuple[list[int], list[list[int]], list[int], list[int]]:
        """从 game_server.conf 读取 1-4 类 free 的次数和消除倍数。"""

        if not self.game_server_config.has_section("Game Info"):
            raise ValueError(f"{self.game_server_config_file} has no [Game Info] section")

        game_info = self.game_server_config["Game Info"]
        free_count_list = self._parse_config_int_list(game_info.get("FREE_COUNT_LIST", ""), "FREE_COUNT_LIST")
        if "FREE_MULTI_LIST" in game_info:
            free_multi_list = self._parse_literal_nested_int_list(
                game_info.get("FREE_MULTI_LIST", "[]"),
                "FREE_MULTI_LIST",
            )
        else:
            free_multi_list = [
                self._parse_config_int_list(
                    game_info.get(f"FREE_MULTI_LIST_{index}", ""),
                    f"FREE_MULTI_LIST_{index}",
                )
                for index in range(1, len(free_count_list) + 1)
            ]
        if not free_count_list:
            raise ValueError("FREE_COUNT_LIST cannot be empty")
        if len(free_count_list) != len(free_multi_list):
            raise ValueError("FREE_COUNT_LIST and FREE_MULTI_LIST must have the same length")

        free_random_count_weights = self._parse_optional_weight_list(
            game_info.get("FREE_RANDOM_COUNT_WEIGHTS", ""),
            "FREE_RANDOM_COUNT_WEIGHTS",
            len(free_count_list),
        )
        free_random_multi_weights = self._parse_optional_weight_list(
            game_info.get("FREE_RANDOM_MULTI_WEIGHTS", ""),
            "FREE_RANDOM_MULTI_WEIGHTS",
            len(free_multi_list),
        )
        return free_count_list, free_multi_list, free_random_count_weights, free_random_multi_weights

    def load_win_box_level_config(self) -> tuple[list[int], list[list[int]]]:
        """Load base cascade multiplier weights and multiplier lists."""

        if not self.game_server_config.has_section("Game Info"):
            return [1], [[1]]

        game_info = self.game_server_config["Game Info"]
        rates = self._parse_config_int_list(game_info.get("WinBoxLevelUpRate", "1"), "WinBoxLevelUpRate")
        multiplier_lists = []
        if "WinBoxLevelMultiple" in game_info:
            multiplier_lists.append(self._parse_config_int_list(game_info.get("WinBoxLevelMultiple"), "WinBoxLevelMultiple"))
        else:
            for index in range(1, len(rates) + 1):
                key = f"WinBoxLevelMultiple_{index}"
                multiplier_lists.append(self._parse_config_int_list(game_info.get(key, ""), key))

        if not rates:
            raise ValueError("WinBoxLevelUpRate cannot be empty")
        if len(rates) != len(multiplier_lists):
            raise ValueError("WinBoxLevelUpRate and WinBoxLevelMultiple_n must have the same length")
        return rates, multiplier_lists

    def choose_base_win_multipliers(self) -> tuple[int, list[int]]:
        """Choose one base cascade multiplier list for this paid spin."""

        multiplier_index = self.weighted_random_index(self.win_box_level_up_rates)
        return multiplier_index + 1, list(self.win_box_level_multipliers[multiplier_index])

    def get_win_box_level_multipliers(self) -> list[int]:
        """从 game server 的 WinBoxLevelMultiple 读取普通游戏消除倍数。"""

        return list(self.win_box_level_multipliers[0])

    def get_game_server_section(self, index: int):
        """根据 spin 的 index 选择 game_server 配置段。"""

        for section_name in (str(index), "0", "Game Info"):
            if self.game_server_config.has_section(section_name):
                return self.game_server_config[section_name]
        raise ValueError("game server config has no usable game section")

    @staticmethod
    def weighted_random_index(weights: list[int]) -> int:
        """按整数权重随机返回列表下标。"""

        total_weight = sum(weights)
        if total_weight <= 0:
            raise ValueError("random weights total must be greater than 0")

        hit = random.randrange(total_weight)
        current_weight = 0
        for index, weight in enumerate(weights):
            current_weight += weight
            if hit < current_weight:
                return index
        return len(weights) - 1

    def get_gold_symbol_weights(
        self,
        game_server_section,
        free_game: bool = False,
        free_general_index: int | None = None,
    ) -> list[int]:
        """从当前 game_server 配置段读取第 2/3/4 列的金色 symbol 生成权重。"""

        if free_game:
            return self.get_free_gold_symbol_weights(game_server_section, free_general_index)
        value = game_server_section.get("GoldSymbolWeight")
        return self._parse_int_list(value)

    def get_level_up_gold_symbol_weights(self, game_server_section) -> list[int]:
        """读取 base 倍乘框升级时第 2/3/4 列的金色 symbol 生成权重。"""

        value = game_server_section.get("LevelUpGoldWeight")
        if value is None and self.game_server_config.has_section("Game Info"):
            value = self.game_server_config["Game Info"].get("LevelUpGoldWeight")
        if value is None:
            return self.get_gold_symbol_weights(game_server_section, free_game=False)
        return self._parse_config_int_list(value, "LevelUpGoldWeight")

    def get_free_gold_symbol_weights(
        self,
        value,
        free_general_index: int | None = None,
    ) -> list[int]:
        """Read free gold weights, supporting one list per free GENERAL index."""

        if hasattr(value, "get") and not isinstance(value, str):
            weight_index = 1 if free_general_index is None else max(int(free_general_index), 1)
            indexed_value = value.get(f"FreeGoldSymbolWeight_{weight_index}")
            if indexed_value is not None:
                return self._parse_config_int_list(indexed_value, f"FreeGoldSymbolWeight_{weight_index}")
            fallback_value = value.get("FreeGoldSymbolWeight_1")
            if fallback_value is not None:
                return self._parse_config_int_list(fallback_value, "FreeGoldSymbolWeight_1")
            value = value.get("FreeGoldSymbolWeight")

        parsed_value = self.parse_gold_symbol_weight_value(value)
        if not parsed_value:
            return []

        if isinstance(parsed_value[0], list):
            weight_index = 0 if free_general_index is None else max(int(free_general_index) - 1, 0)
            if weight_index >= len(parsed_value):
                weight_index = 0
            return parsed_value[weight_index]

        return parsed_value

    def parse_gold_symbol_weight_value(self, value: str):
        """Parse flat or nested GoldSymbolWeight values."""

        if value is None:
            return []
        stripped_value = value.strip()
        try:
            parsed_value = ast.literal_eval(stripped_value)
        except (SyntaxError, ValueError):
            return self._parse_int_list(value)

        if not isinstance(parsed_value, (list, tuple)):
            raise ValueError("GoldSymbolWeight must be a list or comma-separated ints")
        if not parsed_value:
            return []
        if all(isinstance(item, (list, tuple)) for item in parsed_value):
            return [[int(weight) for weight in item] for item in parsed_value]
        return [int(weight) for weight in parsed_value]

    def count_scatter(self, item_list, row: int | None = None, col: int | None = None, free_game: bool = False) -> int:
        """统计最终牌面上的普通 scatter 数量。"""

        if row is not None and col is not None:
            return sum(
                1
                for col_index, row_index in self.iter_active_positions(
                    item_list,
                    row=row,
                    col=col,
                    free_game=free_game,
                )
                if item_list[col_index][row_index] == self.SCATTER_ID
            )
        return sum(1 for col_items in item_list for symbol_id in col_items if symbol_id == self.SCATTER_ID)

    def apply_gold_symbols(
        self,
        item_list,
        gold_weights,
        row: int,
        col: int,
        free_game: bool = False,
    ) -> list[list[int]]:
        """根据 GoldSymbolWeight 把牌面中的普通 symbol 转成 100+symbol_id。"""

        board = self._clone_board(item_list)
        for col_index, row_index in self.iter_active_positions(board, row=row, col=col, free_game=free_game):
            board[col_index][row_index] = self.apply_gold_to_symbol(
                board[col_index][row_index],
                col_index,
                row_index,
                gold_weights,
                free_game=free_game,
            )
        return board

    def apply_gold_to_symbol(
        self,
        symbol_id: int,
        col_index: int,
        row_index: int,
        gold_weights,
        free_game: bool = False,
    ) -> int:
        """按万分比判断一个 symbol 是否变成金色，金色用 100+symbol_id 表示。"""

        if col_index not in self.GOLD_COLUMNS:
            return symbol_id
        if not self.can_be_gold_symbol(symbol_id):
            return symbol_id

        weight_index = self.GOLD_COLUMNS.index(col_index)
        if weight_index >= len(gold_weights):
            return symbol_id

        weight = gold_weights[weight_index]
        if random.randrange(self.GOLD_BASE) < weight:
            return self.GOLD_SYMBOL_OFFSET + symbol_id
        return symbol_id

    def can_be_gold_symbol(self, symbol_id: int) -> bool:
        """只有普通可赔付 symbol 才生成金色，scatter 和原生 wild 不生成金色。"""

        symbol_id = self.get_base_symbol_id(symbol_id)
        if symbol_id == self.wild_id or symbol_id == self.SCATTER_ID:
            return False
        return self._get_or_default(self.config.base_nums, symbol_id, 0) > 0

    def _build_evaluate_board(self, item_list):
        """把金色 symbol 临时还原成原 symbol 后交给通用算奖逻辑。"""

        evaluate_board = self._clone_board(item_list)
        for col_index, col_items in enumerate(evaluate_board):
            for row_index in range(len(col_items)):
                evaluate_board[col_index][row_index] = self.get_base_symbol_id(
                    evaluate_board[col_index][row_index]
                )
        return evaluate_board

    def is_gold_symbol(self, symbol_id: int) -> bool:
        """判断一个 symbol 是否是 100+symbol_id 编码的金色 symbol。"""

        return symbol_id > self.GOLD_SYMBOL_OFFSET

    def get_base_symbol_id(self, symbol_id: int) -> int:
        """把金色 symbol 还原成基础 symbol id。"""

        if symbol_id > self.GOLD_SYMBOL_OFFSET:
            return symbol_id - self.GOLD_SYMBOL_OFFSET
        return symbol_id

    @staticmethod
    def _clone_board(item_list):
        """复制牌面，避免消除流程直接修改调用者传入的对象。"""

        return [list(col_items) for col_items in item_list]

    @staticmethod
    def _parse_literal_int_list(value: str, key: str) -> list[int]:
        """解析形如 [24, 12, 8, 6] 的整数列表配置。"""

        return ThemeMath._parse_config_int_list(value, key)

    @staticmethod
    def _parse_config_int_list(value: str | None, key: str) -> list[int]:
        """Parse comma-separated or Python-style integer lists."""

        if value is None or not str(value).strip():
            raise ValueError(f"{key} cannot be empty")
        stripped_value = str(value).strip()
        try:
            result = ast.literal_eval(stripped_value)
        except (SyntaxError, ValueError) as exc:
            try:
                return [int(item.strip()) for item in stripped_value.split(",") if item.strip()]
            except ValueError as parse_exc:
                raise ValueError(f"{key} must be comma-separated ints or a Python-style list") from parse_exc
        if not isinstance(result, (list, tuple)):
            raise ValueError(f"{key} must be a list")
        return [int(item) for item in result]

    @classmethod
    def _parse_optional_weight_list(cls, value: str, key: str, expected_length: int) -> list[int]:
        """读取可选权重配置；未配置时默认各选项等权重。"""

        if not value or not value.strip():
            return [1 for _ in range(expected_length)]

        weights = cls._parse_config_int_list(value, key)
        if len(weights) != expected_length:
            raise ValueError(f"{key} length must be {expected_length}")
        if any(weight < 0 for weight in weights):
            raise ValueError(f"{key} cannot contain negative weights")
        if sum(weights) <= 0:
            raise ValueError(f"{key} total must be greater than 0")
        return weights

    @classmethod
    def _parse_literal_nested_int_list(cls, value: str, key: str) -> list[list[int]]:
        """解析形如 [[1, 2], [3, 4]] 的整数嵌套列表配置。"""

        try:
            result = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"{key} must be a Python-style nested list") from exc
        if not isinstance(result, list):
            raise ValueError(f"{key} must be a list")
        nested_result = []
        for item in result:
            if not isinstance(item, list) or not item:
                raise ValueError(f"{key} must contain non-empty lists")
            nested_result.append([int(multiplier) for multiplier in item])
        return nested_result
