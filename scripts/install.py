#!/usr/bin/env python3
"""Install secret-guard into the current Git repository."""

from __future__ import annotations

import argparse
import locale
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def chinese() -> bool:
    requested = os.environ.get("SECRET_GUARD_LANG", "").strip()
    if not requested:
        requested = locale.getlocale()[0] or ""
    normalized = requested.lower().replace("_", "-")
    return normalized == "zh" or normalized.startswith("zh-")


def translated(english: str, chinese_text: str) -> str:
    return chinese_text if chinese() else english


def git_dir() -> Path:
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-dir"],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "not inside a Git repository")
    return Path(result.stdout.strip())


def install(force: bool) -> None:
    target = git_dir()
    hooks = target / "hooks"
    guard = target / "secret-guard"
    hook_names = ("pre-commit", "pre-push")
    conflicts = [hooks / name for name in hook_names if (hooks / name).exists()]
    if conflicts and not force:
        names = ", ".join(str(path) for path in conflicts)
        raise RuntimeError(translated(
            f"existing hook(s) preserved: {names}; integrate manually or rerun with --force",
            f"检测到现有 hook，已保留且未覆盖：{names}；请手动集成，或明确使用 --force",
        ))

    hooks.mkdir(parents=True, exist_ok=True)
    guard.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL / "scripts" / "secret_guard.py", guard / "secret_guard.py")
    for name in hook_names:
        destination = hooks / name
        shutil.copy2(SKILL / "assets" / name, destination)
        destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    ignore = target.parent / ".gitignore"
    template = (SKILL / "assets" / "gitignore.security").read_text(encoding="utf-8")
    current = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    marker = "# Secret Guard: credentials and local configuration"
    if marker not in current:
        separator = "" if not current or current.endswith("\n") else "\n"
        with ignore.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(separator + template)
    print(translated(
        f"secret-guard installed successfully in {target}",
        f"secret-guard 安装成功：{target}",
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace existing pre-commit/pre-push hooks")
    args = parser.parse_args()
    try:
        install(args.force)
        return 0
    except Exception as exc:
        print(translated(
            f"secret-guard installation failed: {exc}",
            f"secret-guard 安装失败：{exc}",
        ), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
