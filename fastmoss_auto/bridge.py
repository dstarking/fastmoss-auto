"""BrowserSkill transport: argument arrays, bounded calls, owned session cleanup."""
import json
import os
import subprocess
from threading import Event
from .domain import Cancelled


class Bridge:
    def __init__(self, executable="bsk", cancel=None):
        self.executable = executable
        self.cancel = cancel or Event()
        self.session = None

    def run(self, *args, cleanup=False):
        if self.cancel.is_set() and not cleanup:
            raise Cancelled("任务已取消")
        try:
            result = subprocess.run(
                [self.executable, *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("找不到 bsk，请在设置中选择 bsk.exe 或安装 BrowserSkill CLI") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("BrowserSkill 超时，请检查扩展连接和浏览器") from exc
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "BrowserSkill 调用失败").strip())
        if self.cancel.is_set() and not cleanup:
            raise Cancelled("任务已取消")
        return result.stdout.strip()

    def start(self):
        # Retain session ID before checking cancellation, so finally can stop it.
        response = json.loads(self.run("session", "start", "--json", cleanup=True))
        self.session = response["session_id"]
        if self.cancel.is_set():
            raise Cancelled("任务已取消")

    def navigate(self, url):
        self.run("navigate", url, "--session", self.session, "--wait-until", "load", "--timeout", "30s")

    def evaluate(self, js):
        raw = self.run("evaluate", js, "--session", self.session, "--timeout", "30s")
        try:
            value = json.loads(raw)
            if isinstance(value, str):
                value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("BrowserSkill 返回非 JSON 数据，请检查 CLI 版本") from exc
        if not isinstance(value, dict):
            raise RuntimeError("页面返回数据格式异常")
        if value.get("error"):
            raise RuntimeError(str(value["error"]))
        return value

    def close(self):
        if self.session:
            sid, self.session = self.session, None
            self.run("session", "stop", sid, cleanup=True)
