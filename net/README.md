# B-612 联机服务 · 最短启动说明

游戏本体仍是单文件：`game/index.html` 双击即可离线单机玩，不连服务器不会有任何报错。
联机是可选项，点右上角的「地球」按钮，填同一个房间号即可。

## 1. 本机两个人（同一台电脑 / 同一 WiFi）

```bash
pip install websockets          # 只需一次
python net/roomserver.py
```

看到 `静态 http://<你的IP>:18100/  WS ws://<你的IP>:18201/ws` 即启动成功。

- 浏览器 A：打开 `http://localhost:18100/`
- 浏览器 B：再开一个窗口，同样打开 `http://localhost:18100/`
- 两边都点「地球」→ 房间号填**完全相同**的中文/英文（例如 `B612`）→ 点「连 接」。
- 服务器地址默认就是 `ws://<当前网页主机>:18201/ws`，本机不用改。

也可以直接双击各自的 `game/index.html`（file://）。这时服务器地址默认
`ws://localhost:18201/ws`，两台都在本机时可直接连；如果对方在另一台电脑，
把那台电脑的服务器地址改成 `ws://<你的内网IP>:18201/ws`。

## 2. 公网 / 不同 WiFi

把整个 `net/` 和 `game/` 放到一台有公网 IP 的机器上，然后：

```bash
python net/roomserver.py
```

放行入站 TCP 端口：`18100`（游戏页面）和 `18201`（WebSocket）。
两人都打开 `http://<公网IP>:18100/`，房间号填一样即可；服务器地址会自动
指向当前网页的主机，不需要手填。

可选：
- 只改端口：`WS_PORT=19001 STATIC_PORT=19000 API_PORT=19002 python net/roomserver.py`
- 限制来源：`ORIGIN_ALLOW=https://your.site`（逗号分隔；`file://` 的 Origin 是 `null`）
- HTTPS 页面必须用 `wss://`：在 Nginx/Caddy 把 `/ws` 反代到 `127.0.0.1:18201`，
  面板里服务器地址填 `wss://your.domain/ws`。
- `18200` 只是 `/health`、`/stats`、`/drop` 调试接口，不开放也不影响联机。

## 3. 行为说明

- 同步频率约 16.7Hz，只发位置/朝向/步态/角色/换装/挖土的变化量。
- 断线后 250ms 起指数退避重连，最长 3s；对方角色会在 0.55s 内淡出，不会僵在原地。
- 关闭联机（面板里点「断 开」）后完全回到单机，存档不受影响。
