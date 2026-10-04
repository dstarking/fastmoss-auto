# FastMoss Auto

Windows / macOS 桌面应用，面向 **TikTok Shop 跨境店**。默认新加坡和宠物用品，支持选择国家、组合筛选、采集结果表格、销量图、历史 JSON 导入，以及 **自选输出目录**。

技术栈：Python 3.13 / PySide6 / BrowserSkill / fastmoss-rpa-skills / pandas / QtCharts / PyInstaller。

## Windows 启动

你已安装 Python 3.13、BrowserSkill CLI 和浏览器扩展，可以直接执行：

```powershell
git clone https://github.com/dstarking/fastmoss-auto.git
cd fastmoss-auto
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

脚本创建 `.venv`、安装依赖并打开界面。也可手动执行：

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe main.py
```

在左侧 **设置** 中：

1. 选择已下载的 `fastmoss-rpa-skills` 根目录，里面应有 `scripts/sections.py`。没有下载时执行：
   ```powershell
   git clone https://github.com/liangdabiao/fastmoss-rpa-skills.git
   ```
2. 选择 `bsk.exe` 的实际位置；如果已加入 PATH，可保持 `bsk`。
3. 打开 Chrome/Edge，连接 BrowserSkill 扩展并登录 FastMoss，使用中文页面。
4. 尚未运行服务时点击“启动 BrowserSkill 服务”；已有服务无需再次启动。
5. 点击“检查环境”，确认日志中 BrowserSkill 显示已连接浏览器（connected ≥ 1）。

然后到左侧 **商品分析** 或 **店铺分析** 的“采集设置”：

1. 选择国家。列表是候选中文标签，可以手动输入页面上的准确名称；国家可用性由 FastMoss 和账号权限决定。
2. 选择商品新品榜、店铺销量榜或店铺热推榜。商品入口来自上游 `newProducts`，并非全市场商品搜索。
3. 品类默认 `宠物用品`；周期可留空。填写的标签必须与页面一致。留空表示沿用页面默认，不代表全量数据。
4. 选择页数和等待时间；页面较慢时增加等待秒数。
5. 点击输出目录旁边的“选择…”，或直接输入，例如 `F:/fastmoss/data`、`D:/选品数据`。设置自动记住。
6. 点击“开始采集”，完成后查看表格和图表，或打开输出目录。

应用固定执行“国家 + 跨境店 + 已填写的品类/周期”筛选。页面不提供某筛选或无法确认选中状态时，会显示原因并停止。店铺榜上游只内置国家筛选，本应用额外尝试页面的跨境店/品类/周期控件，是否支持需实机验证，无法确认时明确报错。

## 左侧导航

- **市场分析**：查看当前记录数量、数据概况与首次使用引导，不代表全市场规模。
- **商品分析**：配置商品采集、查看结果和销量图。
- **店铺分析**：配置店铺采集、查看结果和销量图。
- **达人分析**：导入并查看达人历史 JSON；暂不直接采集无法确认跨境店筛选的达人榜。
- **设置**：配置上游目录、BrowserSkill 与浏览器连接。

v0.1.1 使用完整的浅色配色，避免 Windows/macOS 深色系统主题导致白底白字。各页面在尚无数据时也显示明确的提示。

## 输出文件

每次成功任务创建独立目录，避免覆盖旧数据：

```text
你选择的目录/
  20261004_180000_products_随机后缀/
    data.csv       # UTF-8 BOM，可用 Excel 打开
    data.json      # 筛选参数、UTC采集时间、原始数据、提示
    report.md      # 数量摘要及分析限制
```

界面可导入历史 `data.json`。数据来自当前账号可访问的页面，不保证覆盖全市场。销量图只展示能明确解析的数字，不混算金额、区间或不同币种；没有历史快照时不虚构增长率。真实数据不会写入 GitHub。

## 取消、异常与服务

- 后台 `QThreadPool/QRunnable` 采集，界面保持响应。
- 可取消任务，在页面等待或下一次命令边界退出，当前命令最长约 45 秒。
- 取消/采集失败不导出未完成结果；导出失败会清理半成品目录。
- 重复页、未变化页码、错误国家、空页、登录/验证码会中止任务。
- 每个任务只清理自己的 BrowserSkill 会话。
- `QProcess` 管理本应用启动的 `bsk daemon --foreground`，关闭应用会停止该进程，不停止外部已启动服务。
- 浏览器登录和验证码由你手动处理，处理好后重新采集。

## 下载可直接运行的版本

到 [GitHub Releases](https://github.com/dstarking/fastmoss-auto/releases/latest) 下载：

| 系统 | 文件 | 使用方法 |
| --- | --- | --- |
| Windows 64 位 | FastMossAuto-Windows-x64.exe | 下载后双击运行 |
| Mac Apple 芯片 | FastMossAuto-macOS-arm64.zip | 解压，运行 FastMossAuto.app |
| Mac Intel | FastMossAuto-macOS-x64.zip | 解压，运行 FastMossAuto.app |

程序已包含 Python 和界面依赖。首次使用仍需 BrowserSkill CLI、浏览器扩展、上游仓库目录和 FastMoss 登录态。Mac 从 Finder 启动时请在环境设置选择 `bsk` 的绝对路径，避免 PATH 与终端不同导致无法找到 CLI。

Mac 包未做 Apple Developer ID 公证；系统阻止打开时可查看“系统设置 → 隐私与安全性”中的提示。Windows 包没有商业代码签名。

## 自行打包

Windows 安装好开发依赖后：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

生成 `dist/FastMossAuto.exe`（单文件）。

macOS 在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
bash scripts/build-macos.sh
```

生成 `dist/FastMossAuto.app` 和 ZIP。Apple 芯片与 Intel 需要分别在相应架构上打包。

GitHub Actions Release 工作流自动测试三个平台、构建和校验启动，然后上传 GitHub Release。后续版本可手动运行该工作流并填写新的版本号。

## 开发与校验

```powershell
.venv\Scripts\python.exe -m pytest -q
```

测试覆盖组合筛选、筛选失败、分页/末页、重复数据、国家不一致、取消清理、UTF-8 BOM、中文路径、唯一输出目录、导出失败清理、销量值解析、CLI 参数安全、Qt 界面及设置持久化。模拟浏览器测试不代表已通过真实 FastMoss 端到端验证。

本次本地开发环境为 Linux/Python 3.12。Windows/macOS/Python 3.13 由仓库 CI 校验，构建结果以 Actions 状态为准。真实采集需要你自己的登录态、会员权限和 BrowserSkill 扩展。

## 代码结构

- `fastmoss_auto/app.py`：界面、线程任务、QtCharts、QProcess 服务管理。
- `domain.py`：任务参数、验证、上游解析器加载。
- `bridge.py`：BrowserSkill CLI 适配，参数数组不经过 shell。
- `collector.py`：组合筛选、选中状态检查、分页和取消。
- `export.py`：CSV/JSON/Markdown 导出及数值解析。
- `tests/`：核心测试和 Qt 离屏界面测试。
- `scripts/`：Windows 启动、Windows/macOS 打包脚本。

## 上游与依赖

[fastmoss-rpa-skills](https://github.com/liangdabiao/fastmoss-rpa-skills) 提供页面地址、提取 JS 和行解析器；开发时核对版本 `dcd45e7f2b088867551fb10772e32b21f4219193`。

该版本未发现许可证文件，本项目不复制分发其源码，而是加载你本地的 `scripts/sections.py`。该文件是可执行 Python 模块，请只选择你信任的源码目录。上游页面结构变化后可能需要更新或适配。

[BrowserSkill](https://github.com/Tencent/BrowserSkill) 提供浏览器 CLI 和扩展。Qt/PySide6 和 pandas 等依赖保持各自许可证；分发二进制时应保留依赖许可证文件。
