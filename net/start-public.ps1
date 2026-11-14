# B-612 公网联机：一条命令起「房间服务 + 网关 + 隧道」，并打印公网地址
# 用法（仓库根目录）： powershell -ExecutionPolicy Bypass -File net\start-public.ps1
# 说明：电脑关机/睡眠/关掉本窗口，联机即断；免费隧道每次重启都会换地址。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# 0) 依赖
python -c "import websockets" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "安装 websockets ..." -ForegroundColor Yellow
  pip install websockets
}

# 1) 房间服务 + 网关（各自一个窗口，方便看日志）
Write-Host "启动房间服务 127.0.0.1:18201 / 网关 0.0.0.0:18300 ..." -ForegroundColor Cyan
Start-Process -FilePath python -ArgumentList "`"$root\net\roomserver.py`"" -WorkingDirectory $root
Start-Sleep -Seconds 1
Start-Process -FilePath python -ArgumentList "`"$root\net\gateway.py`"" -WorkingDirectory $root
Start-Sleep -Seconds 2

# 2) cloudflared 快速隧道（不需要账号）
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) { $cf = "cloudflared" }
$log = Join-Path $env:TEMP "b612-tunnel.err.log"
$out = Join-Path $env:TEMP "b612-tunnel.out.log"
Remove-Item $log, $out -Force -ErrorAction SilentlyContinue

Write-Host "建立公网隧道（首次可能要 10 秒）..." -ForegroundColor Cyan
$tun = Start-Process -FilePath $cf `
  -ArgumentList "tunnel", "--url", "http://127.0.0.1:18300", "--no-autoupdate", "--protocol", "http2" `
  -RedirectStandardError $log -RedirectStandardOutput $out -WindowStyle Hidden -PassThru

# 3) 等地址
$url = $null
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 500
  if ($tun.HasExited) { break }
  if (Test-Path $log) {
    $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches
    if ($m) { $url = $m.Matches[0].Value; break }
  }
}
if (-not $url) {
  Write-Host "没拿到公网地址，看日志：$log" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "公网地址（每次重启都会变）：" -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ""
Write-Host "两台设备都打开上面的地址 → 点「联机」→ 填同一个房间号 → 连接。"
Write-Host "页面和 wss 同源，服务器地址留空即可。电脑关机/睡眠/关掉本窗口 = 联机断开。"
Write-Host "按 Ctrl+C 结束隧道。"
Write-Host ""

# 4) 保持前台；退出时把隧道一起收掉
try {
  while (-not $tun.HasExited) { Start-Sleep -Seconds 2 }
} finally {
  if (-not $tun.HasExited) { Stop-Process -Id $tun.Id -Force -ErrorAction SilentlyContinue }
}
