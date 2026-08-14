"""Minimal line-game theme entry.

This model file intentionally keeps theme-specific feature logic out of the
theme layer. Line evaluation is delegated to slots_math.LinesGame.
"""

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from slots_math import LinesGame


class ThemeMath(LinesGame):
    """Thin wrapper for a fixed-line game model."""

    SPECIAL_CONFIG_DIR = "special"
    DEFAULT_GAME_CONFIG_FILE = str(Path(SPECIAL_CONFIG_DIR) / "xxx_game_config.conf")
    FREE_REEL_CONFIG_DIR = "free_reel_config"

    def __init__(self, base_bet: int = 10000, **kwargs):
        project_dir = kwargs.pop("project_dir", Path(__file__).resolve().parent)
        game_config_file = kwargs.pop("game_config_file", self.DEFAULT_GAME_CONFIG_FILE)
        super().__init__(
            base_bet=base_bet,
            project_dir=project_dir,
            game_config_file=game_config_file,
            **kwargs,
        )
        self.game_config_file = game_config_file
        self.scatter_id, self.scatter_cols, self.scatter_multiples = self._load_win_free_config()
        self.last_ng_result: dict = {}
        self.last_fg_result: dict = {}

    def ng_spin(
        self,
        index: int,
        general_index: int,
        return_detail: bool = False,
    ) -> dict:
        return self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=None,
            free_game=False,
            return_detail=return_detail,
        )

    def fg_spin(
        self,
        index: int,
        general_index: int,
        return_detail: bool = False,
    ) -> dict:
        result = self._spin_and_evaluate(
            index=index,
            general_index=general_index,
            reel_config_dir=self.FREE_REEL_CONFIG_DIR,
            free_game=True,
            return_detail=return_detail,
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
    ) -> dict:
        item_list = self.spin(
            index=index,
            general_index=general_index,
            row=self.config.row_count,
            col=self.config.col_count,
            reel_config_dir=reel_config_dir,
        )
        return self.evaluate(
            item_list=item_list,
            row=self.config.row_count,
            col=self.config.col_count,
            return_detail=return_detail,
            free_game=free_game,
        )

    def evaluate(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        return_detail: bool = True,
        free_game: bool = False,
    ) -> dict:
        win_result = self.cal_item_list(
            item_list,
            return_detail=True,
            free_game=free_game,
            row=row,
            col=col,
        )
        result = {
            "item_list": item_list,
            "total_win": win_result["total_win"],
            "win_items": win_result["items"] if return_detail else [],
            "win_positions": win_result["win_positions"],
            "win_free": self.check_win_free(item_list, row=row, col=col, free_game=free_game),
            "spin_info": self.last_spin_info,
            "free_game": free_game,
        }
        self.last_ng_result = result
        return result

    def check_win_free(
        self,
        item_list,
        row: int | None = None,
        col: int | None = None,
        free_game: bool = False,
    ) -> bool:
        board_cols, col_count, row_count = self._normalize_item_list(item_list, row=row, col=col)
        grid_disables = self._get_grid_disables(free_game, col_count, row_count)
        scatter_count = 0
        for col_index in range(col_count):
            if self._get_or_default(self.scatter_cols, col_index, 1) != 1:
                continue
            for row_index in range(min(row_count, len(board_cols[col_index]))):
                if self._is_disabled(grid_disables, col_index, row_index, row_count):
                    continue
                if board_cols[col_index][row_index] == self.scatter_id:
                    scatter_count += 1

        return self._get_or_default(self.scatter_multiples, scatter_count, 0) > 0

    def _load_win_free_config(self) -> tuple[int, list[int], list[int]]:
        parser = self._read_config_file(self.project_dir / self.game_config_file)
        main = parser["MAIN"]
        return (
            int(main.get("SCATTER_ID", "0")),
            self._parse_int_list(main.get("SCATTER_COLS", "")),
            self._parse_int_list(main.get("SCATTER_MULTIPLES", "")),
        )
