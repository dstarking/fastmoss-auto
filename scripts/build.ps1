$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --windowed --onefile --name FastMossAuto main.py
if ($LASTEXITCODE -ne 0) { throw "打包失败" }
Write-Host "生成文件：dist/FastMossAuto.exe"
