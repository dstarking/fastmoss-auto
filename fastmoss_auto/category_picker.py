"""Noneditable cascading category choices; stopping at any parent is valid."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QComboBox, QLabel


class CategoryPicker(QWidget):
    editingFinished = Signal()

    def __init__(self, preferred='', parent=None):
        super().__init__(parent)
        self.preferred = preferred
        self.paths = []
        self.combos = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.set_paths([])

    def text(self):
        parts = []
        for combo in self.combos:
            value = combo.currentData()
            if not value:
                break
            parts.append(value)
        return ' / '.join(parts)

    def setText(self, value):
        self.preferred = str(value)
        selected = [part.strip() for part in str(value).split('/') if part.strip()]
        prefix = []
        for level, combo in enumerate(self.combos):
            self._populate(level, prefix)
            combo.blockSignals(True)
            index = combo.findData(selected[level]) if level < len(selected) else 0
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
            if combo.currentData():
                prefix.append(combo.currentData())
            else:
                break
        if len(prefix) < len(selected):
            # Do not silently broaden a remembered leaf selection to its parent.
            self.combos[0].blockSignals(True)
            self.combos[0].setCurrentIndex(0)
            self.combos[0].blockSignals(False)
            prefix = []
        self._refresh_children(len(prefix))

    def set_paths(self, paths, preferred=None):
        self.paths = sorted({tuple(path) for path in paths if isinstance(path, (list, tuple)) and path
                             and all(isinstance(part, str) and part.strip() for part in path)})
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.combos = []
        depth = max(3, max((len(path) for path in self.paths), default=1))
        for level in range(depth):
            holder = QWidget()
            layout = QVBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(3)
            label = ['一级（必选）', '二级（可选）', '三级（可选）'][level] if level < 3 else f'第{level+1}级（可选）'
            layout.addWidget(QLabel(label))
            combo = QComboBox()
            combo.setEditable(False)
            combo.setMinimumWidth(120)
            layout.addWidget(combo)
            self.grid.addWidget(holder, level // 3, level % 3)
            self.combos.append(combo)
            combo.currentIndexChanged.connect(lambda _, depth=level: self._changed(depth))
        self.setText(self.preferred if preferred is None else preferred)

    def _populate(self, level, prefix):
        combo = self.combos[level]
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('请选择一级类目' if level == 0 else '全部子类（停在父类）', '')
        choices = sorted({path[level] for path in self.paths if len(path) > level and tuple(path[:level]) == tuple(prefix)})
        if level and len(prefix) != level:
            choices = []
        for label in choices:
            combo.addItem(label, label)
        combo.setEnabled(bool(choices))
        combo.blockSignals(False)

    def _refresh_children(self, start):
        prefix = [combo.currentData() for combo in self.combos[:start] if combo.currentData()]
        for level in range(start, len(self.combos)):
            self._populate(level, prefix)
            # Child levels remain unselected until the user explicitly narrows scope.

    def _changed(self, level):
        self._refresh_children(level + 1)
        self.preferred = self.text()
        self.editingFinished.emit()
