"""
B-612 联机房间服务（正式版，WebSocket 路线）

一个进程同时提供：
  18201  WebSocket /ws   —— 房间广播（位置 / 朝向 / 角色 / 换装 / 动作）
  18100  静态文件         —— 直接打开 http://<host>:18100/ 就是游戏
  18200  HTTP API         —— /health /stats /drop（/drop 用于断线重连自测）

依赖：websockets（3.x / 17.x 均可）、其余全是标准库。
启动：python roomserver.py
环境变量：
  WS_PORT / STATIC_PORT / API_PORT  端口覆盖
  ORIGIN_ALLOW  逗号分隔的 Origin 白名单；不设 = 全部放行
  CORS_ORIGIN   HTTP API 的 Access-Control-Allow-Origin，默认 *
"""
import asyncio
import json
import os
import socket
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

BASE = Path(__file__).resolve().parent
GAME_DIR = (BASE.parent / "game").resolve()

API_PORT = int(os.environ.get("API_PORT", "18200"))
WS_PORT = int(os.environ.get("WS_PORT", "18201"))
STATIC_PORT = int(os.environ.get("STATIC_PORT", "18100"))
ORIGIN_ALLOW = os.environ.get("ORIGIN_ALLOW", "").strip()
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

ROOMS = {}           # room -> {peer_id: Peer}
PEER_SEQ = 0
_lock = threading.Lock()
LOOP = None


def now_ms():
    return int(time.time() * 1000)


def log(tag, msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} [{tag}] {msg}", flush=True)


class Peer:
    __slots__ = ("pid", "room", "ws", "origin", "joined")

    def __init__(self, pid, room, ws, origin):
        self.pid = pid
        self.room = room
        self.ws = ws
        self.origin = origin
        self.joined = time.time()


async def broadcast(room, payload, exclude=None):
    # 必须发 str（文本帧）。发 bytes 时浏览器 ev.data 是 Blob，前端 JSON.parse 会静默失败。
    dead = []
    for pid, peer in list(ROOMS.get(room, {}).items()):
        if pid == exclude:
            continue
        try:
            await peer.ws.send(payload)
        except Exception:
            dead.append(pid)
    for pid in dead:
        ROOMS.get(room, {}).pop(pid, None)


def process_request(connection, request):
    """WS 端口上顺带提供 /health /stats，便于跨域探活。"""
    if request.path.startswith("/ws"):
        return None
    u = urlparse(request.path)
    if u.path.rstrip("/") in ("", "/health"):
        body = json.dumps({"ok": True, "serverTime": now_ms(),
                           "rooms": {r: len(p) for r, p in ROOMS.items()}}).encode()
        status = 200
    elif u.path.rstrip("/") == "/stats":
        body = json.dumps({"rooms": {r: {pid: {"age": round(time.time() - p.joined, 1)}
                                          for pid, p in peers.items()}
                                     for r, peers in ROOMS.items()}}).encode()
        status = 200
    else:
        body = json.dumps({"ok": False, "err": "not found"}).encode()
        status = 404
    hdrs = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Server", "b612-room"),
        ("Access-Control-Allow-Origin", CORS_ORIGIN),
    ]
    return Response(status, "OK" if status == 200 else "Not Found", Headers(hdrs), body)


async def handler(ws):
    global PEER_SEQ
    parsed = urlparse(ws.request.path)
    if not parsed.path.rstrip("/").endswith("/ws"):
        await ws.close(code=1008, reason="unknown path")
        return
    qs = parse_qs(parsed.query)
    room = (qs.get("room") or ["r1"])[0][:64] or "r1"
    name = (qs.get("name") or [""])[0][:32]
    origin = ws.request.headers.get("Origin", "-")

    PEER_SEQ += 1
    pid = f"{PEER_SEQ:04d}"
    peer = Peer(pid, room, ws, origin)
    ROOMS.setdefault(room, {})[pid] = peer
    log("join", f"room={room} peer={pid} name={name} origin={origin}")

    try:
        await ws.send(json.dumps({
            "t": "welcome", "id": pid, "room": room,
            "peers": [p for p in ROOMS[room] if p != pid],
            "serverTime": now_ms(),
        }))
        await broadcast(room, json.dumps({"t": "peer-join", "id": pid, "name": name}), exclude=pid)

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            t = msg.get("t")

            # state = 位置/朝向；world = 地形（坑/土块/树苗/花）。都按房间原样转发。
            if t in ("state", "world"):
                msg["id"] = pid
                msg["srx"] = now_ms()
                await broadcast(room, json.dumps(msg), exclude=pid)

            elif t == "ping":
                await ws.send(json.dumps({"t": "pong", "c": msg.get("c"), "serverTime": now_ms()}))

            elif t == "dropme":
                log("drop", f"room={room} peer={pid} 主动断链")
                peer.ws.transport.abort()
                break

            elif t == "bye":
                break

    except Exception:
        log("err", traceback.format_exc(limit=2).replace("\n", " | "))
    finally:
        ROOMS.get(room, {}).pop(pid, None)
        try:
            await broadcast(room, json.dumps({"t": "peer-leave", "id": pid}))
        except Exception:
            pass
        log("leave", f"room={room} peer={pid}")


def cors_headers(h):
    h.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "content-type")
    h.send_header("Vary", "Origin")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "b612-room/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        cors_headers(self)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json({"ok": True, "serverTime": now_ms(),
                               "rooms": {r: len(p) for r, p in ROOMS.items()}})
        if u.path == "/stats":
            return self._json({"rooms": {r: {pid: {"age": round(time.time() - p.joined, 1)}
                                              for pid, p in peers.items()}
                                         for r, peers in ROOMS.items()}})
        if u.path == "/drop":
            room = parse_qs(u.query).get("room", ["r1"])[0]
            peers = list(ROOMS.get(room, {}).values())

            def _abort():
                for p in peers:
                    try:
                        p.ws.transport.abort()
                    except Exception:
                        pass
            LOOP.call_soon_threadsafe(_abort)
            return self._json({"ok": True, "dropped": len(peers)})
        return self._json({"ok": False, "err": "not found"}, 404)


class StaticHandler(BaseHTTPRequestHandler):
    server_version = "b612-static/1.0"
    MIME = {
        ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
        ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
    }

    def log_message(self, *a):
        pass

    def do_GET(self):
        rel = urlparse(self.path).path.lstrip("/") or "index.html"
        fp = (GAME_DIR / rel).resolve()
        if not str(fp).startswith(str(GAME_DIR)) or not fp.is_file():
            body = b"404"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.MIME.get(fp.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def start_http(port, cls):
    srv = ThreadingHTTPServer(("0.0.0.0", port), cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


async def main():
    global LOOP
    LOOP = asyncio.get_running_loop()
    origins = [o.strip() for o in ORIGIN_ALLOW.split(",") if o.strip()] or None
    start_http(API_PORT, ApiHandler)
    start_http(STATIC_PORT, StaticHandler)
    ip = lan_ip()
    log("boot", f"静态 http://{ip}:{STATIC_PORT}/   WS ws://{ip}:{WS_PORT}/ws   API :{API_PORT}  ORIGIN={origins or '*'}")
    async with serve(handler, "0.0.0.0", WS_PORT, origins=origins,
                     process_request=process_request,
                     ping_interval=20, ping_timeout=20, max_size=2 ** 20):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("exit", "KeyboardInterrupt")
