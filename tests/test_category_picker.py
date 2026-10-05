import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from fastmoss_auto.category_picker import CategoryPicker
from fastmoss_auto.app import Window

PATHS = [['宠物用品'],['宠物用品','猫用品'],['宠物用品','猫用品','猫砂盆、猫厕所'],
         ['宠物用品','狗用品','牵引绳'],['美妆','唇部','口红']]


def app():
    return QApplication.instance() or QApplication([])


def test_parent_is_valid_and_descendants_are_optional():
    application = app()
    picker = CategoryPicker('宠物用品')
    picker.set_paths(PATHS)
    assert picker.text() == '宠物用品'
    assert picker.combos[1].currentData() == ''
    assert not picker.combos[2].isEnabled()
    assert all(not combo.isEditable() for combo in picker.combos)
    picker.combos[1].setCurrentIndex(picker.combos[1].findData('猫用品'))
    assert picker.text() == '宠物用品 / 猫用品'
    picker.combos[2].setCurrentIndex(picker.combos[2].findData('猫砂盆、猫厕所'))
    assert picker.text() == '宠物用品 / 猫用品 / 猫砂盆、猫厕所'
    picker.combos[1].setCurrentIndex(0)
    assert picker.text() == '宠物用品' and picker.combos[2].currentData() == ''


def test_parent_change_resets_children_and_unknown_path_does_not_broaden():
    application = app()
    picker = CategoryPicker()
    picker.set_paths(PATHS, '宠物用品 / 猫用品 / 猫砂盆、猫厕所')
    picker.combos[0].setCurrentIndex(picker.combos[0].findData('美妆'))
    assert picker.text() == '美妆'
    assert picker.combos[1].findData('猫用品') == -1
    picker.set_paths([['宠物用品']], '宠物用品 / 猫用品')
    assert picker.text() == ''
    picker.set_paths([], '宠物用品')
    assert picker.text() == '' and not picker.combos[0].isEnabled()


def configure(tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(tmp_path))
    settings = QSettings('FastMossAuto','Desktop')
    settings.clear()
    settings.setValue('country','新加坡')
    settings.setValue('category','宠物用品')


def test_country_cache_persists_and_is_isolated(tmp_path):
    application = app()
    configure(tmp_path)
    window = Window()
    window.navigation.setCurrentRow(1)
    window.categories_done({'schema_version':2,'country':'新加坡','paths':PATHS,'warnings':[]})
    assert window.job().category == '宠物用品'
    assert window.read_categories_btn.isEnabled()
    window.category.setText('宠物用品 / 猫用品 / 猫砂盆、猫厕所')
    window.save_settings()
    window.close()
    restored = Window()
    assert restored.category.text() == '宠物用品 / 猫用品 / 猫砂盆、猫厕所'
    restored.country.setCurrentText('泰国')
    assert restored.category.text() == '' and not restored.category.paths
    restored.categories_done({'schema_version':2,'country':'新加坡','paths':PATHS,'warnings':[]})
    assert restored.category.text() == ''  # a stale completion does not replace Thailand's selection
    restored.country.setCurrentText('新加坡')
    restored.category.setText('宠物用品')
    assert restored.job().category == '宠物用品'
    restored.navigation.setCurrentRow(2)
    assert not restored.read_categories_btn.isEnabled() and restored.job().category == ''
    restored.close()


def test_read_button_snapshots_configuration_and_uses_worker(tmp_path, monkeypatch):
    application = app()
    configure(tmp_path)
    window = Window()
    window.navigation.setCurrentRow(1)
    window.source.setText('source')
    window.bsk.setText('C:/tools/bsk.exe')
    monkeypatch.setattr('fastmoss_auto.app.load_sections',lambda source: {})
    seen = {}
    def read(self,*args):
        seen['args'] = args
        return {'schema_version':2,'country':'新加坡','paths':PATHS,'warnings':[]}
    monkeypatch.setattr('fastmoss_auto.app.CategoryReader.read',read)
    monkeypatch.setattr(window,'run_work',lambda fn,callback: callback(fn(lambda *args: None)))
    window.read_categories_btn.click()
    assert seen['args'][0:3] == ('新加坡','source','C:/tools/bsk.exe')
    assert window.category.text() == '宠物用品'
    window.close()


def test_refresh_hides_old_controls_immediately():
    application = app()
    picker = CategoryPicker('宠物用品')
    picker.set_paths(PATHS)
    picker.show()
    application.processEvents()
    old_holder = picker.combos[0].parentWidget()
    assert old_holder.isVisible()
    picker.set_paths(PATHS)
    assert not old_holder.isVisible()  # no event-loop/deferred-delete wait needed
    picker.close()
