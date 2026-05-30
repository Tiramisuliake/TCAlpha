"""开发入口（PyCharm 右键 Run 即启）。

行为：
  1. 在 8001..8050 范围扫描第一个干净端口（绕开 Windows tcpip.sys socket 泄漏）
  2. 把端口写到 frontend/.dev-port，Vite 启动时读取，前后端自动对齐
  3. 调 uvicorn 启动 app.main:app，热重载，监听 127.0.0.1

生产环境不走这里——生产用 `uvicorn app.main:app --host 0.0.0.0 ...`。

PyCharm 配置：
  - Interpreter 指向 backend/.venv/Scripts/python.exe
  - Working directory = backend/
  - 右键此文件 → Run "run"
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

# Windows 控制台 / PyCharm 终端默认编码可能是 GBK，强制 UTF-8 让中文不乱码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError:
        # 老 Python（< 3.7）没有 reconfigure，忽略
        pass


PORT_START = 8000
PORT_RANGE = 50
BIND_HOST = "127.0.0.1"

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
PORT_FILE = REPO_ROOT / "frontend" / ".dev-port"


def is_port_free(port: int) -> bool:
    """尝试 bind；只有真正可用才返回 True，绕开 Get-NetTCPConnection 仍能看见的幽灵 socket。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 不设 SO_REUSEADDR：要的是"完全无人占用"
        sock.bind((BIND_HOST, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_free_port() -> int:
    # 允许通过 BACKEND_PORT 锁定端口
    override = os.environ.get("BACKEND_PORT")
    if override:
        try:
            p = int(override)
            if is_port_free(p):
                print(f"[run] BACKEND_PORT={p} 锁定生效")
                return p
            print(f"[run] BACKEND_PORT={p} 被占用，回退到自动扫描")
        except ValueError:
            print(f"[run] BACKEND_PORT={override!r} 不是合法整数，忽略")

    for port in range(PORT_START, PORT_START + PORT_RANGE):
        if is_port_free(port):
            return port
    raise SystemExit(
        f"[run] {PORT_START}..{PORT_START + PORT_RANGE - 1} 范围无可用端口；"
        "建议重启电脑清 tcpip.sys 幽灵 socket"
    )


def write_port_file(port: int) -> None:
    try:
        PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORT_FILE.write_text(str(port), encoding="utf-8")
        print(f"[run] 端口写入 {PORT_FILE}（vite 自动读取）")
    except OSError as e:
        print(f"[run] ⚠ 写入 {PORT_FILE} 失败：{e}")


def main() -> None:
    port = find_free_port()
    print()
    print("=" * 56)
    print(f" ▶ TCAlpha 后端开发入口")
    print(f"   API     → http://{BIND_HOST}:{port}")
    print(f"   Swagger → http://{BIND_HOST}:{port}/docs")
    print(f"   按 Ctrl+C 停止")
    print("=" * 56)
    print()

    write_port_file(port)

    # 延迟 import：避免脚本一启动就拉起 SQLAlchemy 引擎
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=BIND_HOST,
        port=port,
        reload=True,
        reload_dirs=[str(BACKEND_DIR / "app")],
    )


if __name__ == "__main__":
    # 让 `python backend/run.py` 也能找到 app 包
    sys.path.insert(0, str(BACKEND_DIR))
    main()
