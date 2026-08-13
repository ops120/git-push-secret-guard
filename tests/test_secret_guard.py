import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "secret_guard.py"
INSTALLER = ROOT / "scripts" / "install.py"


def run(cmd, cwd, *, input_text=None, check=True, env=None):
    result = subprocess.run(cmd, cwd=cwd, input=input_text, text=True,
                            capture_output=True, env=env)
    if check and result.returncode:
        raise AssertionError(f"command failed: {cmd}\n{result.stdout}\n{result.stderr}")
    return result


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        run(["git", "init", "-q"], self.repo)
        run(["git", "config", "user.email", "guard@example.invalid"], self.repo)
        run(["git", "config", "user.name", "Guard Test"], self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        run(["git", "add", name], self.repo)

    def scan_staged(self, lang=None):
        env = os.environ.copy()
        if lang:
            env["SECRET_GUARD_LANG"] = lang
        return run([sys.executable, str(SCANNER), "staged"], self.repo,
                   check=False, env=env)

    def commit(self, message):
        run(["git", "commit", "-qm", message], self.repo)
        return run(["git", "rev-parse", "HEAD"], self.repo).stdout.strip()

    def scan_push(self, local_sha, remote_sha="0" * 40):
        line = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
        return run([sys.executable, str(SCANNER), "pre-push"], self.repo,
                   input_text=line, check=False)

    def assertBlocked(self, result, risk):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(risk, result.stdout + result.stderr)

    def test_clean_staged_content_passes(self):
        self.write("app.py", "print('safe')\n")
        self.assertEqual(self.scan_staged().returncode, 0)

    def test_language_override_selects_chinese_messages(self):
        self.write("storymap.db", b"SQLite format 3\x00")
        result = self.scan_staged("zh-CN")
        output = result.stdout + result.stderr
        self.assertIn("已阻断", output)
        self.assertIn("检测到 SQLite 数据库", output)
        self.assertIn("内容尚未推送到远端", output)
        self.assertIn("[sqlite-database]", output)

    def test_language_override_selects_english_messages(self):
        self.write("storymap.db", b"SQLite format 3\x00")
        result = self.scan_staged("en-US")
        output = result.stdout + result.stderr
        self.assertIn("BLOCKED", output)
        self.assertIn("SQLite database detected", output)
        self.assertIn("No content was pushed to the remote", output)
        self.assertNotIn("已阻断", output)

    def test_provider_and_generic_secrets_are_blocked_and_redacted(self):
        minimax_fixture = "eyJhbGciOiJIUzI1NiJ9." + "test-fixture-1234567890"
        deepseek_fixture = "sk-1234567890" + "abcdefghijklmnop"
        generic_fixture = "fixture-secret-value-" + "1234567890"
        fixtures = {
            "minimax": f"MINIMAX_API_KEY='{minimax_fixture}'\n",
            "deepseek": f"DEEPSEEK_API_KEY='{deepseek_fixture}'\n",
            "generic": f"api_key = '{generic_fixture}'\n",
        }
        for index, (kind, secret_line) in enumerate(fixtures.items()):
            with self.subTest(kind=kind):
                run(["git", "reset", "-q"], self.repo)
                self.write(f"secret{index}.txt", secret_line)
                result = self.scan_staged()
                self.assertBlocked(result, "credential")
                self.assertNotIn(secret_line.split("'", 2)[1], result.stdout + result.stderr)

    def test_common_credential_field_styles_are_blocked_and_redacted(self):
        value = "RealLikeValue" + "84920571AbCd"
        fixtures = [
            f"apiKey = '{value}'\n",
            f"ApiKey: '{value}'\n",
            f"API-KEY={value}\n",
            f"api key = {value}\n",
            f"bearer_token = '{value}'\n",
            f"refreshToken: '{value}'\n",
            f"api_secret = '{value}'\n",
            f"appSecret: '{value}'\n",
            f"passwd = '{value}'\n",
            f"pwd: '{value}'\n",
        ]
        for index, content in enumerate(fixtures):
            with self.subTest(content=content.split("=", 1)[0]):
                run(["git", "reset", "-q"], self.repo)
                self.write(f"style{index}.txt", content)
                result = self.scan_staged("en-US")
                self.assertBlocked(result, "credential")
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_wide_token_and_secret_fields_require_long_values(self):
        long_value = "LongGenericValue" + "73910582XyZa"
        self.write("wide.json", '{\n  "token":\n  "' + long_value + '",\n  "secret": "' + long_value + '"\n}\n')
        result = self.scan_staged()
        self.assertBlocked(result, "credential")
        self.assertNotIn(long_value, result.stdout + result.stderr)

    def test_authorization_bearer_is_blocked_and_redacted(self):
        value = "BearerValue" + "62819473QrStUv"
        self.write("headers.txt", f"Authorization: Bearer {value}\n")
        result = self.scan_staged()
        self.assertBlocked(result, "credential")
        self.assertNotIn(value, result.stdout + result.stderr)

    def test_common_credential_placeholders_are_allowed(self):
        content = "\n".join([
            "apiKey = your-api-key",
            "token = example-token",
            "secret = placeholder",
            "pwd = test",
            "Authorization: Bearer YOUR_TOKEN_HERE",
        ])
        self.write("credential-examples.md", content + "\n")
        self.assertEqual(self.scan_staged().returncode, 0)

    def test_high_confidence_bare_sk_and_tp_credentials_are_blocked_and_redacted(self):
        fixtures = {
            "sk": "sk-" + "A8f29dkL03mNz71QpX6vBcDe",
            "tp": "tp-" + "B7g38elM14nOy82RqW5uCdEf",
        }
        for index, (kind, secret) in enumerate(fixtures.items()):
            with self.subTest(kind=kind):
                run(["git", "reset", "-q"], self.repo)
                self.write(f"bare{index}.txt", f"value: {secret}\n")
                result = self.scan_staged("en-US")
                self.assertBlocked(result, "bare-credential")
                self.assertNotIn(secret, result.stdout + result.stderr)

    def test_bare_credential_in_comment_is_blocked(self):
        secret = "tp-" + "C6h47fmN25pQz93SrX4vDeFg"
        self.write("comment.py", f"# temporary token {secret}\n")
        self.assertBlocked(self.scan_staged(), "bare-credential")

    def test_multiline_json_credential_is_blocked(self):
        secret = "tp-" + "D5i56gnO36qRa04TsY3wEfGh"
        self.write("config.json", '{\n  "token":\n  "' + secret + '"\n}\n')
        self.assertBlocked(self.scan_staged(), "bare-credential")

    def test_short_and_placeholder_prefixes_are_allowed(self):
        content = "\n".join([
            "tp-xxxx", "tp-example", "tp-your-key", "tp-1024",
            "sk-xxx", "sk-example", "sk-your-key",
        ])
        self.write("examples.md", content + "\n")
        self.assertEqual(self.scan_staged().returncode, 0)

    def test_custom_bare_prefix_is_supported(self):
        secret = "ak-" + "E4j65hoP47rSb15UtZ2xFgHi"
        self.write("custom.txt", secret + "\n")
        env = os.environ.copy()
        env["SECRET_GUARD_PREFIXES"] = "sk,tp,ak"
        result = run([sys.executable, str(SCANNER), "staged"], self.repo,
                     check=False, env=env)
        self.assertBlocked(result, "bare-credential")

    def test_private_key_is_blocked(self):
        marker = "-----BEGIN " + "PRIVATE KEY-----"
        self.write("key.txt", marker + "\nfixture\n")
        self.assertBlocked(self.scan_staged(), "private-key")

    def test_database_backup_path_is_blocked(self):
        self.write("storymap.db.bak-before-cn-integration", b"not even sqlite")
        self.assertBlocked(self.scan_staged(), "prohibited-path")

    def test_renamed_sqlite_is_blocked_by_magic(self):
        self.write("innocent.bin", b"SQLite format 3\x00" + b"x" * 32)
        self.assertBlocked(self.scan_staged(), "sqlite-database")

    def test_large_file_is_blocked(self):
        self.write("payload.bin", b"x" * (5 * 1024 * 1024 + 1))
        self.assertBlocked(self.scan_staged(), "oversized-file")

    def test_secret_in_earlier_push_commit_is_blocked_after_later_deletion(self):
        fixture = "sk-1234567890" + "abcdefghijklmnop"
        self.write("config.txt", f"DEEPSEEK_API_KEY='{fixture}'\n")
        self.commit("add secret")
        os.remove(self.repo / "config.txt")
        run(["git", "add", "-u"], self.repo)
        head = self.commit("remove secret")
        self.assertBlocked(self.scan_push(head), "credential")

    def test_malformed_push_input_fails_closed(self):
        result = run([sys.executable, str(SCANNER), "pre-push"], self.repo,
                     input_text="broken input\n", check=False)
        self.assertBlocked(result, "scan-error")

    def test_installer_adds_hooks_and_commit_hook_blocks_backup(self):
        result = run([sys.executable, str(INSTALLER)], self.repo, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        git_dir = self.repo / ".git"
        self.assertTrue((git_dir / "hooks" / "pre-commit").is_file())
        self.assertTrue((git_dir / "hooks" / "pre-push").is_file())
        self.assertTrue((git_dir / "secret-guard" / "secret_guard.py").is_file())
        path = self.repo / "storymap.db.bak-before-cn-integration"
        path.write_bytes(b"SQLite format 3\x00")
        run(["git", "add", "-f", path.name], self.repo)
        commit = run(["git", "commit", "-m", "must block"], self.repo, check=False)
        self.assertNotEqual(commit.returncode, 0)
        self.assertIn("prohibited-path", commit.stdout + commit.stderr)

    def test_installer_preserves_existing_hook_without_force(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("existing hook", encoding="utf-8")
        result = run([sys.executable, str(INSTALLER)], self.repo, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "existing hook")

    def test_installer_messages_follow_language_override(self):
        env = os.environ.copy()
        env["SECRET_GUARD_LANG"] = "zh-CN"
        result = run([sys.executable, str(INSTALLER)], self.repo, check=False, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertIn("安装成功", result.stdout)

    def test_pre_push_hook_blocks_secret_hidden_in_earlier_commit(self):
        remote_dir = Path(self.tmp.name + "-remote.git")
        self.addCleanup(lambda: subprocess.run(
            [sys.executable, "-c", "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)", str(remote_dir)]))
        run(["git", "init", "--bare", "-q", str(remote_dir)], self.repo)
        run(["git", "remote", "add", "origin", str(remote_dir)], self.repo)
        secret = self.repo / "credentials.txt"
        fixture = "eyJhbGciOiJIUzI1NiJ9." + "test-fixture-1234567890"
        secret.write_text(f"MINIMAX_API_KEY='{fixture}'\n", encoding="utf-8")
        run(["git", "add", secret.name], self.repo)
        self.commit("add credential")
        secret.unlink()
        run(["git", "add", "-u"], self.repo)
        self.commit("remove credential")
        run([sys.executable, str(INSTALLER)], self.repo)
        pushed = run(["git", "push", "origin", "HEAD:refs/heads/main"], self.repo, check=False)
        self.assertNotEqual(pushed.returncode, 0)
        self.assertIn("credential", pushed.stdout + pushed.stderr)


if __name__ == "__main__":
    unittest.main()
