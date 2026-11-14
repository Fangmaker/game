# B-612 联机服务 · 最短启动说明

## 0. 公网联机（不同 WiFi、手机流量也能进同一个房间）

**公网地址：每次启动脚本会打印一个 `https://xxxx.trycloudflare.com`。**
当前实测可用的地址是 `https://demanding-bookstore-southeast-collaborative.trycloudflare.com`
——它只在这次隧道还活着时有效，隧道一停就作废，别收藏。

**电脑关了就断：**房间服务和隧道都跑在这台电脑上，电脑关机 / 睡眠 / 关掉脚本，
联机立刻断开（单机存档不受影响）。

一条命令（在仓库根目录，Windows PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File net\start-public.ps1
```

脚本会依次做三件事，并打印公网地址：

1. `python net/roomserver.py` —— 房间服务（WS 18201）
2. `python net/gateway.py` —— 网关（18300，同一个端口同时给页面和 `/ws`）
3. `cloudflared tunnel --url http://127.0.0.1:18300` —— 公网 https 隧道

拿到地址后：两台设备都打开 `https://xxxx.trycloudflare.com/`，点「联机」，
房间号填**完全相同**的，点「连接」。页面和 WebSocket 同源，**不用填服务器地址**。

> 为什么必须这样：GitHub Pages 是 https，浏览器只允许 `wss://`；
> 隧道一次只能映射一个本地端口，所以把静态页和 WS 收在一个网关端口上。
> 从 GitHub Pages 进游戏也可以，但要在「服务器」里手填 `wss://xxxx.trycloudflare.com/ws`。

依赖：

- `pip install websockets`（只需一次）
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  （本机已装在 `C:\Program Files (x86)\cloudflared\cloudflared.exe`）
- 免费快速隧道**不需要账号、不需要域名**；代价是地址每次重启都变

## 1. 本机两个人（同一台电脑 / 同一 WiFi）

```bash
pip install websockets          # 只需一次
python net/roomserver.py
```

看到 `静态 http://<你的IP>:18100/  WS ws://<你的IP>:18201/ws` 即启动成功。

- 浏览器 A：打开 `http://localhost:18100/`
- 浏览器 B：再开一个窗口，同样打开 `http://localhost:18100/`
- 两边都点「联机」→ 房间号填**完全相同**的中文/英文（例如 `B612`）→ 点「连接」。

也可以直接双击各自的 `game/index.html`（file://）。这时服务器地址默认
`ws://localhost:18201/ws`，两台都在本机时可直接连；如果对方在另一台电脑，
把那台电脑的服务器地址改成 `ws://<你的内网IP>:18201/ws`。

同一 WiFi 想走网关也行：`python net/gateway.py`，两人都开
`http://<你的内网IP>:18300/`，默认地址同样是同源 `ws://…/ws`。

## 2. 公网联机：手动模式（有公网 IP 或自己的反代时）

```bash
python net/roomserver.py
```

放行入站 TCP `18100`（页面）和 `18201`（WebSocket），两人都打开
`http://<公网IP>:18100/`，房间号填一样。

可选：
- 只改端口：`WS_PORT=19001 STATIC_PORT=19000 API_PORT=19002 python net/roomserver.py`
- 网关端口：`GATEWAY_PORT=18300 python net/gateway.py`
- 限制来源：`ORIGIN_ALLOW=https://your.site`（逗号分隔；`file://` 的 Origin 是 `null`）
- 自己的域名 + HTTPS：在 Nginx/Caddy 把 `/ws` 反代到 `127.0.0.1:18201`，
  或者直接把整站反代到网关 `127.0.0.1:18300`（页面和 WS 一起走），
  面板里服务器地址填 `wss://your.domain/ws`。
- `18200` 只是 `/health`、`/stats`、`/drop` 调试接口，不开放也不影响联机。

## 3. 行为说明

- 同步频率约 16.7Hz，只发位置/朝向/步态/角色/换装/挖土的变化量。
- 5 秒内 WS 没握手成功就切到「未连上 · 单机模式」并说明原因，面板给「重 试」；
  不会无限转圈。
- https 页面填 `ws://` 会被浏览器当混合内容拦掉，面板会直接提示改用 `wss://`。
- 断线后 250ms 起指数退避重连，最长 3s；对方角色会在 0.55s 内淡出，不会僵在原地。
- 关闭联机（面板里点「断 开」）后完全回到单机，存档不受影响。

## 4. 排错

| 现象 | 原因 / 做法 |
|---|---|
| 打开公网地址是 530 / 1033 | 隧道进程已经退出：重跑 `start-public.ps1`，地址会换新的 |
| 一直「未连上 · 5 秒没连上」 | 房间服务或网关没起，或隧道地址过期 |
| 「页面是 https，浏览器会拦掉 ws://」 | 地址写成了 `ws://`，改成 `wss://` 或直接留空用同源 |
| 两台能看到彼此但不动 | 两端都要用同一个 `wss://…/ws`；路由器/公司网禁用 WebSocket 时换网络 |
