"""重新统计轴带 symbol 数量，并写回到轴配置备注中。

默认统计当前目录下 reel_config 和 free_reel_config 中所有 .conf 文件，
只处理 NORMAL_ROLL_* 和 SP_ROLL_*，统计结果格式与配置中的备注一致。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_CONFIG_DIRS = ("reel_config", "free_reel_config")
DEFAULT_ROLL_PREFIXES = ("NORMAL_ROLL", "SP_ROLL")
ROLL_RE = re.compile(r"^(NORMAL_ROLL|SP_ROLL)_(\d+)\s*=\s*(.*)$")
COUNT_LINE_RE = re.compile(r"^\s*\[[\d,\s-]*\],?\s*$")


@dataclass
class FileResult:
    path: Path
    groups: int = 0
    old_blocks_removed: int = 0
    changed: bool = False
    warnings: list[str] = field(default_factory=list)


def parse_roll_values(line: str) -> list[int]:
    """从 ROLL 配置行中解析出 symbol id 列表。"""
    value_text = line.split("=", 1)[1].split("#", 1)[0].strip()
    if not value_text:
        return []
    return [int(value.strip()) for value in value_text.split(",") if value.strip()]


def count_symbols(
    rolls: list[list[int]],
    symbol_min: int,
    symbol_max: int,
) -> tuple[list[list[int]], dict[int, int]]:
    """统计每列轴中 symbol_min 到 symbol_max 的出现次数。"""
    symbol_count = symbol_max - symbol_min + 1
    counts = [[0 for _ in range(symbol_count)] for _ in rolls]
    out_of_range: dict[int, int] = {}

    for roll_index, roll in enumerate(rolls):
        for symbol in roll:
            if symbol_min <= symbol <= symbol_max:
                counts[roll_index][symbol - symbol_min] += 1
            else:
                out_of_range[symbol] = out_of_range.get(symbol, 0) + 1

    return counts, out_of_range


def format_count_block(counts: list[list[int]], newline: str) -> list[str]:
    """生成和配置文件备注一致的三引号统计块。"""
    lines = [f'"""{newline}']
    for index, row in enumerate(counts):
        suffix = ", " if index < len(counts) - 1 else ""
        lines.append(f"{row}{suffix}{newline}")
    lines.append(f'"""{newline}')
    return lines


def is_symbol_count_block(lines: list[str], start: int, end: int) -> bool:
    """判断三引号块是否为本脚本生成的 symbol 数量备注。"""
    content_lines = lines[start + 1 : end]
    if not content_lines:
        return False
    return all(COUNT_LINE_RE.match(line.rstrip("\r\n")) for line in content_lines)


def remove_old_count_block(lines: list[str], roll_start: int) -> tuple[int, int]:
    """删除紧贴在 ROLL 组前面的旧统计备注，返回新的 ROLL 起点。"""
    block_end = roll_start - 1
    while block_end >= 0 and not lines[block_end].strip():
        block_end -= 1

    if block_end < 0 or lines[block_end].strip() != '"""':
        return roll_start, 0

    block_start = block_end - 1
    while block_start >= 0 and lines[block_start].strip() != '"""':
        block_start -= 1

    if block_start < 0 or not is_symbol_count_block(lines, block_start, block_end):
        return roll_start, 0

    del lines[block_start:roll_start]
    return block_start, 1


def collect_roll_group(
    lines: list[str],
    start: int,
    enabled_prefixes: set[str],
) -> tuple[str | None, list[list[int]], int]:
    """从当前位置收集同一组连续 ROLL_1、ROLL_2... 配置。"""
    first_match = ROLL_RE.match(lines[start].rstrip("\r\n"))
    if not first_match:
        return None, [], start

    prefix = first_match.group(1)
    if prefix not in enabled_prefixes or int(first_match.group(2)) != 1:
        return None, [], start

    rolls: list[list[int]] = []
    next_index = start
    expected_roll_index = 1

    while next_index < len(lines):
        match = ROLL_RE.match(lines[next_index].rstrip("\r\n"))
        if not match:
            break
        if match.group(1) != prefix or int(match.group(2)) != expected_roll_index:
            break

        rolls.append(parse_roll_values(lines[next_index]))
        next_index += 1
        expected_roll_index += 1

    return prefix, rolls, next_index


def detect_newline(text: str) -> str:
    """沿用原配置文件的换行符。"""
    return "\r\n" if "\r\n" in text else "\n"


def update_file(
    path: Path,
    symbol_min: int,
    symbol_max: int,
    enabled_prefixes: set[str],
    dry_run: bool,
) -> FileResult:
    """更新单个配置文件中的所有 ROLL 统计备注。"""
    original_text = path.read_text(encoding="utf-8")
    newline = detect_newline(original_text)
    lines = original_text.splitlines(keepends=True)
    result = FileResult(path=path)

    line_index = 0
    while line_index < len(lines):
        prefix, rolls, next_index = collect_roll_group(lines, line_index, enabled_prefixes)
        if not prefix:
            line_index += 1
            continue

        line_index, removed = remove_old_count_block(lines, line_index)
        result.old_blocks_removed += removed

        counts, out_of_range = count_symbols(rolls, symbol_min, symbol_max)
        if out_of_range:
            detail = ", ".join(f"{symbol}:{count}" for symbol, count in sorted(out_of_range.items()))
            result.warnings.append(f"{prefix} has out-of-range symbols: {detail}")

        count_block = format_count_block(counts, newline)
        lines[line_index:line_index] = count_block
        result.groups += 1
        line_index += len(count_block) + len(rolls)

    updated_text = "".join(lines)
    result.changed = updated_text != original_text
    if result.changed and not dry_run:
        path.write_text(updated_text, encoding="utf-8", newline="")

    return result


def iter_config_files(root: Path, config_dirs: tuple[str, ...]) -> list[Path]:
    """按固定顺序收集要统计的配置文件。"""
    files: list[Path] = []
    for dirname in config_dirs:
        config_dir = root / dirname
        if not config_dir.exists():
            continue
        files.extend(sorted(config_dir.glob("*.conf")))
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计正常盘和特殊盘轴带中的 symbol 数量。")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="项目目录，默认是 symbol_count.py 所在目录。",
    )
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=list(DEFAULT_CONFIG_DIRS),
        help="要扫描的配置目录，默认 reel_config free_reel_config。",
    )
    parser.add_argument(
        "--prefixes",
        nargs="+",
        default=list(DEFAULT_ROLL_PREFIXES),
        help="要统计的 ROLL 前缀，默认 NORMAL_ROLL SP_ROLL。",
    )
    parser.add_argument("--symbol-min", type=int, default=0, help="统计的最小 symbol id。")
    parser.add_argument("--symbol-max", type=int, default=10, help="统计的最大 symbol id。")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写回文件。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_dirs = tuple(args.dirs)
    enabled_prefixes = set(args.prefixes)

    if args.symbol_min > args.symbol_max:
        raise ValueError("--symbol-min 不能大于 --symbol-max")

    files = iter_config_files(root, config_dirs)
    if not files:
        print(f"未找到配置文件: {root}")
        return 1

    results = [
        update_file(
            path=path,
            symbol_min=args.symbol_min,
            symbol_max=args.symbol_max,
            enabled_prefixes=enabled_prefixes,
            dry_run=args.dry_run,
        )
        for path in files
    ]

    total_groups = sum(result.groups for result in results)
    total_removed = sum(result.old_blocks_removed for result in results)
    total_changed = sum(1 for result in results if result.changed)
    action = "检查" if args.dry_run else "更新"

    for result in results:
        if result.groups == 0:
            continue
        state = "changed" if result.changed else "unchanged"
        relative_path = result.path.relative_to(root)
        print(
            f"{relative_path}: groups={result.groups}, "
            f"old_blocks_removed={result.old_blocks_removed}, {state}"
        )
        for warning in result.warnings:
            print(f"  warning: {warning}")

    print(
        f"{action}完成: files={len(files)}, groups={total_groups}, "
        f"old_blocks_removed={total_removed}, changed_files={total_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
