Windows / macOS 桌面应用，默认新加坡宠物用品，固定 TikTok Shop 跨境店，支持国家选择、可选品类/周期/页数、自选输出目录、CSV/JSON/报告导出、表格、销量图、历史结果导入、取消任务和进度日志。

下载选择：
- Windows 64 位：`FastMossAuto-Windows-x64.exe`，单文件程序，下载后运行。
- Apple 芯片 Mac（M1/M2/M3/M4 等）：`FastMossAuto-macOS-arm64.zip`，解压后运行 `.app`。
- Intel Mac：`FastMossAuto-macOS-x64.zip`，解压后运行 `.app`。
- `SHA256SUMS.txt`：下载文件校验值。

程序已包含 Python、PySide6 和 pandas，运行不需要另行安装 Python。

首次使用仍需要本机 BrowserSkill CLI、Chrome/Edge 扩展、FastMoss 登录态和已下载的 fastmoss-rpa-skills。打开“环境设置”，选择 `bsk` 可执行文件与上游仓库目录，检查浏览器连接；然后选择国家、参数和输出目录即可采集。

Mac 从 Finder 启动时 PATH 可能与终端不同，请选择 `bsk` 的绝对路径。

macOS 包采用本地 ad-hoc 签名，没有 Apple Developer ID 公证；若系统阻止打开，请在系统设置 → 隐私与安全性中检查提示并允许打开。Windows 程序没有商业代码签名，系统可能显示未知发布者。

测试目标为 Windows 和 macOS 15（Apple 芯片、Intel），每个平台运行自动化测试及打包后启动检查。真实 FastMoss 采集需要用户本机账号权限和页面筛选支持，未在开发环境通过真实账号端到端验证。
