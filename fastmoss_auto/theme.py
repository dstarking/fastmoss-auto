"""Explicit Fusion palette: readable under Windows/macOS dark system themes."""
from PySide6.QtGui import QColor, QPalette, QFont


def apply_theme(application):
    application.setStyle('Fusion')
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: '#f4f7fb', QPalette.ColorRole.WindowText: '#243248',
        QPalette.ColorRole.Base: '#ffffff', QPalette.ColorRole.AlternateBase: '#f0f4fa',
        QPalette.ColorRole.Text: '#243248', QPalette.ColorRole.Button: '#ffffff',
        QPalette.ColorRole.ButtonText: '#243248', QPalette.ColorRole.Highlight: '#2563eb',
        QPalette.ColorRole.HighlightedText: '#ffffff', QPalette.ColorRole.ToolTipBase: '#ffffff',
        QPalette.ColorRole.ToolTipText: '#243248', QPalette.ColorRole.PlaceholderText: '#68778c',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#7b8798'))
    application.setPalette(palette)
    font = QFont()
    font.setFamilies(['Microsoft YaHei UI', 'PingFang SC', 'Noto Sans CJK SC', 'Arial'])
    font.setPointSize(10)
    application.setFont(font)


STYLE = '''
QMainWindow, QWidget { color: #243248; }
QMainWindow { background: #f4f7fb; }
QWidget#sidebar { background: #142238; }
QLabel#brand { color: #ffffff; font-size: 20px; font-weight: 700; }
QLabel#sidebarNote { color: #a9b9d0; }
QListWidget#navigation { background: #142238; color: #c8d5e6; border: 0; outline: none; }
QListWidget#navigation::item { padding: 14px 16px; margin: 4px 0; border-radius: 7px; }
QListWidget#navigation::item:selected { background: #2563eb; color: #ffffff; }
QListWidget#navigation::item:hover:!selected { background: #233752; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; color: #183153; }
QLabel#subtitle, QLabel#muted { color: #596c85; }
QWidget#card { background: #ffffff; border: 1px solid #dce5f0; border-radius: 9px; }
QLabel#metric { font-size: 28px; font-weight: 700; color: #183153; border: 0; }
QPushButton { background: #ffffff; color: #243248; border: 1px solid #cbd7e6; border-radius: 5px; padding: 8px 16px; }
QPushButton:hover { background: #edf3fc; border-color: #93b4ef; }
QPushButton:disabled { background: #eef2f7; color: #7b8798; border-color: #dce5f0; }
QPushButton#primary { background: #2563eb; color: #ffffff; border-color: #2563eb; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#primary:disabled { background: #91b3f5; border-color: #91b3f5; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #ffffff; color: #243248; border: 1px solid #cbd7e6; border-radius: 4px; padding: 6px; min-height: 20px; selection-background-color: #2563eb; selection-color: #ffffff; }
QComboBox QAbstractItemView { background: #ffffff; color: #243248; selection-background-color: #2563eb; selection-color: #ffffff; }
QTabWidget::pane { background: #ffffff; border: 1px solid #dce5f0; }
QTabBar::tab { background: #e8eef8; color: #405471; padding: 10px 20px; }
QTabBar::tab:selected { background: #ffffff; color: #1d4ed8; }
QPlainTextEdit, QTableWidget { background: #ffffff; color: #243248; border: 1px solid #dce5f0; border-radius: 5px; selection-background-color: #dbeafe; selection-color: #243248; }
QHeaderView::section { background: #eef3fa; color: #405471; padding: 7px; border: 1px solid #dce5f0; }
QProgressBar { background: #e8eef8; color: #243248; border: 1px solid #dce5f0; border-radius: 4px; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #4b87ee; }
QStatusBar { color: #596c85; background: #f4f7fb; }
'''
