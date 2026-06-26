"""删除 rand_ex 轴配置中的 symbol 数量备注。

默认扫描当前目录下 reel_config 和 free_reel_config 中的 *rand_ex*.conf 文件，
只删除紧贴在 NORMAL_ROLL_* 和 SP_ROLL_* 前面、内容为计数列表的三引号备注块。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_DIRS = ("reel_config", "free_reel_config")
DEFAULT_FILE_PATTERN = "*rand_ex*.conf"
DEFAULT_ROLL_PREFIXES = ("NORMAL_ROLL", "SP_ROLL")
ROLL_RE = re.compile(r"^(NORMAL_ROLL|SP_ROLL)_(\d+)\s*=")
COUNT_LINE_RE = re.compile(r"^\s*\[[\d,\s-]*\],?\s*$")


@dataclass
class FileResult:
    path: Path
    groups: int = 0
    count_blocks_removed: int = 0
    changed: bool = False


def is_symbol_count_block(lines: list[str], start: int, end: int) -> bool:
    """判断三引号块是否为 symbol 数量备注。"""
    content_lines = lines[start + 1 : end]
    if not content_lines:
        return False
    return all(COUNT_LINE_RE.match(line.rstrip("\r\n")) for line in content_lines)


def remove_count_block_before_roll(lines: list[str], roll_start: int) -> tuple[int, int]:
    """删除紧贴在 ROLL 组前面的统计备注，返回新的 ROLL 起点和删除数量。"""
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


def collect_roll_group_end(
    lines: list[str],
    start: int,
    enabled_prefixes: set[str],
) -> tuple[str | None, int]:
    """从当前位置识别同一组连续 ROLL_1、ROLL_2... 配置。"""
    first_match = ROLL_RE.match(lines[start].rstrip("\r\n"))
    if not first_match:
        return None, start

    prefix = first_match.group(1)
    if prefix not in enabled_prefixes or int(first_match.group(2)) != 1:
        return None, start

    next_index = start
    expected_roll_index = 1
    while next_index < len(lines):
        match = ROLL_RE.match(lines[next_index].rstrip("\r\n"))
        if not match:
            break
        if match.group(1) != prefix or int(match.group(2)) != expected_roll_index:
            break

        next_index += 1
        expected_roll_index += 1

    return prefix, next_index


def update_file(path: Path, enabled_prefixes: set[str], dry_run: bool) -> FileResult:
    """删除单个配置文件中的所有 ROLL 统计备注。"""
    original_text = path.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)
    result = FileResult(path=path)

    line_index = 0
    while line_index < len(lines):
        prefix, next_index = collect_roll_group_end(lines, line_index, enabled_prefixes)
        if not prefix:
            line_index += 1
            continue

        group_line_count = next_index - line_index
        line_index, removed = remove_count_block_before_roll(lines, line_index)
        result.groups += 1
        result.count_blocks_removed += removed
        line_index += group_line_count

    updated_text = "".join(lines)
    result.changed = updated_text != original_text
    if result.changed and not dry_run:
        path.write_text(updated_text, encoding="utf-8", newline="")

    return result


def iter_config_files(root: Path, config_dirs: tuple[str, ...], pattern: str) -> list[Path]:
    """按固定顺序收集要处理的 rand_ex 配置文件。"""
    files: list[Path] = []
    for dirname in config_dirs:
        config_dir = root / dirname
        if not config_dir.exists():
            continue
        files.extend(sorted(config_dir.glob(pattern)))
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="删除 rand_ex 轴配置中的 symbol 数量备注。")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="项目目录，默认是 remove_symbol_count.py 所在目录。",
    )
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=list(DEFAULT_CONFIG_DIRS),
        help="要扫描的配置目录，默认 reel_config free_reel_config。",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_FILE_PATTERN,
        help="要处理的文件名模式，默认 *rand_ex*.conf。",
    )
    parser.add_argument(
        "--prefixes",
        nargs="+",
        default=list(DEFAULT_ROLL_PREFIXES),
        help="要处理的 ROLL 前缀，默认 NORMAL_ROLL SP_ROLL。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写回文件。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_dirs = tuple(args.dirs)
    enabled_prefixes = set(args.prefixes)

    files = iter_config_files(root, config_dirs, args.pattern)
    if not files:
        print(f"未找到配置文件: {root}")
        return 1

    results = [
        update_file(
            path=path,
            enabled_prefixes=enabled_prefixes,
            dry_run=args.dry_run,
        )
        for path in files
    ]

    total_groups = sum(result.groups for result in results)
    total_removed = sum(result.count_blocks_removed for result in results)
    total_changed = sum(1 for result in results if result.changed)
    action = "检查" if args.dry_run else "删除"

    for result in results:
        if result.groups == 0:
            continue
        state = "changed" if result.changed else "unchanged"
        relative_path = result.path.relative_to(root)
        print(
            f"{relative_path}: groups={result.groups}, "
            f"count_blocks_removed={result.count_blocks_removed}, {state}"
        )

    print(
        f"{action}完成: files={len(files)}, groups={total_groups}, "
        f"count_blocks_removed={total_removed}, changed_files={total_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
