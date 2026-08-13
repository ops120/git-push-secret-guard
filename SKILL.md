---
name: git-push-secret-guard
description: Use when committing or pushing Git changes, preparing a repository for safe collaboration, checking pending history for leaked credentials, or responding to an API key, token, private key, database, backup, or sensitive-file exposure.
---

# Git Push Secret Guard

Prevent secrets from reaching a remote. Treat a successful deterministic scan as mandatory evidence, never as a best-effort suggestion.

## User Language

Display user-facing scanner and installer messages in the operating-system language. Use Chinese for `zh` locales and English otherwise. Preserve stable English risk codes such as `credential`, `sqlite-database`, and `scan-error` for CI parsing.

Allow an explicit override:

```powershell
$env:SECRET_GUARD_LANG = "zh-CN" # or en-US
```

```bash
export SECRET_GUARD_LANG=zh-CN   # or en-US
```

## Install Once Per Repository

Run from the repository root:

```powershell
python <skill-directory>/scripts/install.py
```

If hooks already exist, preserve them and integrate the commands manually. Use `--force` only with explicit user approval because it replaces hooks.

## Mandatory Workflow

1. Before committing, run:

   ```powershell
   python <skill-directory>/scripts/secret_guard.py staged
   ```

2. Let the installed `pre-commit` hook repeat the staged scan.
3. Immediately before every push, construct standard pre-push input and run:

   ```powershell
   $localSha = git rev-parse HEAD
   $remoteSha = git rev-parse --verify refs/remotes/origin/<branch> 2>$null
   if (-not $remoteSha) { $remoteSha = '0000000000000000000000000000000000000000' }
   "refs/heads/<branch> $localSha refs/heads/<branch> $remoteSha" |
     python <skill-directory>/scripts/secret_guard.py pre-push
   ```

4. Push only after `secret-guard: PASS`, using an explicit remote and refspec:

   ```powershell
   git push origin HEAD:refs/heads/<branch>
   ```

The installed `pre-push` hook repeats the scan using Git's exact ref-update input.

## Blocking Policy

Block provider-independent credential assignments, Authorization Bearer values, high-confidence bare `sk-`/`tp-` credentials, private keys, `.env` files, databases/backups, disguised SQLite blobs, files over 5 MiB, and secrets present in any commit introduced by the push. Recognize API key, token, secret, password, `passwd`, and `pwd` fields across snake_case, kebab-case, camelCase, PascalCase, environment variables, JSON, and multiline JSON. Bare credentials require at least 20 suffix characters containing both letters and digits; allow short placeholders such as `tp-xxxx` and `sk-example`. Extend prefixes with `SECRET_GUARD_PREFIXES=sk,tp,ak`. Block when Git object enumeration, input parsing, or file reading fails. Never bypass with `--no-verify`.

Do not print secret values. Report only risk type, path, commit context, and remediation.

## Remediation

For unpushed content, remove the file from the index, move credentials to environment variables or a secret manager, and amend/rewrite every affected local commit before rescanning.

If content reached any remote, assume compromise:

1. Revoke or rotate the credential at MiniMax, DeepSeek, or the relevant provider first.
2. Stop collaborators from pushing and identify all affected refs, forks, PRs, and caches.
3. Remove the material with `git filter-repo`, force-push only with explicit authorization, and have collaborators re-clone.
4. Contact the hosting provider when cached views or fork references remain.

History rewriting does not make an exposed key safe again.

## Common Mistakes

| Mistake | Required response |
|---|---|
| Scan only the working tree | Scan staged blobs and every object introduced by the push. |
| Trust `.gitignore` alone | Keep hooks; `git add -f` bypasses ignore rules. |
| Check extensions only | Detect SQLite magic bytes and size as independent signals. |
| Delete the file in a later commit | Rewrite the earlier commit; push scanning still detects it. |
| Continue after scanner failure | Fail closed and repair the scanner or Git state. |
| Clean history but retain the key | Revoke or rotate the key before cleanup. |
