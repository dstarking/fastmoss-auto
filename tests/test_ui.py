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
    assert window.navigation.count() == 5
    assert window.tabs.count() == 2
    window.navigation.setCurrentRow(1)
    assert window.job().output.endswith('自选 output')
    window.show_rows([{'product_name': 'Cat toy', 'sales_period': '1.2k'}, {'product_name': 'Leash', 'sales_period': '400'}])
    assert window.table.rowCount() == 2
    assert len(window.chart.chart().series()) == 1
    window.close()
    next_window = Window()
    assert next_window.output.text() == str(tmp_path / '自选 output')
    next_window.close()


def test_dark_system_palette_stays_readable(tmp_path):
    from PySide6.QtGui import QPalette, QColor
    app = QApplication.instance() or QApplication([])
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, QColor('#202020'))
    dark.setColor(QPalette.ColorRole.Base, QColor('#202020'))
    dark.setColor(QPalette.ColorRole.Text, QColor('#ffffff'))
    dark.setColor(QPalette.ColorRole.WindowText, QColor('#ffffff'))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor('#ffffff'))
    app.setPalette(dark)
    window = Window()
    window.show()
    window.navigation.setCurrentRow(1)
    app.processEvents()
    for field in (window.country, window.category, window.output, window.pages, window.wait):
        assert field.isVisible()
        assert field.palette().color(QPalette.ColorRole.Text).lightness() < 100
        assert field.palette().color(QPalette.ColorRole.Base).lightness() > 220
        assert field.height() >= 20
    assert window.start_btn.isVisible()
    window.close()


def test_sidebar_empty_states_and_data_isolation():
    app = QApplication.instance() or QApplication([])
    window = Window()
    window.show()
    for index in range(5):
        window.navigation.setCurrentRow(index)
        app.processEvents()
        assert window.page_title.isVisible()
        assert window.stack.currentWidget().isVisible()
    window.navigation.setCurrentRow(1)
    window.tabs.setCurrentIndex(1)
    assert window.result_empty.isVisible()
    window.show_rows([{'product_name': 'Toy', 'sales_period': '100'}])
    window.show_rows([{'shop_name': 'Shop', '销量': '200'}])
    window.navigation.setCurrentRow(2)
    assert window.table.item(0, 0).text() == 'Shop'
    window.navigation.setCurrentRow(1)
    assert window.table.item(0, 0).text() == 'Toy'
    assert window.metrics['products'].text() == '1'
    assert window.metrics['shops'].text() == '1'
    window.show_rows([{'creator_name': 'Creator'}])
    window.navigation.setCurrentRow(3)
    assert window.creator_table.rowCount() == 1
    assert window.metrics['creators'].text() == '1'
    window.close()
