"""Pemilih font di dalam jendela, dengan pratinjau langsung ke naskah.

Dialog font bawaan sistem diganti karena dua alasan: di PySide6 6.12 nilai
kembaliannya tidak sesuai urutan yang didokumentasikan (bug yang membuat font
tidak bisa diganti), dan dialog itu tidak bisa memperlihatkan hasilnya di naskah
selagi kamu memilih.
"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDoubleSpinBox, QFontComboBox, QGridLayout, QLabel,
                               QSpinBox, QVBoxLayout, QWidget)


class FontChooser(QWidget):
    changed = Signal(str, float, float)      # (family, size, line spacing)

    def __init__(self, family: str = "", size: float = 12.0,
                 spacing: float = 1.35, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)
        outer.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.combo = QFontComboBox(self)
        self.combo.setFontFilters(QFontComboBox.ScalableFonts)
        self.combo.setMinimumWidth(250)
        if family:
            self.combo.setCurrentFont(QFont(family))

        self.spin = QSpinBox(self)
        self.spin.setRange(6, 72)
        self.spin.setSuffix(" pt")
        self.spin.setValue(int(round(size)))
        self.spin.setMinimumWidth(92)

        self.spacing = QDoubleSpinBox(self)
        self.spacing.setRange(1.0, 2.6)
        self.spacing.setSingleStep(0.05)
        self.spacing.setDecimals(2)
        self.spacing.setValue(max(1.0, min(2.6, float(spacing))))
        self.spacing.setMinimumWidth(92)

        self.sample = QLabel("Hujan turun, dan kalimat ini menjadi panjang sekali.", self)
        self.sample.setWordWrap(True)
        self.sample.setMinimumHeight(38)

        grid.addWidget(QLabel("Font", self), 0, 0)
        grid.addWidget(self.combo, 0, 1, 1, 3)
        grid.addWidget(QLabel("Size", self), 1, 0)
        grid.addWidget(self.spin, 1, 1)
        grid.addWidget(QLabel("Spacing", self), 1, 2)
        grid.addWidget(self.spacing, 1, 3)
        grid.addWidget(self.sample, 2, 0, 1, 4)
        grid.setColumnStretch(1, 1)

        outer.addLayout(grid)

        self.combo.currentFontChanged.connect(self._emit)
        self.spin.valueChanged.connect(self._emit)
        self.spacing.valueChanged.connect(self._emit)
        self._refresh_sample()

    # -- nilai ----------------------------------------------------------
    def family(self) -> str:
        return self.combo.currentFont().family()

    def size(self) -> float:
        return float(self.spin.value())

    def line_spacing(self) -> float:
        return float(self.spacing.value())

    # -- pratinjau ------------------------------------------------------
    def _emit(self, *_args):
        self._refresh_sample()
        self.changed.emit(self.family(), self.size(), self.line_spacing())

    def _refresh_sample(self):
        font = QFont(self.family())
        font.setPointSizeF(min(20.0, max(10.0, self.size())))
        self.sample.setFont(font)