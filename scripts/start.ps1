$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv/Scripts/python.exe)) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.13 创建虚拟环境失败" }
}
& .venv/Scripts/python.exe -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }
& .venv/Scripts/python.exe main.py
