from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from prompt_architect.web.app import create_app
from prompt_architect.web.paths import AppPaths


class DesktopBridge:
    def __init__(self, paths: AppPaths, app) -> None:
        self.paths = paths
        self.app = app

    @staticmethod
    def _window():
        import webview

        return webview.windows[0]

    def choose_files(self) -> list[str]:
        import webview

        dialog = getattr(getattr(webview, "FileDialog", object), "OPEN", None)
        dialog = dialog or getattr(webview, "OPEN_DIALOG")
        result = self._window().create_file_dialog(dialog, allow_multiple=True)
        return [str(item) for item in (result or [])]

    def choose_directory(self) -> str | None:
        import webview

        dialog = getattr(getattr(webview, "FileDialog", object), "FOLDER", None)
        dialog = dialog or getattr(webview, "FOLDER_DIALOG")
        result = self._window().create_file_dialog(dialog)
        if not result:
            return None
        return str(result[0])

    def open_run_folder(self, run_id: str) -> bool:
        detail = self.app.state.runs.get(run_id)
        if detail is None:
            return False
        target = Path(detail.output_dir).resolve()
        if not target.is_relative_to(self.paths.runs.resolve()):
            return False
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
            return True
        return False


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _show_error(message: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Prompt Architect 启动失败", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> None:
    paths = AppPaths.default()
    log_path = paths.logs / "desktop.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        import uvicorn
        import webview

        if "--smoke-test" in sys.argv:
            app = create_app(paths=paths, desktop=True)
            if not app.routes or not callable(getattr(webview, "create_window", None)):
                raise RuntimeError("桌面运行时自检失败")
            return

        port = _available_port()
        app = create_app(paths=paths, desktop=True)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True, name="prompt-architect-api")
        thread.start()
        url = f"http://127.0.0.1:{port}"
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"{url}/api/v1/health", timeout=0.25) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("本地服务未能在预期时间内启动")

        bridge = DesktopBridge(paths, app)
        webview.create_window(
            "Prompt Architect",
            url,
            js_api=bridge,
            width=1400,
            height=900,
            min_size=(1024, 700),
        )
        webview.start()
        server.should_exit = True
        thread.join(timeout=5)
    except Exception as exc:  # desktop boundary: present a useful error instead of a traceback window
        logging.exception("Desktop startup failed")
        _show_error(f"应用未能启动。\n\n{exc}\n\n日志：{log_path}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
