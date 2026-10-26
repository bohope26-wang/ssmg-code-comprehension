from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from app.main import app


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_local_env() -> None:
    local_env = app_dir() / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=False)
        return
    load_dotenv(override=False)


def choose_port(host: str, preferred_port: int) -> int:
    if is_port_available(host, preferred_port):
        return preferred_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def open_browser_when_ready(url: str, host: str, port: int) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.3)
    webbrowser.open(url)


def main() -> None:
    os.chdir(app_dir())
    load_local_env()

    host = os.getenv("LLM_PARTITION_HOST", DEFAULT_HOST)
    preferred_port = int(os.getenv("LLM_PARTITION_PORT", str(DEFAULT_PORT)))
    port = choose_port(host, preferred_port)
    url = f"http://{host}:{port}/"

    threading.Thread(target=open_browser_when_ready, args=(url, host, port), daemon=True).start()
    print(f"LLM Function Partition is running at {url}")
    print("Close this window to stop the local service.")
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
