"""Dialog konfirmasi yang hidup DI DALAM jendela aplikasi.

Window manager bebas mengabaikan posisi yang diminta aplikasi (Wayland bahkan
melarang client menentukan posisi sama sekali), jadi QMessageBox sering muncul
di pinggir layar. Overlay ini widget biasa: posisinya kita yang menentukan,
sehingga selalu tepat di tengah jendela.
"""
from PySide6.QtCore import (QEasingCurve, QEvent, QEventLoop, QPropertyAnimation,
                            QSize, Qt, QVariantAnimation)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout,
                               QWidget)


class ConfirmOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("confirmOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.result = None
        self.card = None
        self._loop = None
        self._buttons = {}
        self._default = None
        self._colors = None
        self._rise = None
        self._animations = []
        self._dim = True
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self.hide()
        if parent is not None:
            parent.installEventFilter(self)

    # -- mengikuti ukuran jendela induk ---------------------------------
    def eventFilter(self, obj, event):
        parent = self.parentWidget()
        if obj is parent and event.type() == QEvent.Resize:
            self.setGeometry(parent.rect())
        return super().eventFilter(obj, event)

    def set_colors(self, c):
        self._colors = c
        self._apply_backdrop()
        if self.card is not None:
            self._style_card()

    def _apply_backdrop(self):
        background = "rgba(0, 0, 0, 96)" if self._dim else "transparent"
        self.setStyleSheet(f"#confirmOverlay {{ background: {background}; }}")

    def set_dim(self, dim: bool):
        """Tanpa peredup, naskah di belakang tetap terlihat jelas (pemilih font)."""
        self._dim = bool(dim)
        self._apply_backdrop()

    def _style_card(self):
        c = self._colors or {}
        accent = c.get("accent", "#8a6a2f")
        self.card.setStyleSheet(
            "QFrame#confirmCard {"
            f" background: {c.get('base', '#fbf8f0')};"
            f" border: 1px solid {c.get('border', '#d8d0bd')};"
            " border-radius: 10px; }"
            f" QLabel {{ color: {c.get('fg', '#2b2a26')}; }}"
            f" QLabel#confirmTitle {{ color: {c.get('heading', '#1d1b17')}; }}"
            " QPushButton#confirmPrimary {"
            f" background: {accent}; color: {c.get('bg', '#f2ede2')};"
            f" border: 1px solid {accent}; font-weight: bold; }}"
            " QPushButton#confirmPrimary:hover { background: "
            f"{c.get('heading', '#1d1b17')}; border-color: {c.get('heading', '#1d1b17')}; }}"
            " QPushButton#confirmDestructive {"
            f" color: {c.get('danger', '#a33a2a')};"
            f" background: {c.get('danger_bg', '#f7e2db')}; font-weight: bold;"
            f" border: 1px solid {c.get('danger', '#a33a2a')}; }}"
        )

    # -- membangun isi ---------------------------------------------------
    def _clear(self):
        while self._outer.count():
            item = self._outer.takeAt(0)
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    sub = layout.takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().deleteLater()
                layout.deleteLater()
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons = {}
        self._default = None

    def build(self, title, message, options, icon=None, content=None,
              dim: bool = True, placement: str = "center"):
        """options: [(key, label, kind)] dengan kind: primary | destructive | ''."""
        self._clear()
        self.card = QFrame(self)
        self.card.setObjectName("confirmCard")
        if content is not None:
            self.card.setMinimumWidth(520)
            self.card.setMaximumWidth(620)
        elif icon is not None and not icon.isNull():
            self.card.setMinimumWidth(450)   # teks tidak terlipat di samping ikon
            self.card.setMaximumWidth(560)
        else:
            self.card.setMinimumWidth(360)
            self.card.setMaximumWidth(480)
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(24, 20, 24, 16)
        card_lay.setSpacing(8)

        title_label = QLabel(title, self.card)
        title_label.setObjectName("confirmTitle")
        font = title_label.font()
        font.setPointSizeF(font.pointSizeF() + 1.5)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setWordWrap(True)
        if icon is not None and not icon.isNull():
            header = QHBoxLayout()
            header.setSpacing(14)
            icon_label = QLabel(self.card)
            icon_label.setPixmap(icon)
            icon_label.setFixedSize(icon.size())
            header.addWidget(icon_label, 0, Qt.AlignTop)
            header.addWidget(title_label, 1)
            card_lay.addLayout(header)
        else:
            card_lay.addWidget(title_label)

        if message:
            message_label = QLabel(message, self.card)
            message_label.setWordWrap(True)
            card_lay.addWidget(message_label)

        if content is not None:
            content.setParent(self.card)
            card_lay.addWidget(content)

        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        labels = []
        for key, label, kind in options:
            button = QPushButton(label, self.card)
            button.setMinimumWidth(88)
            button.clicked.connect(lambda _checked=False, k=key: self._finish(k))
            if kind == "primary":
                button.setObjectName("confirmPrimary")
                button.setDefault(True)
                button.setAutoDefault(True)
                self._default = button
            elif kind == "destructive":
                button.setObjectName("confirmDestructive")
            row.addWidget(button)
            self._buttons[key] = button
            labels.append(label)
        card_lay.addLayout(row)

        middle = QHBoxLayout()
        middle.addStretch(1)
        middle.addWidget(self.card)
        middle.addStretch(1)
        # spacer di atas kartu: dianimasikan supaya kartu "naik" ke posisinya
        self._rise = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._outer.addStretch(1)
        self._outer.addItem(self._rise)
        self._outer.addLayout(middle)
        if placement == "bottom":
            self._outer.addItem(QSpacerItem(0, 26, QSizePolicy.Minimum, QSizePolicy.Fixed))
        else:
            self._outer.addStretch(1)

        self.set_dim(dim)

        self._style_card()
        return labels

    # -- menampilkan ------------------------------------------------------
    def ask(self, title, message, options, icon=None, content=None,
            dim: bool = True, placement: str = "center"):
        self.build(title, message, options, icon, content, dim, placement)
        return self.run()

    def _animate_in(self):
        """Fade-in singkat + kartu naik ~10 px. Qt tidak punya transisi CSS,
        jadi ini dilakukan dengan animasi properti bawaan."""
        self._animations = []
        effect = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(170)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.start()
        self._animations.append(fade)

        rise = QVariantAnimation(self)
        rise.setDuration(200)
        rise.setStartValue(20.0)
        rise.setEndValue(0.0)
        rise.setEasingCurve(QEasingCurve.OutCubic)
        rise.valueChanged.connect(self._set_rise)
        rise.start()
        self._animations.append(rise)

    def _set_rise(self, value):
        if self._rise is None:
            return
        self._rise.changeSize(0, int(value), QSizePolicy.Minimum, QSizePolicy.Fixed)
        self._outer.invalidate()

    def run(self):
        parent = self.parentWidget()
        self.result = None
        if parent is not None:
            self.setGeometry(parent.rect())
        self._set_rise(20)
        self.raise_()
        self.show()
        self._animate_in()
        self.setFocus()
        if self._default is not None:
            self._default.setFocus()
        self._loop = QEventLoop()
        self._loop.exec()
        self._loop = None
        self.hide()
        return self.result

    def _finish(self, key):
        self.result = key
        if self._loop is not None:
            self._loop.quit()
        else:
            self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._finish("cancel")
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self._default is not None:
            self._default.click()
            return
        super().keyPressEvent(event)