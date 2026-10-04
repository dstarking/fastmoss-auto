# FastMoss Auto

Windows / macOS 桌面应用，面向 **TikTok Shop 跨境店**。默认新加坡和宠物用品，支持选择国家、商品国家＋必选类目精确筛选、采集结果表格、销量图、历史 JSON 导入，以及 **自选输出目录**。

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
2. 商品页面固定使用销量榜；店铺页面单独选择销量榜或热推榜。商品首先打开上游入口，再从真实导航链接定位商品销量榜，不猜测URL，不用新品榜替代。找不到唯一入口时停止并显示原因。
3. 商品分析点击 **读取类目**：应用使用你配置的本地 `bsk` 连接已登录的FastMoss浏览器，确认所选国家后读取真实分类。读取过程中界面保持响应，可取消。分类按国家缓存；切换国家只使用该国家的缓存，不混用其他市场。
4. 从级联下拉选择品类：**一级必选，二级/三级可选**。只选“宠物用品”，下级保持“全部子类（停在父类）”，即可采集该父类目下通过验证的商品；选中子类会缩小范围。改变父类自动清空下级。如果页面只返回一级，会明确提示；可选择父类再点读取类目尝试加载下级，程序不补造未返回的分类。分类改用只读下拉，不再手动填写。周期不指定，保留实际销量指标名，不猜测日/周/月周期。
5. 选择页数和等待时间；页面较慢时增加等待秒数。
6. 点击输出目录旁边的“选择…”，或直接输入，例如 `F:/fastmoss/data`、`D:/选品数据`。设置自动记住。
7. 点击“开始采集”，完成后查看表格和图表，或打开输出目录。

商品执行“国家 + 跨境店 + 必选品类”组合筛选（本应用扩展，上游 CLI 每次只处理一个维度）。店铺执行“国家 + 跨境店”，不传品类/周期。页面不提供某筛选或无法确认选中状态时，会显示原因并停止。店铺榜上游只内置国家筛选，本应用额外验证页面的跨境店控件，是否支持需实机验证，无法确认时明确报错。

读取类目失败或取消不覆盖原缓存；可以重试刷新。旧版手填选择仅在真实分类中完整存在时恢复，不能恢复时要求重新选择，不静默扩大到父类目。应用仍在用户电脑本机调用BrowserSkill，不需要把账号或登录凭据交给其他服务。

## 已核对的上游参数

核对上游 `dcd45e7f2b088867551fb10772e32b21f4219193` 的 `scripts/core.py` 与 `scripts/sections.py`：

| 参数 | 商品榜 products | 店铺榜 shops | 本应用处理 |
| --- | --- | --- | --- |
| section | 必填 products | 必填 shops | 由界面榜单选择生成 |
| ranking | 上游不使用，固定新品 URL | 必填 sales / hot | 本应用扩展商品销量榜真实导航，店铺沿用上游 |
| country | 支持中文标签 | 支持中文标签 | 必选；兼容 SG / Singapore 等输入并转为中文点击 |
| category | 支持 | 不支持 | 商品必选并逐条验证；店铺禁用且不传 |
| shop-type | 支持 | 上游未支持 | 固定跨境店；额外页面验证，不允许静默降级为本土店 |
| time | 不支持 | 不支持 | 禁用，旧设置忽略；上游仅达人支持 |
| pages | 默认 filter 3 / scrape 5 | 默认 filter 3 / scrape 5 | 界面默认3，最大100 |
| out | 必填 CSV 文件路径 | 必填 CSV 文件路径 | 自选目录下生成独立任务文件 |
| session | 可选 | 可选 | 由应用管理独立 BrowserSkill 会话 |
| nav-sleep / page-sleep | 支持 | 支持 | 界面的页面等待用于导航、筛选及分页 |

国家字段优先通过表头定位，支持国旗图片元信息，保留 `country_raw`。商品每行必须有可识别的国家和类目，与所选范围一致。若行内仅显示末级类目（例如“猫砂盆、猫厕所”），先读取类目单元格提示中的完整路径，再核对页面组件的真实类目树及上游已使用的 `GoodCategory/filterInfo` 数据；必要时通过独立会话打开该商品真实详情页，核对类目区域中的完整路径。没有可验证父子关系时不会按关键词或手写分类猜测归属。保持销量榜筛选与分页不变，记录 `country_verification` 和 `category_verification`。缺失、未知国家或其他类目会等待刷新重试，持续异常时停止整个任务，不导出混合数据。筛选控件查询排除表格内容，父容器整体高亮不能作为某个类目已选中的证据。

店铺榜若没有可确认的跨境店筛选，仍无法保证范围符合要求，会明确停止。需要按品类观察跨境店时，可先使用商品分析查看商品所属店铺。

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
    bestsellers.csv # 按当前榜单销量降序排列的候选清单
    report.md      # 范围、Top10候选、数据限制与下载提示
    images/        # 下载成功的商品主图
```

v0.1.4 保留 `category` 与 `category_raw` 原始类目，新增 `category_path` 完整层级。`category_verification=source_hierarchy_and_page_filter` 表示末级类目通过真实父子关系与页面筛选双重确认；完整路径直接匹配时为 `row_and_page_filter`。选择“宠物用品”会包含确认属于其下的猫砂盆等子类目，结果不强制改写成父类目名称。

商品 CSV 增加 `product_title`（完整标题）、`product_url`（页面真实详情链接）、`product_id`、`main_image_url`（主图链接）、`main_image_file`（相对图片路径）和 `source_url`（销量榜来源）。CSV不能嵌入图片像素，使用URL与文件路径引用主图。主图去重下载、最长网络空闲等待5秒、最大10MB；URL过期或下载失败时保留URL并在日志/JSON/报告提示。页面未展示链接或主图时保留空值，不拼造链接。

商品候选清单仅按可解析的榜单销量排序，不用累计销量代替；保留实际表头 `sales_metric`。候选排名是当前已采集样本内排名，不是全市场排名，也不预测增长、利润或未来爆款。按产品ID/真实详情链接去重，名称不作为唯一商品身份。

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

浏览器脚本DOM夹具额外需要 Node.js：`npm install --prefix .dom-tests jsdom@26.1.0 --no-audit --no-fund`。Release CI会安装并执行这些测试；仅安装Python依赖时会跳过DOM夹具。

```powershell
.venv\Scripts\python.exe -m pytest -q
```

测试覆盖组合筛选、筛选失败、分页/末页、重复数据、国家不一致、取消清理、UTF-8 BOM、中文路径、唯一输出目录、导出失败清理、销量值解析、CLI 参数安全、Qt 界面及设置持久化。模拟浏览器测试不代表已通过真实 FastMoss 端到端验证。

本次本地开发环境为 Linux/Python 3.12。Windows/macOS/Python 3.13 由仓库 CI 校验，构建结果以 Actions 状态为准。真实采集需要你自己的登录态、会员权限和 BrowserSkill 扩展。

## 代码结构

- `fastmoss_auto/app.py`：界面、线程任务、QtCharts、QProcess 服务管理。
- `category_picker.py`：只读级联下拉与可停在任意父类的选择逻辑。
- `category_reader.py`：通过独立BrowserSkill会话读取真实分类，验证国家、取消及清理。
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
