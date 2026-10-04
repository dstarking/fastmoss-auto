$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name FastMossAuto --collect-all PySide6 --collect-all pandas main.py
if ($LASTEXITCODE -ne 0) { throw "打包失败" }
Write-Host "生成目录：dist/FastMossAuto；请完整复制该目录，运行 FastMossAuto.exe"
