"""
B-612 公网网关：一个端口同时给页面和 WebSocket，方便一条隧道打通两者。

  GET  /*                          -> game/ 里的静态文件（含 index.html）
  GET  /health                     -> {"ok":true,...} 探活
  GET  /ws  (Upgrade: websocket)   -> 原样转发到本机 roomserver 的 18201

为什么要它：浏览器从 https 页面只能连 wss://，而隧道（cloudflared）一次只能映射
一个本地端口。把静态页和 WS 放在同一个端口后，公网 https 地址就是游戏地址，
同源默认连 wss://<公网地址>/ws，不用再填地址。

启动顺序：先 python roomserver.py，再 python gateway.py，最后 cloudflared。
环境变量：GATEWAY_PORT(18300) WS_HOST(127.0.0.1) WS_PORT(18201) PUBLIC_URL(可选，展示用)
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

BASE = Path(__file__).resolve().parent
GAME_DIR = (BASE.parent / "game").resolve()
PORT = int(os.environ.get("GATEWAY_PORT", "18300"))
WS_HOST = os.environ.get("WS_HOST", "127.0.0.1")
WS_PORT = int(os.environ.get("WS_PORT", "18201"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip()

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
}


def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} [gateway] {msg}", flush=True)


def http_response(status, body, ctype="text/plain; charset=utf-8"):
    reason = "OK" if status == 200 else ("Not Found" if status == 404 else "Bad Request")
    head = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {ctype}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin-1")
    return head + body


async def read_head(reader):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            return data
        data += chunk
        if len(data) > 65536:
            return data
    return data


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def serve_file(target):
    path = unquote(urlparse(target).path)
    rel = path.lstrip("/") or "index.html"
    fp = (GAME_DIR / rel).resolve()
    if str(fp).startswith(str(GAME_DIR)) and fp.is_file():
        body = fp.read_bytes()
        return http_response(200, body, MIME.get(fp.suffix.lower(), "application/octet-stream"))
    if rel == "index.html":
        return http_response(404, b"game/index.html not found; run build first")
    return http_response(404, b"404")


async def write_all(writer, data):
    """大文件分块写，最后等缓冲区真正刷完，避免隧道侧收到半截页面"""
    for i in range(0, len(data), 65536):
        writer.write(data[i:i + 65536])
        await writer.drain()


async def handle(reader, writer):
    try:
        head = await read_head(reader)
        if not head:
            return
        try:
            method, target, _ver = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
        except Exception:
            writer.write(http_response(400, b"bad request"))
            await writer.drain()
            return

        if method == "GET" and b"upgrade: websocket" in head.lower():
            up_r, up_w = await asyncio.open_connection(WS_HOST, WS_PORT)
            up_w.write(head)
            await up_w.drain()
            await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))
            return

        if method != "GET":
            writer.write(http_response(400 if method != "HEAD" else 404, b"only GET"))
            await writer.drain()
            return

        if urlparse(target).path.rstrip("/") == "/health":
            body = json.dumps({"ok": True, "gateway": PORT, "ws": f"{WS_HOST}:{WS_PORT}",
                               "publicUrl": PUBLIC_URL}).encode()
            payload = http_response(200, body, "application/json; charset=utf-8")
        else:
            payload = await serve_file(target)
        await write_all(writer, payload)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except Exception as e:
        log(f"conn err: {e!r}")
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    srv = await asyncio.start_server(handle, "0.0.0.0", PORT)
    log(f"listening :{PORT}  static={GAME_DIR}  ws -> {WS_HOST}:{WS_PORT}")
    if PUBLIC_URL:
        log(f"public url: {PUBLIC_URL}")
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
