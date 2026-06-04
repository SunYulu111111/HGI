"""麻将五龙主题数学入口。

ThemeMath 继承通用 WaysGame，只负责把 mahj3 主题自己的流程串起来：
正常 spin、生成金色 symbol、计算赢钱、消除中奖格、从原停轴上方补牌并继续计算。
"""

from pathlib import Path
import sys
from configparser import ConfigParser
import random

# 直接运行 mahj3/simulation.py 时，Python 默认只把 mahj3 加到 sys.path。
# 这里把项目根目录加入搜索路径，才能导入上一层的 slots_math.py。
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import WaysGame


class ThemeMath(WaysGame):
    """mahj3 主题的数学封装。"""

    # 配置里的 GoldSymbolWeight 对应第 2、3、4 列，内部下标是 1、2、3。
    # 100 固定表示黑色 scatter；金色 symbol 使用 100+普通 symbol id，因此只会是 102、103...
    GOLD_COLUMNS = (1, 2, 3)
    GOLD_BASE = 10000
    GOLD_SYMBOL_OFFSET = 100
    SCATTER_ID = 0
    BLACK_SCATTER_ID = 100
    FREE_BASE_SCATTER_COUNT = 3
    FREE_BASE_TIMES = 10
    FREE_EXTRA_TIMES_PER_SCATTER = 2
    FREE_REEL_CONFIG_DIR = "free_reel_config"
    BASE_CASCADE_MULTIPLIERS = (1, 2, 3)
    BASE_CASCADE_AFTER_MULTIPLIER = 5
    FREE_CASCADE_MULTIPLIERS = (2, 4, 6)
    FREE_CASCADE_AFTER_MULTIPLIER = 10
    ROUND_LIMIT_NO_WIN_ATTEMPTS = 200

    def __init__(self, base_bet: int = 10000, **kwargs):
        # 默认项目目录就是当前 theme_math.py 所在的 mahj3 文件夹。
        project_dir = kwargs.pop("project_dir", Path(__file__).resolve().parent)
        self.game_server_config_file = kwargs.pop("game_server_config_file", "mahj3_game_server.conf")
        super().__init__(base_bet=base_bet, project_dir=project_dir, **kwargs)
        self.game_server_config = self._load_game_server_config(self.project_dir / self.game_server_config_file)
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

    def ng_spin(
        self,
        index: int,
        general_index: int,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        """普通游戏 spin，并执行完整消除流程。"""

        return self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=None,
            free_game=False,
            return_detail=return_detail,
            max_cascades=max_cascades,
        )

    def fg_spin(
        self,
        index: int,
        general_index: int,
        return_detail: bool = False,
        max_cascades: int = 100,
    ) -> dict:
        """免费游戏 spin，读取 free_reel_config 并执行完整消除算奖流程。"""

        result = self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=self.FREE_REEL_CONFIG_DIR,
            free_game=True,
            return_detail=return_detail,
            max_cascades=max_cascades,
        )
        self.last_fg_result = result
        return result

    def _spin_and_evaluate(
        self,
        index: int,
        general_index: int,
        reel_config_dir,
        free_game: bool,
        return_detail: bool,
        max_cascades: int,
    ) -> dict:
        """按指定轴目录 spin，并套用主题的黑色 scatter、金色 symbol 和消除算奖。"""

        # 行列从 game_config.conf 自动读取；初始取轴仍按原始 5x6 窗口，
        # 进入主题计算前再按 GRID_DISABLES 裁成真正的 45554 有效牌面。
        source_row = self.config.row_count
        col = self.config.col_count

        # spin 传入的 index 同时决定使用 game_server 中哪个配置段。
        game_server_section = self.get_game_server_section(index)
        gold_weights = self.get_gold_symbol_weights(game_server_section, free_game=free_game)
        black_scatter_weights = self.get_black_scatter_weights(game_server_section)
        extra_black_scatter_weights = self.get_extra_black_scatter_weights(game_server_section)
        max_round_num = self.get_max_round_num(free_game=free_game)

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
        # free 中不生成黑色 scatter；base 中普通 scatter 只在 45554 有效格内按 BlackScatterWeight 转黑。
        if free_game:
            item_list = self.clear_black_scatter_symbols(item_list)
        else:
            item_list = self.apply_black_scatter_symbols(
                item_list,
                black_scatter_weights,
                row=row,
                col=col,
                free_game=free_game,
            )
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
        spin_state = self.clone_spin_state(self.last_spin_state)
        return self.evaluate_cascades(
            item_list=item_list,
            gold_weights=gold_weights,
            black_scatter_weights=black_scatter_weights,
            extra_black_scatter_weights=extra_black_scatter_weights,
            row=row,
            col=col,
            spin_info=spin_info,
            spin_state=spin_state,
            return_detail=return_detail,
            max_cascades=max_cascades,
            free_game=free_game,
            max_round_num=max_round_num,
        )

    def build_effective_board(self, item_list, free_game: bool = False) -> list[list[int]]:
        """把原始 5x6 牌面按 GRID_DISABLES 裁成真正参与计算的变长列牌面。"""

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
        total_win = win_result["total_win"]
        win_items = win_result["items"]
        win_positions = win_result["win_positions"]

        self.last_ng_result = {
            "item_list": item_list,
            "total_win": total_win,
            "win_items": win_items,
            "win_positions": win_positions,
            "spin_info": self.last_spin_info,
        }
        return self.last_ng_result

    def evaluate_cascades(
        self,
        item_list,
        gold_weights,
        black_scatter_weights,
        extra_black_scatter_weights,
        row: int,
        col: int,
        spin_info: dict,
        spin_state: dict,
        return_detail: bool = False,
        max_cascades: int = 100,
        free_game: bool = False,
        max_round_num: int | None = None,
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

        for cascade_index in range(1, max_cascades + 1):
            round_info = self.evaluate(board, row=row, col=col, return_detail=True, free_game=free_game)
            win_positions = round_info["win_positions"]
            if round_info["total_win"] <= 0 or not win_positions:
                break

            # 本轮有奖才进入消除流程；无奖时最终牌面就是当前 board。
            # 普通游戏和免费游戏使用不同的连续消除赢钱倍数。
            reached_round_limit = round_limit > 0 and cascade_index >= round_limit
            win_multiplier = self.get_cascade_win_multiplier(cascade_index, free_game=free_game)
            raw_total_win = round_info["total_win"]
            round_total_win = raw_total_win * win_multiplier
            round_win_items = self.apply_win_multiplier(round_info["win_items"], win_multiplier)
            total_win += round_total_win
            all_win_items.extend(round_win_items)

            if reached_round_limit:
                next_board, drop_info = self.drop_new_items_without_win(
                    item_list=board,
                    win_positions=win_positions,
                    gold_weights=gold_weights,
                    black_scatter_weights=black_scatter_weights,
                    row=row,
                    col=col,
                    spin_state=spin_state,
                    free_game=free_game,
                )
            else:
                next_board, drop_info = self.drop_new_items(
                    item_list=board,
                    win_positions=win_positions,
                    gold_weights=gold_weights,
                    black_scatter_weights=black_scatter_weights,
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

        # 消除流程会推进 spin_state 的 top_indexes，这里记录最终状态方便排查。
        # base 中如果没有 ways 中奖且没有触发 free，才按 ExtraBlackScatterWeight 再给普通 scatter 一次转黑机会。
        scatter_count_before_extra = self.count_scatter(board, row=row, col=col, free_game=free_game)
        if (
            not free_game
            and not rounds
            and total_win == 0
            and scatter_count_before_extra < self.FREE_BASE_SCATTER_COUNT
        ):
            board = self.apply_black_scatter_symbols(
                board,
                extra_black_scatter_weights,
                row=row,
                col=col,
                free_game=free_game,
            )
            item_list = board

        scatter_count = self.count_scatter(board, row=row, col=col, free_game=free_game)
        free_times = self.get_free_times(scatter_count)
        is_trigger_free = free_times > 0
        black_scatter_count = self.count_black_scatter(board, row=row, col=col, free_game=free_game)
        scatter_win = self.get_black_scatter_win(black_scatter_count) if is_trigger_free else 0

        self.last_spin_info = spin_info
        self.last_spin_state = spin_state
        self.last_ng_result = {
            "item_list": item_list,
            "final_item_list": board,
            "total_win": total_win,
            "cascade_count": len(rounds),
            "max_round_num": round_limit,
            "scatter_count": scatter_count,
            "black_scatter_count": black_scatter_count,
            "scatter_win": scatter_win,
            "is_trigger_free": is_trigger_free,
            "free_times": free_times,
            "win_items": all_win_items if return_detail else [],
            "rounds": rounds if return_detail else [],
            "spin_info": spin_info,
            "final_top_indexes": spin_state["top_indexes"][:],
        }
        return self.last_ng_result

    def get_black_scatter_win(self, black_scatter_count: int) -> int:
        """根据黑色 scatter 数量计算触发 free 时的额外赢钱。"""

        if black_scatter_count <= 0:
            return 0

        multipliers = self.get_black_scatter_win_multipliers()
        multiplier_index = min(black_scatter_count, len(multipliers)) - 1
        return self.base_bet * self._get_or_default(multipliers, multiplier_index, 0)

    def get_black_scatter_win_multipliers(self) -> list[int]:
        """读取黑色 scatter 额外赔付倍数。"""

        if not self.game_server_config.has_section("Game Info"):
            return [50, 500, 5000, 100000]
        return self._parse_int_list(
            self.game_server_config["Game Info"].get("BlackScatterWinMult", "50,500,5000,100000")
        )

    def get_free_times(self, scatter_count: int) -> int:
        """根据 scatter 数量计算免费游戏次数。"""

        if scatter_count < self.FREE_BASE_SCATTER_COUNT:
            return 0
        extra_scatter_count = scatter_count - self.FREE_BASE_SCATTER_COUNT
        return self.FREE_BASE_TIMES + extra_scatter_count * self.FREE_EXTRA_TIMES_PER_SCATTER

    def get_cascade_win_multiplier(self, cascade_index: int, free_game: bool = False) -> int:
        """获取当前消除轮次的赢钱倍数。"""

        if cascade_index <= 0:
            raise ValueError("cascade_index must be positive")

        if free_game:
            return self._get_or_default(
                self.FREE_CASCADE_MULTIPLIERS,
                cascade_index - 1,
                self.FREE_CASCADE_AFTER_MULTIPLIER,
            )
        return self._get_or_default(
            self.BASE_CASCADE_MULTIPLIERS,
            cascade_index - 1,
            self.BASE_CASCADE_AFTER_MULTIPLIER,
        )

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

    def drop_new_items_without_win(
        self,
        item_list,
        win_positions,
        gold_weights,
        black_scatter_weights,
        row: int,
        col: int,
        spin_state: dict,
        free_game: bool = False,
    ):
        """达到最大消除次数后补牌，确保下一版牌面不再中奖。"""

        attempts = 0
        last_board = None
        last_drop_info = None
        while attempts < self.ROUND_LIMIT_NO_WIN_ATTEMPTS:
            attempts += 1
            next_board, drop_info = self.drop_new_items(
                item_list=item_list,
                win_positions=win_positions,
                gold_weights=gold_weights,
                black_scatter_weights=black_scatter_weights,
                row=row,
                col=col,
                spin_state=spin_state,
                free_game=free_game,
            )
            next_eval = self.evaluate(next_board, row=row, col=col, return_detail=True, free_game=free_game)
            drop_info["round_limit_cut"] = True
            drop_info["round_limit_attempts"] = attempts
            drop_info["next_board_raw_win"] = next_eval["total_win"]
            if next_eval["total_win"] <= 0 or not next_eval["win_positions"]:
                return next_board, drop_info

            last_board = next_board
            last_drop_info = drop_info

        # 极端情况下，仅靠继续取上方符号仍然无法生成无奖牌面时，用确定性兜底牌面打断 ways。
        fixed_board, fix_info = self.force_no_win_board(last_board, row=row, col=col, free_game=free_game)
        last_drop_info["round_limit_forced_no_win"] = True
        last_drop_info["force_no_win_info"] = fix_info
        return fixed_board, last_drop_info

    def force_no_win_board(self, item_list, row: int, col: int, free_game: bool = False):
        """兜底生成无奖牌面，避免超过配置允许的最大连续消除次数。"""

        board = self._clone_board(item_list)
        replacements = []
        for col_index, symbol_id in ((0, 2), (1, 3)):
            if col_index >= col:
                continue
            for row_index in self.get_active_rows_for_col(board, col_index, row, col, free_game=free_game):
                old_symbol_id = board[col_index][row_index]
                board[col_index][row_index] = symbol_id
                replacements.append(
                    {
                        "col": col_index,
                        "row": row_index,
                        "old_symbol_id": old_symbol_id,
                        "new_symbol_id": symbol_id,
                    }
                )

        final_eval = self.evaluate(board, row=row, col=col, return_detail=True, free_game=free_game)
        if final_eval["total_win"] > 0 and final_eval["win_positions"]:
            raise RuntimeError("force_no_win_board failed to build a no-win board")

        return board, {
            "replacements": replacements,
            "final_raw_win": final_eval["total_win"],
        }

    def drop_new_items(
        self,
        item_list,
        win_positions,
        gold_weights,
        black_scatter_weights,
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

        black_scatter_count = self.count_black_scatter(board, row=row, col=col, free_game=free_game)
        refill_items = []
        for col_index in range(col):
            valid_rows = self.get_active_rows_for_col(board, col_index, row, col, free_game=free_game)
            # valid_rows 是从上到下排列；survivors 保留原相对顺序，整体向下补齐。
            survivors = [
                board[col_index][row_index]
                for row_index in valid_rows
                if (col_index, row_index) not in actual_remove_positions
            ]
            need_count = len(valid_rows) - len(survivors)
            top_index_before = spin_state["top_indexes"][col_index]
            # 新 symbol 从当前列停轴窗口上方继续取；base 额外做黑色 scatter 转换，free 中不出黑色 scatter。
            new_items = self.take_symbols_above(spin_state, col_index, need_count)
            if free_game:
                new_items = self.clear_black_scatter_symbols(new_items)
            else:
                new_items, black_scatter_count = self.apply_black_scatter_to_symbols_with_count(
                    new_items,
                    black_scatter_weights,
                    current_black_scatter_count=black_scatter_count,
                )
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
        """读取 mahj3_game_server.conf，用于金色 symbol 等服务器侧权重。"""

        parser = ConfigParser(inline_comment_prefixes=("#", ";"))
        parser.optionxform = str
        parser.read(path, encoding="utf-8-sig")
        return parser

    def get_game_server_section(self, index: int):
        """根据 spin 的 index 选择 game_server 配置段。

        优先读取同名段，例如 index=8 读取 [8]；
        如果没有独立段，则回退到 [0] 默认档；
        最后才回退到 [Game Info] 的公共配置。
        """

        for section_name in (str(index), "0", "Game Info"):
            if self.game_server_config.has_section(section_name):
                return self.game_server_config[section_name]
        raise ValueError("mahj3_game_server.conf has no usable game section")

    def get_gold_symbol_weights(self, game_server_section, free_game: bool = False) -> list[int]:
        """从当前 game_server 配置段读取第 2/3/4 列的金色 symbol 生成权重。"""

        key = "FreeGoldSymbolWeight" if free_game else "GoldSymbolWeight"
        value = game_server_section.get(key)
        return self._parse_int_list(value)

    def get_black_scatter_weights(self, game_server_section) -> list[int]:
        """读取普通 scatter 转黑色 scatter 的万分比。"""

        return self._parse_int_list(game_server_section.get("BlackScatterWeight"))

    def get_extra_black_scatter_weights(self, game_server_section) -> list[int]:
        """读取未中奖时额外 scatter 转黑色 scatter 的万分比。"""

        return self._parse_int_list(game_server_section.get("ExtraBlackScatterWeight"))

    def apply_black_scatter_symbols(
        self,
        item_list,
        black_scatter_weights,
        row: int,
        col: int,
        free_game: bool = False,
    ) -> list[list[int]]:
        """从左到右逐个判断普通 scatter 是否转成黑色 scatter。"""

        board = self._clone_board(item_list)
        black_scatter_count = self.count_black_scatter(board, row=row, col=col, free_game=free_game)
        for col_index, row_index in self.iter_active_positions(board, row=row, col=col, free_game=free_game):
            if board[col_index][row_index] != self.SCATTER_ID:
                continue
            if self.should_scatter_be_black(black_scatter_count, black_scatter_weights):
                board[col_index][row_index] = self.BLACK_SCATTER_ID
                black_scatter_count += 1
        return board

    def clear_black_scatter_symbols(self, item_list):
        """free 中不出现黑色 scatter，若来源里已有 100，则还原成普通 scatter 0。"""

        if self._is_2d(item_list):
            return [
                [
                    self.SCATTER_ID if symbol_id == self.BLACK_SCATTER_ID else symbol_id
                    for symbol_id in col_items
                ]
                for col_items in item_list
            ]
        return [
            self.SCATTER_ID if symbol_id == self.BLACK_SCATTER_ID else symbol_id
            for symbol_id in item_list
        ]

    def apply_black_scatter_to_symbols(
        self,
        symbols,
        black_scatter_weights,
        current_black_scatter_count: int = 0,
    ) -> list[int]:
        """按当前已有黑 scatter 数，顺序判断一批 symbol 并返回转换后的列表。"""

        converted_symbols, _ = self.apply_black_scatter_to_symbols_with_count(
            symbols,
            black_scatter_weights,
            current_black_scatter_count=current_black_scatter_count,
        )
        return converted_symbols

    def apply_black_scatter_to_symbols_with_count(
        self,
        symbols,
        black_scatter_weights,
        current_black_scatter_count: int = 0,
    ) -> tuple[list[int], int]:
        """顺序判断一批 symbol，同时返回更新后的黑 scatter 数。"""

        result = list(symbols)
        black_scatter_count = current_black_scatter_count
        for symbol_index, symbol_id in enumerate(result):
            if symbol_id != self.SCATTER_ID:
                continue
            if self.should_scatter_be_black(black_scatter_count, black_scatter_weights):
                result[symbol_index] = self.BLACK_SCATTER_ID
                black_scatter_count += 1
        return result, black_scatter_count

    def should_scatter_be_black(self, current_black_scatter_count: int, black_scatter_weights) -> bool:
        """按已有黑 scatter 数读取对应 index 的万分比，判断当前 scatter 是否变黑。"""

        weight = self._get_or_default(black_scatter_weights, current_black_scatter_count, 0)
        return weight > 0 and random.randrange(self.GOLD_BASE) < weight

    def apply_black_scatter_to_symbol(self, symbol_id: int, black_scatter_weights, item_list) -> int:
        """单个 symbol 的黑色 scatter 转换判断。"""

        current_black_scatter_count = self.count_black_scatter(item_list) if item_list else 0
        converted_symbols = self.apply_black_scatter_to_symbols(
            [symbol_id],
            black_scatter_weights,
            current_black_scatter_count=current_black_scatter_count,
        )
        return converted_symbols[0]

    def count_black_scatter(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        free_game: bool = False,
    ) -> int:
        """统计当前牌面已有的黑色 scatter 数量。"""

        if row is not None and col is not None:
            return sum(
                1
                for col_index, row_index in self.iter_active_positions(
                    item_list,
                    row=row,
                    col=col,
                    free_game=free_game,
                )
                if item_list[col_index][row_index] == self.BLACK_SCATTER_ID
            )
        return sum(1 for col_items in item_list for symbol_id in col_items if symbol_id == self.BLACK_SCATTER_ID)

    def count_scatter(self, item_list, row: int | None = None, col: int | None = None, free_game: bool = False) -> int:
        """统计最终牌面上的 scatter 数量，普通 scatter 和黑色 scatter 都计入。"""

        if row is not None and col is not None:
            return sum(
                1
                for col_index, row_index in self.iter_active_positions(
                    item_list,
                    row=row,
                    col=col,
                    free_game=free_game,
                )
                if self.is_scatter_symbol(item_list[col_index][row_index])
            )
        return sum(1 for col_items in item_list for symbol_id in col_items if self.is_scatter_symbol(symbol_id))

    def is_scatter_symbol(self, symbol_id: int) -> bool:
        """判断一个 symbol 是否是普通 scatter 或黑色 scatter。"""

        return symbol_id in (self.SCATTER_ID, self.BLACK_SCATTER_ID)

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
        if symbol_id == self.wild_id:
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
