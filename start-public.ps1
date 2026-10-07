# Запускает приложение на этом компьютере и открывает к нему доступ из интернета через Cloudflare Tunnel.
# Адрес вида https://<случайные-слова>.trycloudflare.com появится в выводе и меняется при каждом запуске.
# Логин и пароль хранятся в файле .credentials рядом со скриптом (он в .gitignore), при первом запуске создаются.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$credFile = Join-Path $PSScriptRoot ".credentials"
if (-not (Test-Path $credFile)) {
    $password = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 20 | ForEach-Object { [char]$_ })
    "driver`n$password" | Set-Content -Encoding utf8 $credFile
}
$user, $password = Get-Content $credFile
$env:DRIVER_SHIFTS_USER = $user
$env:DRIVER_SHIFTS_PASSWORD = $password

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { $cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }

Write-Host "Логин: $user"
Write-Host "Пароль: $password"

$server = Start-Process python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -NoNewWindow -PassThru
try {
    & $cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
} finally {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
}
