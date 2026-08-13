# git-push-secret-guard

## Git 提交与推送防泄漏守卫

`git-push-secret-guard` 是一个跨平台 Agent Skill，在 Git 提交和推送到远端之前，自动检测并阻断 API Key、Token、私钥、敏感配置、数据库备份和历史提交中的敏感信息。

它使用同一套确定性扫描器驱动 `pre-commit` 与 `pre-push` hooks：既检查当前暂存内容，也检查本次推送将引入的全部 Git 历史对象。

> 不只是提醒你可能有风险，而是在敏感内容到达远端之前停止提交或推送。

**English:** A cross-platform Agent Skill that blocks credentials, private keys, sensitive configuration, database backups, oversized files, and secrets hidden in pending Git history before commit and push.

## 功能特性

- 通用凭据检测：识别 API Key、Token、Secret、Password、Bearer Token，不依赖特定供应商。
- 裸凭据检测：默认识别高置信度 `sk-`、`tp-` 凭据，包括普通文本、注释和多行 JSON；短占位符不会阻断。
- 私钥检测：识别 PEM 私钥标记及敏感密钥文件。
- 敏感文件拦截：阻止 `.env`、数据库、备份、转储和密钥文件进入仓库。
- SQLite 识别：通过 `SQLite format 3` 文件头识别改名或伪装的数据库。
- 大文件限制：默认阻止超过 5 MiB 的新增 Git 对象。
- 历史扫描：检查本次推送涉及的全部提交，包括“先提交密钥、后删除文件”的情况。
- 失败关闭：Git 对象读取、输入解析或扫描失败时默认阻断，不静默放行。
- 安全输出：显示风险代码、文件路径和提交上下文，但不打印检测到的密钥原文。
- 双语提示：根据系统语言自动显示中文或英文，也可通过环境变量指定。
- 多 Agent 兼容：采用标准 `SKILL.md` 结构，适用于 Codex、Claude Code、OMP 和 OpenCode。

## 目录

- [快速开始](#快速开始)
- [安装到 Agent](#安装到-agent)
- [使用说明](#使用说明)
- [阻断结果](#阻断结果)
- [语言设置](#语言设置)
- [检测范围](#检测范围)
- [数据与安全](#数据与安全)
- [项目结构](#项目结构)
- [测试与验证](#测试与验证)
- [贡献](#贡献)
- [English](#english)

## 快速开始

### 环境要求

- Python 3.10+
- Git
- Windows、Linux 或 macOS

扫描器只使用 Python 标准库，不需要安装第三方 Python 依赖。

## 安装到 Agent

Skill 仓库：<https://github.com/ops120/git-push-secret-guard>

### 1. 用自然语言首次安装

把下面这段话直接发送给 Claude Code、Codex、OMP 或 OpenCode：

```text
安装 https://github.com/ops120/git-push-secret-guard 这个 Skill。
请识别当前 Agent 和操作系统，将完整仓库安装到正确的用户级 Skills 目录，不要只复制 SKILL.md。
安装完成后验证 SKILL.md、scripts 和 assets 均存在，并告诉我实际安装路径。
然后询问我是否要立即为当前 Git 仓库安装 pre-commit 和 pre-push hooks；未经确认不要覆盖已有 hooks。
```

Agent 应自动识别安装目录、执行下载并报告结果。安装完成后重启 Agent，或开启一个新会话，让它重新发现 Skill。

### 2. 用自然语言保护当前仓库

> **关键区别：Skill 负责告诉 Agent 如何操作，Git hooks 才是真正执行拦截的组件。**

在需要保护的仓库中对 Agent 说：

```text
使用 git-push-secret-guard 为当前 Git 仓库安装防泄漏保护。
请先确认当前目录是正确的 Git 仓库，再安装 pre-commit、pre-push hooks 和扫描器。
如果已有同名 hooks，请停止并说明冲突，不要自行覆盖。
安装后运行暂存区扫描，并告诉我安装是否成功、实际文件位置和验证结果。
```

Agent 将调用 Skill 内的安装器并完成：

1. 将当前版本扫描器复制到仓库的 `.git/secret-guard/secret_guard.py`。
2. 安装 `.git/hooks/pre-commit` 和 `.git/hooks/pre-push`。
3. 将安全规则追加到当前仓库的 `.gitignore`。
4. 运行一次扫描并明确报告 `PASS`、`BLOCKED` 或安装错误。

### 3. 用自然语言更新

更新时直接说：

```text
更新 https://github.com/ops120/git-push-secret-guard 这个 Skill。
请找到当前 Agent 已安装的 Skill 目录，以 fast-forward 方式更新到远端最新版本。
更新后，为当前 Git 仓库重新安装 hooks 和扫描器；覆盖前先检查现有 hooks 是否属于 Secret Guard，如包含其他自定义逻辑则停止并提示我。
最后比较 Skill 源扫描器与 .git/secret-guard/secret_guard.py 是否一致，运行完整测试和暂存区扫描，并用中文报告结果。
```

只更新 Skill 目录不会自动更新业务仓库 `.git/secret-guard/` 中的扫描器副本，因此“重新安装当前仓库 hooks 和扫描器”是更新流程的必要步骤。

### 4. 用自然语言验证

需要单独检查时说：

```text
使用 git-push-secret-guard 检查当前仓库的安装状态。
请验证 pre-commit、pre-push 和 .git/secret-guard/secret_guard.py 均存在，确认仓库内扫描器与已安装 Skill 的版本一致，并扫描当前暂存区。
不要创建或提交真实密钥；如需测试，只使用运行时生成的无效测试凭据并在测试后清理。
```

Agent 应明确区分：Skill 已安装、hooks 已安装、扫描通过、扫描阻断和扫描器错误。

### OMP 调用示例

OMP 安装完成并重启后，也可以显式调用：

```text
/skill:git-push-secret-guard 为当前仓库安装 Git 防泄漏保护
```

Git hooks 不会因为 clone 业务仓库而自动安装；每个业务仓库都必须执行上面的第 2 步。

### 手动安装与故障排查

只有 Agent 无法自动完成时才需要手动操作。

| Agent | Windows 用户级安装目录 | Linux/macOS 用户级安装目录 |
|---|---|---|
| Claude Code | `C:\Users\<用户名>\.claude\skills\git-push-secret-guard\` | `~/.claude/skills/git-push-secret-guard/` |
| Codex | `C:\Users\<用户名>\.codex\skills\git-push-secret-guard\` | `~/.codex/skills/git-push-secret-guard/` |
| OMP | `C:\Users\<用户名>\.omp\skills\git-push-secret-guard\` | `~/.omp/skills/git-push-secret-guard/` |
| OpenCode | `C:\Users\<用户名>\.agents\skills\git-push-secret-guard\` | `~/.agents/skills/git-push-secret-guard/` |

以 Claude Code 为例：

```bash
git clone https://github.com/ops120/git-push-secret-guard.git ~/.claude/skills/git-push-secret-guard
cd /path/to/your-repository
python ~/.claude/skills/git-push-secret-guard/scripts/install.py
```

更新并重新部署当前仓库扫描器：

```bash
git -C ~/.claude/skills/git-push-secret-guard pull --ff-only
cd /path/to/your-repository
python ~/.claude/skills/git-push-secret-guard/scripts/install.py --force
python .git/secret-guard/secret_guard.py staged
```

如果现有 hooks 含有其他逻辑，不要使用 `--force`，应手动集成 Secret Guard 调用。

## 使用说明

安装 hooks 后，日常仍使用标准 Git 命令：

```bash
git add <files>
git commit -m "your message"
git push origin HEAD:refs/heads/<branch>
```

执行 `git commit` 时，`pre-commit` 自动检查暂存区；执行 `git push` 时，`pre-push` 自动检查本次推送将引入远端的全部提交和文件对象。

### 在 Agent 中调用

Codex：

```text
使用 $git-push-secret-guard 检查并安全推送当前分支
```

Claude Code：

```text
/git-push-secret-guard 检查当前仓库并安装保护
```

OMP：

```text
/skill:git-push-secret-guard 检查所有待推送提交
```

OpenCode：

```text
使用 git-push-secret-guard skill 检查待推送历史
```

### 手动扫描暂存区

```bash
python <skill-directory>/scripts/secret_guard.py staged
```

## 阻断结果

中文系统中的阻断示例：

```text
secret-guard：已阻断
- [prohibited-path] storymap.db.bak-before-cn-integration @ commit 4c45a05: 检测到数据库、备份、密钥或环境配置文件
- [sqlite-database] storymap.db.bak-before-cn-integration @ commit 4c45a05: 检测到 SQLite 数据库
- [oversized-file] storymap.db.bak-before-cn-integration @ commit 4c45a05: 文件大小超过限制
结果：内容尚未推送到远端。
建议：从所有受影响的提交中删除相关内容并重新扫描。
```

英文系统中的通过示例：

```text
secret-guard: PASS
All pending content passed the security scan.
```

风险代码保持固定英文，便于 CI 和日志工具解析：

| 风险代码 | 含义 |
|---|---|
| `credential` | 检测到 API Key、Token、密码或 Secret |
| `bare-credential` | 检测到高置信度的裸 `sk-`、`tp-` 或自定义前缀凭据 |
| `private-key` | 检测到私钥 |
| `prohibited-path` | 检测到禁止提交的敏感路径或文件类型 |
| `sqlite-database` | 通过文件头识别到 SQLite 数据库 |
| `oversized-file` | 文件超过 5 MiB 限制 |
| `scan-error` | 扫描器或 Git 对象读取失败，默认阻断 |

当扫描器阻断时，`git push` 返回非零退出码，远端不会收到本次推送。扫描通过后，Git 仍可能因网络、认证或分支保护失败；最终推送状态以 Git 输出和远端分支 SHA 为准。

## 语言设置

程序按以下顺序选择语言：

1. `SECRET_GUARD_LANG` 环境变量。
2. 操作系统区域语言。
3. 非中文环境默认英文。

Windows PowerShell：

```powershell
$env:SECRET_GUARD_LANG = "zh-CN" # 或 en-US
```

Linux/macOS：

```bash
export SECRET_GUARD_LANG=zh-CN   # or en-US
```

可通过逗号分隔的环境变量扩展裸凭据前缀。默认值为 `sk,tp`：

```powershell
$env:SECRET_GUARD_PREFIXES = "sk,tp,ak,mycorp"
```

```bash
export SECRET_GUARD_PREFIXES=sk,tp,ak,mycorp
```

为降低误报，裸凭据后缀必须至少 20 位并同时包含字母和数字。`tp-xxxx`、`tp-example`、`tp-your-key` 和 `tp-1024` 等短值或占位符不会阻断。

## 检测范围

默认阻止以下内容：

- `.env`、`.env.*`（允许 `.env.example` 模板被 `.gitignore` 规则排除）。
- `*.db`、`*.db-*`、`*.sqlite`、`*.sqlite3`。
- `*.bak`、`*.bak-*`、`*.backup`、`*.dump`。
- `*.pem`、`*.key` 和私钥正文。
- 通用凭据字段：`api_key`、`api-key`、`apiKey`、`ApiKey`、`API KEY`。
- Token 字段：`access_token`、`authToken`、`bearer_token`、`refreshToken`，以及高置信度的 `token`。
- Secret 字段：`client_secret`、`apiSecret`、`appSecret`，以及高置信度的 `secret`。
- 密码字段：`password`、`passwd`、`pwd`。
- `Authorization: Bearer ...` 请求头。
- 普通赋值、环境变量、JSON 和多行 JSON 格式。
- 后缀至少 20 位且同时包含字母和数字的裸 `sk-`、`tp-` 或自定义前缀凭据。
- 带 SQLite 文件头的任意扩展名文件。
- 超过 5 MiB 的 Git blob。

## 数据与安全

- 所有扫描在本机完成，不把源码或扫描结果发送给外部服务。
- 输出不会打印匹配到的完整凭据值。
- `.gitignore` 只是第一道防线；即使使用 `git add -f`，`pre-commit` 仍会阻断敏感文件。
- `pre-push` 会检查待推送历史，而不只检查当前工作区。
- 不要使用 `git commit --no-verify` 或 `git push --no-verify` 绕过保护。
- Skill 和本地 hooks 只保护安装过的当前 clone。团队强制执行还需要 CI 必需检查、分支保护和托管平台的 Push Protection。

> 如果凭据已经到达远端，应先在服务商处撤销或轮换密钥，再清理 Git 历史。删除文件或执行 `git filter-repo` 不能让已泄漏的密钥重新安全。

## 项目结构

```text
git-push-secret-guard/
├── SKILL.md                    # Agent Skill 指令
├── README.md                   # 项目说明
├── agents/
│   └── openai.yaml            # Codex UI 元数据
├── assets/
│   ├── gitignore.security     # 安全忽略规则
│   ├── pre-commit             # 提交前 hook
│   └── pre-push               # 推送前 hook
├── scripts/
│   ├── install.py             # 当前 Git 仓库安装器
│   └── secret_guard.py        # 确定性扫描器
└── tests/
    └── test_secret_guard.py   # 端到端测试
```

## 测试与验证

在项目根目录运行：

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

- 安全内容正常通过。
- MiniMax、DeepSeek 和通用凭据阻断与脱敏。
- 私钥阻断。
- 数据库和备份路径阻断。
- 改名 SQLite 文件识别。
- 大文件阻断。
- 较早提交中的密钥在后续删除后仍被推送门禁发现。
- `git add -f` 绕过 `.gitignore` 后仍被 hook 阻断。
- 真实 bare remote 推送阻断。
- 扫描错误时失败关闭。
- 中文与英文输出。

## 贡献

欢迎通过 Issue 报告误报、漏报和平台兼容问题，也欢迎提交 Pull Request 扩展供应商凭据模式、Git 平台集成及测试场景。

提交修改前请运行完整测试，并确保测试数据只使用无效的示例凭据。

## English

`git-push-secret-guard` is a cross-platform Agent Skill that prevents sensitive information from reaching Git remotes. It installs a deterministic scanner behind `pre-commit` and `pre-push` hooks and checks both staged content and every Git object introduced by a push.

### Key features

- Detects provider-independent API keys, tokens, secrets, passwords, and Authorization Bearer values across snake_case, kebab-case, camelCase, PascalCase, environment variables, JSON, and multiline JSON.
- Detects high-confidence bare `sk-` and `tp-` credentials in text, comments, and multiline JSON while allowing short placeholders.
- Detects PEM private keys and sensitive configuration files.
- Blocks databases, backup files, dumps, key files, and blobs larger than 5 MiB.
- Identifies renamed SQLite databases by their file signature.
- Detects secrets committed and deleted in earlier pending commits.
- Fails closed when scanning cannot be completed.
- Redacts secret values from reports.
- Displays Chinese or English based on the system locale.
- Uses the portable Agent Skills layout supported by Codex, Claude Code, OMP, and OpenCode.

### Quick start

Run this from the Git repository you want to protect:

```bash
python <skill-directory>/scripts/install.py
```

Then use Git normally:

```bash
git add <files>
git commit -m "your message"
git push origin HEAD:refs/heads/<branch>
```

The installed hooks run automatically. A blocked scan returns a non-zero exit code and explains the risk without printing the detected credential.

### Important security note

Local hooks protect only clones where they are installed and can technically be bypassed with `--no-verify`. Teams should also enable required CI checks, protected branches, and server-side push protection.

If a credential has already reached a remote, revoke or rotate it before rewriting Git history. History cleanup does not make an exposed credential safe again.

---

在敏感信息到达远端之前，让 Git 停下来。

Stop Git before sensitive information reaches the remote.
