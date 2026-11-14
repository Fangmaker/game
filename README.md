# 小王子 · B-612

一颗只有火山、玫瑰和八位住客的小行星，可以一路往下挖，挖穿就掉到星球另一面。

游戏本体是**单个 HTML 文件**（内联 three.js），不用安装、不用构建、不联网也能玩。

- 成品：`game/index.html`（双击就能打开）
- 联机服务端：`net/roomserver.py`（可选，不启动不影响单机）

## 怎么玩

直接双击 `game/index.html`，或拖进浏览器。

| 操作 | 电脑 | 手机 |
| --- | --- | --- |
| 行走 | `WASD` / 方向键 | 左下角拖动 |
| 转视角 | 鼠标拖拽 | 屏幕拖动 |
| 互动 | `E` 或空格 | 点互动按钮 |

挖土、换装、切换八个角色都在界面里；角色技能各自独立，冷却 12–26 秒。

## 怎么开联机

```bash
pip install websockets
python net/roomserver.py
```

看到 `静态 http://<你的IP>:18100/  WS ws://<你的IP>:18201/ws` 就是启动好了。

浏览器打开 `http://localhost:18100/`，所有人点右上角「地球」，填**同一个房间号**（中英文都行）再点「连接」。
不同 WiFi 就看 `net/README.md` 里的公网/端口说明。

## 八个角色

| 角色 | 技能 |
| --- | --- |
| 小王子 | 看见本质 |
| 狐狸 | 驯养 |
| 国王 | 下令 |
| 点灯人 | 点灯 |
| 玫瑰 | 荆棘护体 |
| 蛇 | 缠送归途 |
| 商人 | 盘账换丸 |
| 地理学家 | 立标测绘 |

## 用 GitHub Pages 打开（可选）

`game/index.html` 在子目录里，Pages 站点根路径没有 `index.html`，所以访问地址要带路径：

```
https://<用户名>.github.io/game/game/index.html
```

开启方式：仓库 Settings → Pages → Source 选 `Deploy from a branch` → 分支 `main`、目录 `/ (root)` → Save。
