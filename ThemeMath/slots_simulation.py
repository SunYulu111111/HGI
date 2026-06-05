"""Common slots simulation status and report helpers."""

from __future__ import annotations

from copy import deepcopy
import unicodedata


class simulation:
    """Shared status update and report helpers for slots simulations."""

    DEFAULT_THRESHOLDS = (5, 10, 20, 50, 100, 1000)
    DEFAULT_STATUS_MODEL = {
        "base": {
            "spin": 0,
            "lines": [0, 0],
            "free": 0,
        },
        "free": {
            "spin": 0,
            "lines": [0, 0],
            "free": 0,
        },
        "bet": 0,
        "wins": 0,
        "hit": 0,
        "free_times": 0,
        "gt_5x": 0,
        "gt_10x": 0,
        "gt_20x": 0,
        "gt_50x": 0,
        "gt_100x": 0,
        "gt_1000x": 0,
    }
    DEFAULT_HEADERS = [
        "SPIN",
        "rtp",
        "rtp_check",
        "base_rtp",
        "free_rtp",
        "base_lines_rtp",
        "free_lines_rtp",
        "总赢钱",
        "Line赢钱",
        "BaseLine",
        "FreeLine",
        "Hit",
        "Hit率",
        ">5x",
        ">10x",
        ">20x",
        ">50x",
        ">100x",
        ">1000x",
        "触发Free",
        "Free频率",
        "Free次数",
        "FreeSpin",
        "Free重触发",
    ]

    def __init__(
        self,
        status_model: dict | None = None,
        thresholds: tuple[int, ...] | list[int] | None = None,
        headers: list[str] | None = None,
        feature_key: str = "lines",
        feature_label: str = "Line",
        print_mode: str = "table",
        statics_columns: list[dict] | None = None,
    ):
        self.status_model = deepcopy(status_model or self.DEFAULT_STATUS_MODEL)
        self.thresholds = tuple(thresholds or self.DEFAULT_THRESHOLDS)
        self.feature_key = feature_key
        self.feature_label = feature_label
        self.headers = list(headers or self.build_default_headers())
        self.print_mode = print_mode
        self.statics_columns = self.normalize_statics_columns(
            statics_columns or self.build_default_statics_columns()
        )

    def build_default_headers(self) -> list[str]:
        """Build report headers for the configured primary win feature."""

        return [
            "SPIN",
            "rtp",
            "rtp_check",
            "base_rtp",
            "free_rtp",
            f"base_{self.feature_key}_rtp",
            f"free_{self.feature_key}_rtp",
            "总赢钱",
            f"{self.feature_label}赢钱",
            f"Base{self.feature_label}",
            f"Free{self.feature_label}",
            "Hit",
            "Hit率",
            ">5x",
            ">10x",
            ">20x",
            ">50x",
            ">100x",
            ">1000x",
            "触发Free",
            "Free频率",
            "Free次数",
            "FreeSpin",
            "Free重触发",
        ]

    def build_default_statics_columns(self) -> list[dict]:
        """Build grouped statics columns for summary-style output."""

        return [
            {
                "title": "基础信息",
                "fields": [
                    "SPIN",
                    "rtp",
                    "rtp_check",
                    "总赢钱",
                    f"{self.feature_label}赢钱",
                    "Hit",
                    "Hit率",
                    ">5x",
                    ">10x",
                    ">20x",
                    ">50x",
                    ">100x",
                    ">1000x",
                    "错误",
                ],
            },
            {
                "title": "Base",
                "fields": [
                    "base_rtp",
                    f"base_{self.feature_key}_rtp",
                    f"Base{self.feature_label}",
                ],
            },
            {
                "title": "Free",
                "fields": [
                    "free_rtp",
                    f"free_{self.feature_key}_rtp",
                    f"Free{self.feature_label}",
                    "触发Free",
                    "Free频率",
                    "Free次数",
                    "FreeSpin",
                    "Free重触发",
                ],
            },
        ]

    def normalize_statics_columns(self, columns: list[dict]) -> list[dict]:
        """Normalize statics column config into title/fields dictionaries."""

        return [
            {
                "title": column["title"],
                "fields": [self.normalize_statics_field(field) for field in column.get("fields", [])],
            }
            for column in columns
        ]

    @staticmethod
    def normalize_statics_field(field) -> dict:
        """Normalize a statics field config."""

        if isinstance(field, str):
            return {"label": field, "key": field}
        if isinstance(field, (list, tuple)) and len(field) == 2:
            return {"label": field[0], "key": field[1]}
        return {"label": field["label"], "key": field["key"]}

    def add_statics_column(self, title: str, fields: list | None = None) -> None:
        """Append one statics output column."""

        self.statics_columns.append(
            {
                "title": title,
                "fields": [self.normalize_statics_field(field) for field in fields or []],
            }
        )

    def add_statics_field(self, column_title: str, field) -> None:
        """Append one field to an existing statics output column."""

        for column in self.statics_columns:
            if column["title"] == column_title:
                column["fields"].append(self.normalize_statics_field(field))
                return
        raise KeyError(f"unknown statics column: {column_title}")

    def new_status(self) -> dict:
        """Create a fresh status dict from the configured status model."""

        return deepcopy(self.status_model)

    def add_status_value(self, status: dict, value, key1: str, key2: str | None = None) -> None:
        """Add int/list value into status by one or two keys."""

        container = status if key2 is None else status[key1]
        target_key = key1 if key2 is None else key2
        target = container[target_key]

        if isinstance(target, list):
            if isinstance(value, list):
                for index, add_value in enumerate(value):
                    target[index] += add_value
            else:
                target[0] += value
            return

        if isinstance(value, list):
            container[target_key] += sum(value)
        else:
            container[target_key] += value

    def update_spin_start(self, status: dict, bet: int, mode_key: str = "base") -> None:
        """Record one spin start and its bet."""

        self.add_status_value(status, 1, mode_key, "spin")
        self.add_status_value(status, bet, "bet")

    def update_feature_win(self, status: dict, mode_key: str, feature_key: str, win: int) -> None:
        """Record one feature hit and its win into a [count, win] status entry."""

        if win > 0:
            self.add_status_value(status, [1, win], mode_key, feature_key)

    def update_free_trigger(self, status: dict, mode_key: str, free_times: int) -> None:
        """Record a free trigger/retrigger and awarded free-spin count."""

        if free_times > 0:
            self.add_status_value(status, 1, mode_key, "free")
            self.add_status_value(status, free_times, "free_times")

    def update_spin_result(self, status: dict, total_win: int, bet: int) -> None:
        """Record total spin win, hit, and threshold counters."""

        self.add_status_value(status, total_win, "wins")
        if total_win > 0:
            self.add_status_value(status, 1, "hit")
        for threshold in self.thresholds:
            if total_win > bet * threshold:
                self.add_status_value(status, 1, f"gt_{threshold}x")

    def get_list_rtp(self, value: list, bet: int) -> float:
        """Use the second list item as win amount and calculate its RTP."""

        if not bet or len(value) < 2:
            return 0
        return value[1] / bet

    def get_status_rtp(self, value, bet: int) -> float:
        """Calculate RTP from all list win values under a status value."""

        if isinstance(value, list):
            return self.get_list_rtp(value, bet)
        if isinstance(value, dict):
            return sum(self.get_status_rtp(child_value, bet) for child_value in value.values())
        return 0

    def get_total_rtp(self, status: dict) -> float:
        """Calculate total RTP from top-level dict elements in status."""

        bet = status["bet"]
        return sum(
            self.get_status_rtp(value, bet)
            for value in status.values()
            if isinstance(value, dict)
        )

    def build_report_row(self, status: dict) -> dict:
        """Build one cumulative report row from status."""

        base_spin = status["base"]["spin"]
        bet = status["bet"]
        base_feature = status["base"].get(self.feature_key, [0, 0])
        free_feature = status["free"].get(self.feature_key, [0, 0])
        base_feature_rtp = self.get_list_rtp(base_feature, bet)
        free_feature_rtp = self.get_list_rtp(free_feature, bet)
        base_rtp = self.get_status_rtp(status["base"], bet)
        free_rtp = self.get_status_rtp(status["free"], bet)
        row = {
            "SPIN": base_spin,
            "rtp": self.get_total_rtp(status),
            "rtp_check": status["wins"] / bet if bet else 0,
            "base_rtp": base_rtp,
            "free_rtp": free_rtp,
            f"base_{self.feature_key}_rtp": base_feature_rtp,
            f"free_{self.feature_key}_rtp": free_feature_rtp,
            "总赢钱": status["wins"],
            f"{self.feature_label}赢钱": base_feature[1] + free_feature[1],
            f"Base{self.feature_label}": base_feature[1],
            f"Free{self.feature_label}": free_feature[1],
            "Hit": status["hit"],
            "Hit率": status["hit"] / base_spin if base_spin else 0,
            "触发Free": status["base"]["free"],
            "Free频率": status["base"]["free"] / base_spin if base_spin else 0,
            "Free次数": status["free_times"],
            "FreeSpin": status["free"]["spin"],
            "Free重触发": status["free"]["free"],
        }
        for threshold in self.thresholds:
            row[f">{threshold}x"] = status[f"gt_{threshold}x"]
        return row

    def print_table(self, rows: list[dict]) -> None:
        """Print checkpoint rows as a text table."""

        if self.print_mode == "statics":
            self.print_statics(rows)
            return

        formatted_rows = [
            [self.format_cell(header, row.get(header, "")) for header in self.headers]
            for row in rows
        ]
        self.print_grid(self.headers, formatted_rows)

    def print_statics(self, rows: list[dict]) -> None:
        """Print rows as grouped statics columns."""

        for row_index, row in enumerate(rows):
            formatted_columns = [self.format_statics_column(column, row) for column in self.statics_columns]
            max_rows = max((len(column) for column in formatted_columns), default=0)
            for column in formatted_columns:
                column.extend([""] * (max_rows - len(column)))

            headers = [column["title"] for column in self.statics_columns]
            body_rows = [
                [formatted_columns[col_index][line_index] for col_index in range(len(headers))]
                for line_index in range(max_rows)
            ]
            self.print_grid(headers, body_rows)
            if row_index != len(rows) - 1:
                print()

    def print_grid(self, headers: list, rows: list[list]) -> None:
        """Print a bordered table and align cells by terminal display width."""

        if not headers:
            return

        string_headers = [str(header) for header in headers]
        string_rows = [[str(value) for value in row] for row in rows]
        col_widths = []
        for col_index, header in enumerate(string_headers):
            values = [header]
            values.extend(
                row[col_index] if col_index < len(row) else ""
                for row in string_rows
            )
            col_widths.append(max(self.display_width(value) for value in values))

        border = "+" + "+".join("-" * (width + 2) for width in col_widths) + "+"
        print(border)
        print(self.format_grid_row(string_headers, col_widths))
        print(border)
        for row in string_rows:
            padded_row = [
                row[col_index] if col_index < len(row) else ""
                for col_index in range(len(string_headers))
            ]
            print(self.format_grid_row(padded_row, col_widths))
        print(border)

    def format_grid_row(self, row: list[str], col_widths: list[int]) -> str:
        """Format one bordered table row."""

        cells = [
            f" {self.pad_display(row[index], col_widths[index])} "
            for index in range(len(col_widths))
        ]
        return "|" + "|".join(cells) + "|"

    def pad_display(self, value, width: int) -> str:
        """Pad text to display width, including CJK wide characters."""

        text = str(value)
        return text + " " * max(width - self.display_width(text), 0)

    @staticmethod
    def display_width(value) -> int:
        """Return terminal display width for mixed ASCII/CJK text."""

        width = 0
        for char in str(value):
            width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        return width

    def format_statics_column(self, column: dict, row: dict) -> list[str]:
        """Format one statics column for one report row."""

        result = []
        for field in column["fields"]:
            key = field["key"]
            if key not in row:
                continue
            value = self.format_cell(key, row.get(key))
            if value == "":
                continue
            result.append(f"{field['label']}: {value}")
        return result

    def format_cell(self, header: str, value):
        """Format one table cell by header name."""

        if value == "" or value is None:
            return ""
        rtp_headers = {
            "rtp",
            "rtp_check",
            "base_rtp",
            "free_rtp",
            f"base_{self.feature_key}_rtp",
            f"free_{self.feature_key}_rtp",
        }
        if header in rtp_headers or header.endswith("_rtp"):
            return f"{value:.6f}"
        if header in {"Hit率", "Free频率", "触发率", "main_win_rate", "free_win_rate", "win_rate", "trigger_free_rate"}:
            return f"{value:.3%}"
        if header in {"Free平均倍"}:
            return f"{value:.3f}"
        if header in {"Free平均次数"}:
            return f"{value:.6f}"
        return value


Simulation = simulation
