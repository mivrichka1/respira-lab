"""Start both Respira Lab services on localhost without Docker."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

HOST = "127.0.0.1"
ROOT = Path(__file__).resolve().parent


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Порт должен быть от 1 до 65535.")
    return port


def wait_for_sse(process, port):
    http = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with http.open(f"http://{HOST}:{port}/health", timeout=0.5) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.1)
    return False


def stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    parser = argparse.ArgumentParser(description="Запуск Respira Lab без Docker")
    parser.add_argument("--web-port", type=port_number, default=8512)
    parser.add_argument("--sse-port", type=port_number, default=8002)
    args = parser.parse_args()
    if args.web_port == args.sse_port:
        parser.error("Веб-приложению и SSE нужны разные порты.")

    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        parser.error("Соберите интерфейс: npm --prefix frontend ci и npm --prefix frontend run build.")

    for port in (args.web_port, args.sse_port):
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                parser.error(f"Порт {port} недоступен. Укажите другой порт через --web-port или --sse-port.")

    processes = []
    try:
        sse = subprocess.Popen(
            [sys.executable, "-m", "respira.server", "sse", "--port", str(args.sse_port)],
            cwd=ROOT,
        )
        processes.append(sse)
        if not wait_for_sse(sse, args.sse_port):
            print("Не удалось запустить SSE. Проверьте вывод выше.", file=sys.stderr)
            return 1

        env = dict(os.environ, RESPIRA_SSE_URL=f"http://{HOST}:{args.sse_port}/sse")
        web = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "respira.web:app", "--host", HOST, "--port", str(args.web_port)],
            cwd=ROOT,
            env=env,
        )
        processes.append(web)
        print(f"Respira Lab: http://{HOST}:{args.web_port}/  |  Ctrl+C для остановки", flush=True)
        return web.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            stop(process)


if __name__ == "__main__":
    raise SystemExit(main())
