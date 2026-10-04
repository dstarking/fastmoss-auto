import json
import shutil
import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import (QObject, Signal, QRunnable, QThreadPool, QSettings,
                            Qt, QUrl, QProcess, QTimer)
from PySide6.QtGui import QDesktopServices, QPainter
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QComboBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QLabel, QTabWidget, QPlainTextEdit, QProgressBar,
    QTableWidget, QTableWidgetItem, QMessageBox, QSplitter, QHeaderView)
from PySide6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis

from .bridge import Bridge
from .collector import Collector
from .domain import Job, Cancelled, COUNTRIES, default_output, load_sections
from .export import export_run, numeric_sales


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
        self.resize(1220, 820)
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
        layout = QVBoxLayout(root)
        title = QLabel("FastMoss Auto")
        title.setStyleSheet("font-size:26px;font-weight:700;color:#183153")
        layout.addWidget(title)
        layout.addWidget(QLabel("TikTok Shop · 跨境店 ｜ 复用 Chrome / Edge 登录态 ｜ CSV / JSON / 报告"))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.setCentralWidget(root)

        collect = QWidget()
        form = QFormLayout(collect)
        self.country = QComboBox()
        self.country.setEditable(True)
        self.country.addItems(COUNTRIES)
        self.country.setCurrentText(self.settings.value("country", "新加坡"))
        self.section = QComboBox()
        self.section.addItem("商品 · 新品榜", "products")
        self.section.addItem("店铺 · 销量榜", "shops:sales")
        self.section.addItem("店铺 · 热推榜", "shops:hot")
        self.category = QLineEdit(self.settings.value("category", "宠物用品"))
        self.category.setPlaceholderText("可选，填写 FastMoss 中文页面的完整标签；留空沿用页面默认")
        self.period = QComboBox()
        self.period.setEditable(True)
        self.period.addItems(["", "日榜", "周榜", "月榜"])
        self.period.setCurrentText(self.settings.value("period", ""))
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
        form.addRow("品类（可选）", self.category)
        form.addRow("周期（可选）", self.period)
        form.addRow("最多采集页数", self.pages)
        form.addRow("页面等待", self.wait)
        form.addRow("输出目录", self.output_row)
        hint = QLabel("请使用 FastMoss 中文页面。国家列表是候选标签，实际可用性以页面和账号权限为准。\n"
                      "任一已填写的筛选无法确认生效时会停止任务；商品榜来自上游的新品榜。")
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        self.start_btn = QPushButton("开始采集")
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
        form.addRow(self.progress)
        self.tabs.addTab(collect, "采集任务")

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
        self.tabs.addTab(result, "数据与图表")

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
                       "4. 检查环境后，返回采集任务选择国家、可选参数和输出目录。\n\n"
                       "设置自动保存；输出目录支持中文和空格，每次任务生成独立子文件夹。\n"
                       "本程序调用你本地的上游 sections.py，不随包复制上游源码。")
        guide.setWordWrap(True)
        setup_form.addRow(guide)
        self.tabs.addTab(setup, "环境设置")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(155)
        layout.addWidget(self.log)
        self.setStyleSheet("QMainWindow{background:#f4f7fb} QPushButton{padding:8px 16px} QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox{padding:5px} QTabWidget::pane{background:white;border:1px solid #dce3ed}")
        for field in (self.output, self.source, self.bsk, self.category):
            field.editingFinished.connect(self.save_settings)
        for combo in (self.country, self.period):
            combo.currentTextChanged.connect(self.save_settings)
        self.pages.valueChanged.connect(self.save_settings)
        self.wait.valueChanged.connect(self.save_settings)
        self.update_chart([])

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
                   category=self.category.text().strip(), period=self.period.currentText().strip(),
                   pages=self.pages.value(), wait=self.wait.value(), output=self.output.text().strip(),
                   source=self.source.text().strip(), bsk=self.bsk.text().strip())

    def run_work(self, fn, success):
        if self.busy:
            return
        self.busy = True
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
        self.start_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.daemon_btn.setEnabled(True)
        self.daemon_stop.setEnabled(True)

    def start_collection(self):
        try:
            job = self.job()
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
            run = export_run(job, rows, warnings)
            return run, rows, warnings
        self.run_work(collect, self.collection_done)

    def collection_done(self, result):
        run, rows, warnings = result
        self.last_run = run
        self.progress.setValue(100)
        self.log.appendPlainText(f"已保存 {len(rows)} 条数据到 {run}")
        for warning in warnings:
            self.log.appendPlainText(warning)
        self.show_rows(rows)
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
            self.show_rows(rows)
            self.last_run = Path(filename).parent
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            self.on_error(str(exc))

    def show_rows(self, rows):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        self.table.clear()
        self.table.setColumnCount(len(fields))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(fields)
        for i, row in enumerate(rows):
            for j, key in enumerate(fields):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(key, ""))))
        self.summary.setText(f"共 {len(rows)} 条数据 · 图表仅使用可解析的明确销量值")
        self.update_chart(rows)

    def update_chart(self, rows):
        chart = QChart()
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
            chart.addAxis(xaxis, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(xaxis)
            yaxis = QValueAxis()
            yaxis.setRange(0, max(1, max(value for _, value in values) * 1.1))
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
        QTimer.singleShot(500, application.quit)
    code = application.exec()
    window.close()
    sys.exit(code)
