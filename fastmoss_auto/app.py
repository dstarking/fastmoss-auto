import json
import shutil
import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import (QObject, Signal, QRunnable, QThreadPool, QSettings,
                            Qt, QUrl, QProcess, QTimer)
from PySide6.QtGui import QDesktopServices, QPainter, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QLabel, QTabWidget, QPlainTextEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QMessageBox, QSplitter, QHeaderView,
    QListWidget, QStackedWidget, QScrollArea)
from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis

from .theme import apply_theme, STYLE
from .bridge import Bridge
from .collector import Collector
from .domain import Job, Cancelled, COUNTRIES, default_output, load_sections
from .export import export_run, numeric_sales
from .category_picker import CategoryPicker
from .category_reader import CategoryReader
from .schema import canonical_country


class Signals(QObject):
    progress = Signal(int, str)
    success = Signal(object)
    error = Signal(str)
    finished = Signal()


class Work(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = Signals()

    def run(self):
        try:
            self.signals.success.emit(self.fn(self.signals.progress.emit))
        except Cancelled as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.signals.finished.emit()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FastMoss Auto · TikTok 跨境选品")
        apply_theme(QApplication.instance())
        self.resize(1280, 860)
        self.setMinimumSize(1000, 720)
        self.rows_by_section = {"products": [], "shops": [], "creators": []}
        self.settings = QSettings("FastMossAuto", "Desktop")
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.cancel = Event()
        self.busy = False
        self.last_run = None
        self.worker = None
        self.daemon = QProcess(self)
        self.daemon.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.daemon.readyReadStandardOutput.connect(self.daemon_log)
        self.daemon.errorOccurred.connect(lambda e: self.log.appendPlainText(f"服务启动失败：{self.daemon.errorString()}"))
        self.daemon.finished.connect(lambda code, status: self.log.appendPlainText(f"本应用启动的服务已退出（{code}）"))

        root = QWidget()
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 28, 18, 22)
        brand = QLabel("FastMoss\n数据助手")
        brand.setObjectName("brand")
        side.addWidget(brand)
        note = QLabel("TikTok Shop · 跨境店")
        note.setObjectName("sidebarNote")
        side.addWidget(note)
        side.addSpacing(25)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.addItems(["市场分析", "商品分析", "店铺分析", "达人分析", "设置"])
        side.addWidget(self.navigation)
        version = QLabel("v0.1.6  ·  本地数据分析")
        version.setObjectName("sidebarNote")
        side.addWidget(version)
        shell.addWidget(sidebar)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        self.page_title = QLabel("市场分析")
        self.page_title.setObjectName("pageTitle")
        self.subtitle = QLabel("从采集结果开始，查看当前市场的数据概况")
        self.subtitle.setObjectName("subtitle")
        layout.addWidget(self.page_title)
        layout.addWidget(self.subtitle)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)
        self.setCentralWidget(root)
        self.build_market_page()
        self.tabs = QTabWidget()
        self.stack.addWidget(self.tabs)

        collect = QWidget()
        form = QFormLayout(collect)
        self.country = QComboBox()
        self.country.setEditable(True)
        self.country.addItems(COUNTRIES)
        self.country.setCurrentText(self.settings.value("country", "新加坡"))
        self.section = QComboBox()
        self.section.addItem("商品 · 销量榜", "products")
        self.category = CategoryPicker(self.settings.value("category", "宠物用品"))
        try:
            self.category_cache = json.loads(self.settings.value('category_cache', '{}'))
            if not isinstance(self.category_cache, dict):
                self.category_cache = {}
        except (ValueError, TypeError):
            self.category_cache = {}
        category_row = QWidget()
        category_layout = QVBoxLayout(category_row)
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.addWidget(self.category)
        category_actions = QHBoxLayout()
        self.read_categories_btn = QPushButton('读取类目')
        self.read_categories_btn.clicked.connect(self.read_categories)
        category_actions.addWidget(self.read_categories_btn)
        self.category_status = QLabel()
        self.category_status.setWordWrap(True)
        category_actions.addWidget(self.category_status, 1)
        category_layout.addLayout(category_actions)
        self.load_category_cache()
        self.period = QComboBox()
        self.period.setEditable(True)
        self.period.addItems(["", "日榜", "周榜", "月榜"])
        self.period.setCurrentText("")
        self.period.setEnabled(False)
        self.period.setToolTip("上游 --time 仅适用于达人榜；商品/店铺榜未支持")
        self.pages = QSpinBox()
        self.pages.setRange(1, 100)
        self.pages.setValue(int(self.settings.value("pages", 3)))
        self.wait = QDoubleSpinBox()
        self.wait.setRange(1, 60)
        self.wait.setValue(float(self.settings.value("wait", 5)))
        self.wait.setSuffix(" 秒")
        self.output = QLineEdit(self.settings.value("output", default_output()))
        self.output_row = self.path_row(self.output, "输出文件夹", directory=True)
        form.addRow("平台 / 店铺类型", QLabel("TikTok Shop / 跨境店（固定）"))
        form.addRow("国家（必选）", self.country)
        form.addRow("采集榜单", self.section)
        form.addRow("商品品类（必选）", category_row)
        form.addRow("周期（此榜单不支持）", self.period)
        form.addRow("最多采集页数", self.pages)
        form.addRow("页面等待", self.wait)
        form.addRow("输出目录", self.output_row)
        hint = QLabel("请使用 FastMoss 中文页面。国家列表是候选标签，实际可用性以页面和账号权限为准。\n"
                      "商品按国家＋跨境店＋必选类目采集销量榜，逐条验证范围；图片下载失败时保留URL并提示。")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        self.start_btn = QPushButton("开始采集")
        self.start_btn.setObjectName("primary")
        self.stop_btn = QPushButton("取消任务")
        self.stop_btn.setEnabled(False)
        self.open_btn = QPushButton("打开输出目录")
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.open_btn)
        self.start_btn.clicked.connect(self.start_collection)
        self.stop_btn.clicked.connect(self.cancel.set)
        self.open_btn.clicked.connect(self.open_output)
        form.addRow(buttons)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        form.addRow(self.progress)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(collect)
        self.tabs.addTab(scroll, "采集设置")

        result = QWidget()
        results = QVBoxLayout(result)
        result_buttons = QHBoxLayout()
        import_btn = QPushButton("导入历史 data.json")
        import_btn.clicked.connect(self.import_run)
        self.summary = QLabel("暂无数据；成功采集后展示原始结果与可解析销量图")
        result_buttons.addWidget(self.summary, 1)
        result_buttons.addWidget(import_btn)
        results.addLayout(result_buttons)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(155)
        self.chart = QChartView()
        self.chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.chart)
        results.addWidget(splitter)
        self.result_empty = QLabel("暂无商品数据。完成采集后自动展示，或点击右上角导入历史 data.json。")
        self.result_empty.setWordWrap(True)
        results.insertWidget(1, self.result_empty)
        self.tabs.addTab(result, "数据结果")
        self.build_creator_page()

        setup = QWidget()
        setup_form = QFormLayout(setup)
        guessed = str(Path.cwd().parent / "fastmoss-rpa-skills")
        self.source = QLineEdit(self.settings.value("source", guessed))
        self.bsk = QLineEdit(self.settings.value("bsk", shutil.which("bsk") or "bsk"))
        setup_form.addRow("fastmoss-rpa-skills 目录", self.path_row(self.source, "选择上游仓库", True))
        setup_form.addRow("BrowserSkill CLI", self.path_row(self.bsk, "选择 bsk 可执行文件", False))
        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        self.check_btn = QPushButton("检查环境")
        self.daemon_btn = QPushButton("启动 BrowserSkill 服务")
        self.daemon_stop = QPushButton("停止本应用启动的服务")
        self.check_btn.clicked.connect(self.check_environment)
        self.daemon_btn.clicked.connect(self.start_daemon)
        self.daemon_stop.clicked.connect(self.stop_daemon)
        for btn in (self.check_btn, self.daemon_btn, self.daemon_stop):
            action_layout.addWidget(btn)
        setup_form.addRow(actions)
        guide = QLabel("1. 安装 BrowserSkill CLI 和 Chrome / Edge 扩展。\n"
                       "2. 选择已有 fastmoss-rpa-skills 的目录。\n"
                       "3. 连接扩展，在浏览器登录 FastMoss，使用中文页面。\n"
                       "4. 检查环境后，进入商品或店铺分析选择国家、可选参数和输出目录。\n\n"
                       "设置自动保存；输出目录支持中文和空格，每次任务生成独立子文件夹。\n"
                       "本程序调用你本地的上游 sections.py，不随包复制上游源码。")
        guide.setWordWrap(True)
        setup_form.addRow(guide)
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setWidget(setup)
        self.stack.addWidget(setup_scroll)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(155)
        layout.addWidget(QLabel("任务日志"))
        self.log.setPlaceholderText("操作提示、采集进度和环境检查结果会显示在这里。")
        layout.addWidget(self.log)
        self.setStyleSheet(STYLE)
        self.navigation.currentRowChanged.connect(self.navigate)
        self.navigation.setCurrentRow(0)
        for field in (self.output, self.source, self.bsk, self.category):
            field.editingFinished.connect(self.save_settings)
        for combo in (self.country, self.period):
            combo.currentTextChanged.connect(self.save_settings)
        self.pages.valueChanged.connect(self.save_settings)
        self.wait.valueChanged.connect(self.save_settings)
        self.section.currentIndexChanged.connect(self.sync_parameters)
        self.country.currentTextChanged.connect(self.load_category_cache)
        self.sync_parameters()
        self.update_chart([])

    def sync_parameters(self, *_):
        products = self.section.currentData() == "products"
        self.category.setEnabled(products and not self.busy)
        self.read_categories_btn.setEnabled(products and not self.busy)
        self.category.setToolTip("按层级选择类目，并逐条验证实际类目；店铺榜不传品类")
        self.period.setCurrentText("")

    def load_category_cache(self, *_):
        country = canonical_country(self.country.currentText()) or self.country.currentText().strip()
        catalog = self.category_cache.get(country, {})
        preferred = self.category.text() or self.category.preferred
        paths = catalog.get('paths', []) if isinstance(catalog, dict) and catalog.get('schema_version') == 1 else []
        self.category.set_paths(paths, preferred)
        if self.category.paths:
            roots = {path[0] for path in self.category.paths}
            depth = max(map(len, self.category.paths))
            self.category_status.setText(f'{country}缓存：{len(roots)} 个一级类目，已读取最深 {depth} 级；可停在父类。')
        else:
            self.category_status.setText('尚未读取当前国家的类目；请点击“读取类目”。')

    def read_categories(self):
        if self.busy:
            return
        country = self.country.currentText().strip()
        source, bsk = self.source.text().strip(), self.bsk.text().strip()
        preferred = self.category.text() or self.category.preferred or '宠物用品'
        wait = self.wait.value()
        try:
            load_sections(source)
            if not country or not bsk:
                raise ValueError('请先选择国家并配置 bsk')
            self.save_settings()
        except Exception as exc:
            self.on_error(str(exc))
            return
        def read(progress):
            return CategoryReader().read(country, source, bsk, preferred, wait, self.cancel, progress)
        self.run_work(read, self.categories_done)

    def categories_done(self, catalog):
        country = catalog['country']
        self.category_cache[country] = catalog
        self.settings.setValue('category_cache', json.dumps(self.category_cache, ensure_ascii=False))
        self.settings.sync()
        self.load_category_cache()
        self.save_settings()
        self.progress.setValue(100)
        self.log.appendPlainText(f"已读取并缓存{country}的 {len(catalog['paths'])} 条真实类目路径。只选一级类目即可采集其子类。")
        for warning in catalog.get('warnings', []):
            self.log.appendPlainText(warning)

    def path_row(self, edit, title, directory):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("选择…")
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        def pick():
            chosen = QFileDialog.getExistingDirectory(self, title, edit.text()) if directory else QFileDialog.getOpenFileName(self, title, edit.text())[0]
            if chosen:
                edit.setText(chosen)
                self.save_settings()
        button.clicked.connect(pick)
        return widget

    def save_settings(self, *_):
        for key, value in {"country": self.country.currentText(), "category": self.category.text(),
            "period": self.period.currentText(), "pages": self.pages.value(), "wait": self.wait.value(),
            "output": self.output.text(), "source": self.source.text(), "bsk": self.bsk.text()}.items():
            self.settings.setValue(key, value)
        self.settings.sync()

    def job(self):
        section, _, ranking = self.section.currentData().partition(":")
        return Job(country=self.country.currentText().strip(), section=section, ranking=ranking or "sales",
                   category=self.category.text().strip() if section == "products" else "", period="",
                   pages=self.pages.value(), wait=self.wait.value(), output=self.output.text().strip(),
                   source=self.source.text().strip(), bsk=self.bsk.text().strip())

    def run_work(self, fn, success):
        if self.busy:
            return
        self.busy = True
        self.sync_parameters()
        self.cancel = Event()
        self.start_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.daemon_btn.setEnabled(False)
        self.daemon_stop.setEnabled(False)
        self.worker = Work(fn)
        self.worker.signals.progress.connect(self.on_progress)
        self.worker.signals.success.connect(success)
        self.worker.signals.error.connect(self.on_error)
        self.worker.signals.finished.connect(self.finished)
        self.pool.start(self.worker)

    def on_progress(self, value, message):
        self.progress.setValue(value)
        self.log.appendPlainText(message)

    def on_error(self, message):
        self.log.appendPlainText(message)
        self.progress.setValue(0)
        self.statusBar().showMessage(message)

    def finished(self):
        self.busy = False
        self.sync_parameters()
        self.start_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.daemon_btn.setEnabled(True)
        self.daemon_stop.setEnabled(True)

    def start_collection(self):
        try:
            job = self.job()
            if job.section == 'products' and not job.category:
                raise ValueError('请先点击“读取类目”，并从下拉框选择一级类目；二级、三级可以不选')
            job.validate()
            load_sections(job.source)
            self.save_settings()
        except Exception as exc:
            self.on_error(str(exc))
            return
        def collect(progress):
            rows, warnings = Collector().collect(job, self.cancel, progress)
            if self.cancel.is_set():
                raise Cancelled("任务已取消")
            progress(95, "保存 CSV、JSON 和报告")
            run = export_run(job, rows, warnings, self.cancel, progress)
            saved = json.loads((run / 'data.json').read_text(encoding='utf-8'))
            rows, warnings = saved['rows'], saved['warnings']
            return run, rows, warnings, job.section
        self.run_work(collect, self.collection_done)

    def collection_done(self, result):
        run, rows, warnings, kind = result
        self.last_run = run
        self.progress.setValue(100)
        self.log.appendPlainText(f"已保存 {len(rows)} 条数据到 {run}")
        for warning in warnings:
            self.log.appendPlainText(warning)
        self.show_rows(rows, kind)
        self.navigation.setCurrentRow(1 if kind == "products" else 2)
        self.tabs.setCurrentIndex(1)

    def check_environment(self):
        source, binary = self.source.text().strip(), self.bsk.text().strip()
        self.save_settings()
        def check(progress):
            load_sections(source)
            progress(20, "上游解析模块已加载")
            bridge = Bridge(binary, self.cancel)
            status = bridge.run("status")
            return status
        self.run_work(check, lambda status: self.on_progress(100, f"BrowserSkill 状态（请确认 connected ≥ 1）：\n{status}"))

    def daemon_log(self):
        self.log.appendPlainText(bytes(self.daemon.readAllStandardOutput()).decode("utf-8", "replace").strip())

    def start_daemon(self):
        if self.daemon.state() != QProcess.ProcessState.NotRunning:
            self.log.appendPlainText("本应用启动的服务正在运行")
            return
        self.save_settings()
        self.daemon.setProgram(self.bsk.text().strip())
        self.daemon.setArguments(["daemon", "--foreground"])
        self.daemon.start()
        self.log.appendPlainText("正在启动 BrowserSkill 服务；已有服务时可直接检查环境")

    def stop_daemon(self):
        if self.daemon.state() != QProcess.ProcessState.NotRunning:
            self.daemon.terminate()
            QTimer.singleShot(3000, self.kill_daemon)

    def kill_daemon(self):
        if self.daemon.state() != QProcess.ProcessState.NotRunning:
            self.daemon.kill()

    def open_output(self):
        path = self.last_run or Path(self.output.text()).expanduser()
        if not path.is_dir():
            self.on_error("输出目录尚不存在，请先完成一次采集或选择已有目录")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def import_run(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入历史结果", self.output.text(), "FastMoss JSON (*.json)")
        if not filename:
            return
        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            rows = data.get("rows")
            if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
                raise ValueError("不是有效的 FastMoss data.json")
            kind = data.get("filters", {}).get("section") or self.row_kind(rows)
            if kind not in self.rows_by_section:
                raise ValueError("未知历史任务类型")
            self.show_rows(rows, kind)
            self.last_run = Path(filename).parent
            self.navigation.setCurrentRow({"products": 1, "shops": 2, "creators": 3}[kind])
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            self.on_error(str(exc))

    @staticmethod
    def row_kind(rows):
        keys = {key for row in rows for key in row}
        if {"product_name", "product_title", "product_url", "商品", "商品信息"} & keys:
            return "products"
        if "creator_name" in keys or "达人" in keys or "达人信息" in keys:
            return "creators"
        return "shops" if "shop_name" in keys or "店铺" in keys else "products"

    def show_rows(self, rows, kind=None):
        kind = kind or self.row_kind(rows)
        self.rows_by_section[kind] = rows
        self.refresh_market()
        if kind == "creators":
            self.fill_table(self.creator_table, rows)
            self.creator_empty.setText(f"已导入 {len(rows)} 条达人记录。")
        else:
            self.render_rows(rows)

    @staticmethod
    def fill_table(table, rows):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        table.clear()
        table.setColumnCount(len(fields))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(fields)
        for i, row in enumerate(rows):
            for j, key in enumerate(fields):
                table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))))

    def render_rows(self, rows):
        self.fill_table(self.table, rows)
        self.summary.setText(f"共 {len(rows)} 条数据 · 图表仅使用可解析的明确销量值")
        self.result_empty.setVisible(not rows)
        self.update_chart(rows)

    def build_market_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        metrics = QHBoxLayout()
        self.metrics = {}
        for key, caption in [("products", "商品记录"), ("shops", "店铺记录"), ("creators", "达人记录")]:
            card = QWidget()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(20, 16, 20, 16)
            box.addWidget(QLabel(caption))
            value = QLabel("0")
            value.setObjectName("metric")
            box.addWidget(value)
            self.metrics[key] = value
            metrics.addWidget(card)
        layout.addLayout(metrics)
        welcome = QWidget()
        welcome.setObjectName("card")
        info = QVBoxLayout(welcome)
        info.setContentsMargins(24, 24, 24, 24)
        self.market_empty = QLabel("开始你的市场分析")
        self.market_empty.setStyleSheet("font-size:18px;font-weight:700;border:0")
        info.addWidget(self.market_empty)
        self.market_note = QLabel("尚未采集或导入数据。\n\n1. 在设置中配置 BrowserSkill 和上游仓库目录。\n2. 在商品或店铺分析中选择国家、可用参数及输出目录，开始采集。\n3. 采集完成后查看表格、销量图与报告。")
        self.market_note.setWordWrap(True)
        info.addWidget(self.market_note)
        actions = QHBoxLayout()
        setup = QPushButton("前往设置")
        setup.clicked.connect(lambda: self.navigation.setCurrentRow(4))
        collect = QPushButton("开始商品分析")
        collect.setObjectName("primary")
        collect.clicked.connect(lambda: self.navigation.setCurrentRow(1))
        history = QPushButton("导入历史数据")
        history.clicked.connect(self.import_run)
        actions.addWidget(setup)
        actions.addWidget(collect)
        actions.addWidget(history)
        actions.addStretch()
        info.addLayout(actions)
        layout.addWidget(welcome)
        notice = QLabel("统计基于本次采集或导入的记录，不代表全市场规模；没有历史快照时不计算增长率。")
        notice.setObjectName("muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addStretch()
        self.stack.addWidget(page)

    def build_creator_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.creator_empty = QLabel("暂无达人数据。可以导入包含 creator_name 或达人字段的历史 data.json。\n"
            "当前直接采集支持商品和店铺；达人榜无法确认跨境店筛选，因此此页提供导入与查看。")
        self.creator_empty.setWordWrap(True)
        layout.addWidget(self.creator_empty)
        history = QPushButton("导入达人数据")
        history.clicked.connect(self.import_run)
        layout.addWidget(history, alignment=Qt.AlignmentFlag.AlignLeft)
        self.creator_table = QTableWidget()
        self.creator_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.creator_table)
        self.stack.addWidget(page)

    def refresh_market(self):
        for key, metric in self.metrics.items():
            metric.setText(str(len(self.rows_by_section[key])))
        rows = [row for items in self.rows_by_section.values() for row in items]
        if rows:
            countries = sorted({str(row.get("filter_country") or row.get("country") or "未标注") for row in rows})
            self.market_empty.setText("当前数据概况")
            self.market_note.setText(f"已加载 {len(rows)} 条记录。\n国家 / 地区：{'、'.join(countries)}\n可在左侧切换商品、店铺或达人分析，查看各自的数据。")

    def navigate(self, index):
        if index < 0:
            return
        names = ["市场分析", "商品分析", "店铺分析", "达人分析", "设置"]
        self.page_title.setText(names[index])
        self.stack.setCurrentIndex([0, 1, 1, 2, 3][index])
        descriptions = ["查看当前采集或导入的数据概况", "选择商品采集条件，查看商品结果与销量图", "选择店铺榜单，查看店铺结果与销量图", "导入并查看达人历史数据", "连接浏览器，配置本地采集环境"]
        self.subtitle.setText(descriptions[index])
        if index in (1, 2):
            kind = "products" if index == 1 else "shops"
            selected = self.section.currentData()
            self.section.blockSignals(True)
            self.section.clear()
            if index == 1:
                self.section.addItem("商品 · 销量榜", "products")
            else:
                self.section.addItem("店铺 · 销量榜", "shops:sales")
                self.section.addItem("店铺 · 热推榜", "shops:hot")
                self.section.setCurrentIndex(1 if selected == "shops:hot" else 0)
            self.section.blockSignals(False)
            self.sync_parameters()
            self.result_empty.setText(f"暂无{'商品' if index == 1 else '店铺'}数据。请开始采集，或导入历史 data.json。")
            self.render_rows(self.rows_by_section[kind])

    def update_chart(self, rows):
        chart = QChart()
        chart.setTheme(QChart.ChartTheme.ChartThemeLight)
        chart.setBackgroundBrush(QColor("#ffffff"))
        chart.setTitleBrush(QColor("#243248"))
        chart.setTitle("销量 Top 10（当前榜单周期；区间和币种值不参与）")
        values = []
        for row in rows:
            sales = next((row[key] for key in ("sales_period", "销量", "商品销量") if key in row), "")
            number = numeric_sales(sales)
            name = row.get("product_name") or row.get("shop_name")
            if number is not None and name:
                values.append((str(name)[:25], number))
        values = sorted(values, key=lambda pair: pair[1], reverse=True)[:10]
        if values:
            bars = QBarSet("销量")
            bars.append([value for _, value in values])
            series = QBarSeries()
            series.append(bars)
            chart.addSeries(series)
            xaxis = QBarCategoryAxis()
            xaxis.append([name for name, _ in values])
            xaxis.setLabelsBrush(QColor("#405471"))
            chart.addAxis(xaxis, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(xaxis)
            yaxis = QValueAxis()
            yaxis.setRange(0, max(1, max(value for _, value in values) * 1.1))
            yaxis.setLabelsBrush(QColor("#405471"))
            chart.addAxis(yaxis, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(yaxis)
        else:
            chart.setTitle("暂无可解析的销量数据；请查看原始表格")
        self.chart.setChart(chart)

    def closeEvent(self, event):
        if self.busy:
            self.cancel.set()
            self.log.appendPlainText("正在取消任务，请等待当前 BrowserSkill 调用结束后再关闭（最长约45秒）")
            event.ignore()
            return
        self.save_settings()
        self.stop_daemon()
        if self.daemon.state() != QProcess.ProcessState.NotRunning:
            if not self.daemon.waitForFinished(1000):
                self.daemon.kill()
                self.daemon.waitForFinished(1000)
        event.accept()


def main():
    application = QApplication(sys.argv)
    application.setApplicationName("FastMoss Auto")
    window = Window()
    window.show()
    if "--smoke-test" in sys.argv:
        window.show_rows([{ "product_name": "Smoke test", "sales_period": "100" }])
        def verify_ui():
            from PySide6.QtGui import QPalette
            assert window.country.palette().color(QPalette.ColorRole.Text).lightness() < 100
            assert window.navigation.count() == 5
            for index in range(5):
                window.navigation.setCurrentRow(index)
                application.processEvents()
                assert window.page_title.isVisible()
                if "--capture-ui" in sys.argv:
                    window.grab().save(f"ui-{index}.png")
            # Exercise packaged cascading widgets using explicit test-only fixtures.
            window.navigation.setCurrentRow(1)
            window.category.set_paths([['宠物用品'], ['宠物用品', '猫用品', '猫砂盆、猫厕所'],
                                       ['宠物用品', '狗用品', '牵引绳']], '宠物用品')
            window.category_status.setText('打包校验夹具（仅测试）：可停在父类，或继续选择下级。')
            assert window.job().category == '宠物用品'
            assert not any(combo.isEditable() for combo in window.category.combos)
            application.processEvents()
            if "--capture-ui" in sys.argv:
                window.grab().save('ui-category-parent.png')
            window.category.setText('宠物用品 / 猫用品 / 猫砂盆、猫厕所')
            assert window.job().category == '宠物用品 / 猫用品 / 猫砂盆、猫厕所'
            application.processEvents()
            if "--capture-ui" in sys.argv:
                window.grab().save('ui-category-leaf.png')
            application.quit()
        QTimer.singleShot(500, verify_ui)
    code = application.exec()
    window.close()
    sys.exit(code)
