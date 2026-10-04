# FastMoss Auto

Windows 桌面应用，面向 **TikTok Shop 跨境店**。默认新加坡和宠物用品，支持选择国家、组合筛选、采集结果表格、销量图、历史 JSON 导入，以及 **自选输出目录**。

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

在应用 **环境设置** 中：

1. 选择已下载的 `fastmoss-rpa-skills` 根目录，里面应有 `scripts/sections.py`。没有下载时执行：
   ```powershell
   git clone https://github.com/liangdabiao/fastmoss-rpa-skills.git
   ```
2. 选择 `bsk.exe` 的实际位置；如果已加入 PATH，可保持 `bsk`。
3. 打开 Chrome/Edge，连接 BrowserSkill 扩展并登录 FastMoss，使用中文页面。
4. 尚未运行服务时点击“启动 BrowserSkill 服务”；已有服务无需再次启动。
5. 点击“检查环境”，确认日志中 BrowserSkill 显示已连接浏览器（connected ≥ 1）。

然后到 **采集任务**：

1. 选择国家。列表是候选中文标签，可以手动输入页面上的准确名称；国家可用性由 FastMoss 和账号权限决定。
2. 选择商品新品榜、店铺销量榜或店铺热推榜。商品入口来自上游 `newProducts`，并非全市场商品搜索。
3. 品类默认 `宠物用品`；周期可留空。填写的标签必须与页面一致。留空表示沿用页面默认，不代表全量数据。
4. 选择页数和等待时间；页面较慢时增加等待秒数。
5. 点击输出目录旁边的“选择…”，或直接输入，例如 `F:/fastmoss/data`、`D:/选品数据`。设置自动记住。
6. 点击“开始采集”，完成后查看表格和图表，或打开输出目录。

应用固定执行“国家 + 跨境店 + 已填写的品类/周期”筛选。页面不提供某筛选或无法确认选中状态时，会显示原因并停止。店铺榜上游只内置国家筛选，本应用额外尝试页面的跨境店/品类/周期控件，是否支持需实机验证，无法确认时明确报错。

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

## 打包成 EXE

在 Windows 安装好项目依赖后：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

运行 `dist/FastMossAuto/FastMossAuto.exe`，分享时需复制完整文件夹。EXE 仍需要本机 BrowserSkill、浏览器扩展、上游仓库路径和 FastMoss 登录态。

仓库的 GitHub Actions 在 Python 3.13 的 Windows/Linux 上测试，然后生成 Windows 文件夹包。在 **Actions → Test and Windows desktop build → 对应运行 → Artifacts** 下载 `FastMossAuto-Windows`。可直接解压使用，仍需配置上述外部环境。若账号的 GitHub App 不允许创建 workflow，使用本地打包脚本。

## 开发与校验

```powershell
.venv\Scripts\python.exe -m pytest -q
```

测试覆盖组合筛选、筛选失败、分页/末页、重复数据、国家不一致、取消清理、UTF-8 BOM、中文路径、唯一输出目录、导出失败清理、销量值解析、CLI 参数安全、Qt 界面及设置持久化。模拟浏览器测试不代表已通过真实 FastMoss 端到端验证。

本次本地开发环境为 Linux/Python 3.12。Windows/Python 3.13 由仓库 CI 校验，构建结果以 Actions 状态为准。真实采集需要你自己的登录态、会员权限和 BrowserSkill 扩展。

## 代码结构

- `fastmoss_auto/app.py`：界面、线程任务、QtCharts、QProcess 服务管理。
- `domain.py`：任务参数、验证、上游解析器加载。
- `bridge.py`：BrowserSkill CLI 适配，参数数组不经过 shell。
- `collector.py`：组合筛选、选中状态检查、分页和取消。
- `export.py`：CSV/JSON/Markdown 导出及数值解析。
- `tests/`：核心测试和 Qt 离屏界面测试。
- `scripts/`：Windows 启动、打包脚本。

## 上游与依赖

[fastmoss-rpa-skills](https://github.com/liangdabiao/fastmoss-rpa-skills) 提供页面地址、提取 JS 和行解析器；开发时核对版本 `dcd45e7f2b088867551fb10772e32b21f4219193`。

该版本未发现许可证文件，本项目不复制分发其源码，而是加载你本地的 `scripts/sections.py`。该文件是可执行 Python 模块，请只选择你信任的源码目录。上游页面结构变化后可能需要更新或适配。

[BrowserSkill](https://github.com/Tencent/BrowserSkill) 提供浏览器 CLI 和扩展。Qt/PySide6 和 pandas 等依赖保持各自许可证；分发二进制时应保留依赖许可证文件。
