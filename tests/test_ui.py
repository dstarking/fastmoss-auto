import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from fastmoss_auto.app import Window

def test_window_and_settings(tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.output.setText(str(tmp_path / '自选 output'))
    window.country.setCurrentText('新加坡')
    window.save_settings(); window.show(); app.processEvents()
    assert window.tabs.count() == 3
    assert window.job().output.endswith('自选 output')
    window.show_rows([{'product_name': 'Cat toy', 'sales_period': '1.2k'}, {'product_name': 'Leash', 'sales_period': '400'}])
    assert window.table.rowCount() == 2
    assert len(window.chart.chart().series()) == 1
    window.close()
    next_window = Window()
    assert next_window.output.text() == str(tmp_path / '自选 output')
    next_window.close()
