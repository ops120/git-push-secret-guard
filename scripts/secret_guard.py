#!/usr/bin/env python3
"""Fail-closed secret and prohibited-file scanner for Git commits and pushes."""

from __future__ import annotations

import re
import locale
import os
import subprocess
import sys
from dataclasses import dataclass

MAX_BYTES = 5 * 1024 * 1024
ZERO_SHA = "0" * 40
SQLITE_MAGIC = b"SQLite format 3\x00"

MESSAGES = {
    "en": {
        "pass": "secret-guard: PASS\nAll pending content passed the security scan.",
        "blocked": "secret-guard: BLOCKED",
        "prohibited": "database, backup, key, or environment file detected",
        "oversized": "file size {size} bytes exceeds the {limit}-byte limit",
        "sqlite": "SQLite database detected",
        "private": "private key detected",
        "credential": "credential-like assignment detected; value redacted",
        "result": "Result: No content was pushed to the remote.",
        "action": "Action: Remove the content from every affected commit and scan again. If it reached any remote, revoke or rotate the credential first, then clean history.",
        "error": "secret-guard: BLOCKED\n- [scan-error] Security scan failed: {error}\nResult: Push was not attempted by secret-guard.",
    },
    "zh": {
        "pass": "secret-guard：检查通过\n所有待提交或待推送内容均已通过安全扫描。",
        "blocked": "secret-guard：已阻断",
        "prohibited": "检测到数据库、备份、密钥或环境配置文件",
        "oversized": "文件大小为 {size} 字节，超过 {limit} 字节限制",
        "sqlite": "检测到 SQLite 数据库",
        "private": "检测到私钥",
        "credential": "检测到疑似凭据，敏感值已隐藏",
        "result": "结果：内容尚未推送到远端。",
        "action": "建议：从所有受影响的提交中删除相关内容并重新扫描。如果内容曾到达远端，请先撤销或轮换凭据，再清理历史。",
        "error": "secret-guard：已阻断\n- [scan-error] 安全扫描失败：{error}\n结果：secret-guard 未尝试推送。",
    },
}


def language() -> str:
    requested = os.environ.get("SECRET_GUARD_LANG", "").strip()
    if not requested:
        requested = (locale.getlocale()[0] or "")
    normalized = requested.lower().replace("_", "-")
    return "zh" if normalized == "zh" or normalized.startswith("zh-") else "en"


def message(key: str, **values: object) -> str:
    return MESSAGES[language()][key].format(**values)

PROHIBITED = re.compile(
    r"(^|/)(?:\.env(?:\..+)?|[^/]*\.(?:db|sqlite3?|bak|backup|dump|pem|key)(?:[.\-_].*)?)$",
    re.IGNORECASE,
)
PRIVATE_KEY = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
PROVIDER = re.compile(
    rb"(?i)(?:minimax|deepseek)[_a-z0-9-]*(?:api[_-]?key|token|secret)"
    rb"\s*[:=]\s*['\"]?([A-Za-z0-9._\-/+=]{16,})"
)
GENERIC = re.compile(
    rb"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)"
    rb"\s*[:=]\s*['\"]?([A-Za-z0-9._\-/+=]{16,})"
)


@dataclass(frozen=True)
class Finding:
    risk: str
    path: str
    context: str
    detail: str


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], input=input_bytes, capture_output=True)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def inspect_blob(path: str, data: bytes, context: str) -> list[Finding]:
    findings: list[Finding] = []
    normalized = path.replace("\\", "/")
    if PROHIBITED.search(normalized):
        findings.append(Finding("prohibited-path", path, context, message("prohibited")))
    if len(data) > MAX_BYTES:
        findings.append(Finding("oversized-file", path, context,
                                message("oversized", size=len(data), limit=MAX_BYTES)))
    if data.startswith(SQLITE_MAGIC):
        findings.append(Finding("sqlite-database", path, context, message("sqlite")))
    if PRIVATE_KEY.search(data):
        findings.append(Finding("private-key", path, context, message("private")))
    if PROVIDER.search(data) or GENERIC.search(data):
        findings.append(Finding("credential", path, context, message("credential")))
    return findings


def staged_blobs():
    raw = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    for item in raw.split(b"\0"):
        if not item:
            continue
        path = item.decode("utf-8", "surrogateescape")
        yield path, git("show", f":{path}"), "index"


def push_blobs(stdin_text: str):
    seen: set[tuple[str, str]] = set()
    lines = [line for line in stdin_text.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("pre-push input is empty")
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            raise RuntimeError("malformed pre-push input")
        local_ref, local_sha, remote_ref, remote_sha = fields
        if local_sha == ZERO_SHA:  # deletion pushes contain no new objects
            continue
        rev_args = [local_sha] if remote_sha == ZERO_SHA else [local_sha, f"^{remote_sha}"]
        commits = git("rev-list", *rev_args).decode().splitlines()
        for commit in commits:
            records = git("ls-tree", "-r", "-z", commit).split(b"\0")
            for record in records:
                if not record:
                    continue
                meta, path_raw = record.split(b"\t", 1)
                _mode, obj_type, oid = meta.decode().split()
                if obj_type != "blob":
                    continue
                path = path_raw.decode("utf-8", "surrogateescape")
                key = (oid, path)
                if key in seen:
                    continue
                seen.add(key)
                yield path, git("cat-file", "blob", oid), f"commit {commit[:12]} ({local_ref} -> {remote_ref})"


def report(findings: list[Finding]) -> int:
    if not findings:
        print(message("pass"))
        return 0
    print(message("blocked"))
    for finding in findings:
        print(f"- [{finding.risk}] {finding.path} @ {finding.context}: {finding.detail}")
    print(message("result"))
    print(message("action"))
    return 1


def main() -> int:
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {"staged", "pre-push"}:
            raise RuntimeError("usage: secret_guard.py staged|pre-push")
        blobs = staged_blobs() if sys.argv[1] == "staged" else push_blobs(sys.stdin.read())
        findings = [finding for path, data, context in blobs
                    for finding in inspect_blob(path, data, context)]
        return report(findings)
    except Exception as exc:
        print(message("error", error=exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
