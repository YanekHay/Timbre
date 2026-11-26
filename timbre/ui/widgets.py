"""Reusable building blocks. Styling lives in theme.py; these only set objectNames/properties."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QSlider, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

from . import icons


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def button(text: str = "", variant: str = "", icon: str = "", role: str = "text2",
           tooltip: str = "", size: int = 16) -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if icon:
        icons.bind(b, icon, "accent_text" if variant == "primary" else role, size)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def icon_button(icon: str, tooltip: str, role: str = "text2", size: int = 16) -> QToolButton:
    b = QToolButton()
    b.setProperty("variant", "icon")
    icons.bind(b, icon, role, size)
    b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(30, 30)
    return b


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFrameShape(QFrame.NoFrame)
    return f


def badge(text: str, kind: str = "") -> QLabel:
    w = QLabel(text)
    w.setObjectName({"accent": "BadgeAccent", "success": "BadgeSuccess",
                     "warning": "BadgeWarning"}.get(kind, "Badge"))
    w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return w


def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0), stretch_at: int | None = None) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for i, item in enumerate(items):
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, int):
            lay.addSpacing(item)
        elif isinstance(item, QWidget):
            lay.addWidget(item)
        else:
            lay.addLayout(item)
    return lay


def vbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for item in items:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, int):
            lay.addSpacing(item)
        elif isinstance(item, QWidget):
            lay.addWidget(item)
        else:
            lay.addLayout(item)
    return lay


class Card(QFrame):
    def __init__(self, parent=None, padding: int = 16, spacing: int = 12, name: str = "Card"):
        super().__init__(parent)
        self.setObjectName(name)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)

    def add(self, *items):
        for item in items:
            if isinstance(item, QWidget):
                self.body.addWidget(item)
            else:
                self.body.addLayout(item)
        return self


class Segmented(QFrame):
    """A segmented control. Emits the selected key."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for text, key in options:
            b = QPushButton(text)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        if options:
            self.buttons[options[0][1]].setChecked(True)

    def value(self) -> str:
        for key, b in self.buttons.items():
            if b.isChecked():
                return key
        return ""

    def set_value(self, key: str, emit: bool = False) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)
            if emit:
                self.changed.emit(key)

    def set_enabled_keys(self, keys: set[str]) -> None:
        for key, b in self.buttons.items():
            b.setEnabled(key in keys)


class Section(QWidget):
    """Collapsible inspector section with a quiet header."""

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.header = QPushButton()
        self.header.setObjectName("SectionHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setMinimumHeight(40)
        inner = QHBoxLayout(self.header)
        inner.setContentsMargins(0, 0, 2, 0)
        self.title = label(title, "SectionTitle")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.chevron = QLabel()
        self.chevron.setAttribute(Qt.WA_TransparentForMouseEvents)
        inner.addWidget(self.title)
        inner.addStretch(1)
        inner.addWidget(self.chevron)
        from .theme import theme
        theme().changed.connect(lambda *_: self._paint_chevron())
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 12)
        self.body.setSpacing(12)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(self.content)
        self.header.toggled.connect(self._toggle)
        self._toggle(expanded)

    def _toggle(self, on: bool) -> None:
        self.content.setVisible(on)
        self._paint_chevron()

    def _paint_chevron(self) -> None:
        from .theme import P
        name = "chevron-down" if self.header.isChecked() else "chevron-right"
        self.chevron.setPixmap(icons.pixmap(name, P().text3, 14))

    def add(self, *items):
        for item in items:
            if isinstance(item, QWidget):
                self.body.addWidget(item)
            else:
                self.body.addLayout(item)
        return self


class Field(QWidget):
    """Label (+ optional hint) above a control."""

    def __init__(self, title: str, control: QWidget | None = None, hint: str = "", trailing: QWidget | None = None,
                 help: str = ""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.title = label(title)
        self.title.setObjectName("FieldTitle")
        top.addWidget(self.title)
        if help:
            top.addWidget(HelpIcon(help))
        top.addStretch(1)
        if trailing:
            top.addWidget(trailing)
        lay.addLayout(top)
        if control is not None:
            lay.addWidget(control)
        if hint:
            h = label(hint, "Hint", wrap=True)
            lay.addWidget(h)


class _ScrollSafeSlider(QSlider):
    """Ignores the mouse wheel unless focused, so scrolling a panel never nudges values."""

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class SliderField(QWidget):
    """Slider with an editable numeric readout. Works in real units."""

    valueChanged = Signal(float)

    def __init__(self, title: str, lo: float, hi: float, step: float, value: float,
                 decimals: int = 2, suffix: str = "", hint: str = "", help: str = "",
                 ends: tuple[str, str] | None = None, default: float | None = None):
        super().__init__()
        self.scale = 1 / step
        self.decimals = decimals
        self.slider = _ScrollSafeSlider(Qt.Horizontal)
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setRange(round(lo * self.scale), round(hi * self.scale))
        self.slider.setCursor(Qt.PointingHandCursor)
        self.spin = QDoubleSpinBox() if decimals else QSpinBox()
        self.spin.setRange(lo, hi) if decimals else self.spin.setRange(int(lo), int(hi))
        if decimals:
            self.spin.setDecimals(decimals)
            self.spin.setSingleStep(step)
        else:
            self.spin.setSingleStep(int(step))
        if suffix:
            self.spin.setSuffix(suffix)
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.setFixedWidth(96)
        self.spin.setObjectName("Value")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(4)
        top.addWidget(label(title))
        if help:
            top.addWidget(HelpIcon(help))
        top.addStretch(1)
        if default is not None:
            # Double-click the value to go back to the default.
            self.spin.setToolTip(f"Default {default:g}{suffix}. Double-click the slider to reset.")
            self.slider.mouseDoubleClickEvent = lambda e: self.set_value(default) or self.valueChanged.emit(default)
        top.addWidget(self.spin)
        lay.addLayout(top)
        lay.addWidget(self.slider)
        if ends:
            row = QHBoxLayout()
            row.addWidget(label(ends[0], "Hint"))
            row.addStretch(1)
            row.addWidget(label(ends[1], "Hint"))
            lay.addLayout(row)
        if hint:
            lay.addWidget(label(hint, "Hint", wrap=True))
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.set_value(value)

    def _from_slider(self, v: int) -> None:
        real = v / self.scale
        self.spin.blockSignals(True)
        self.spin.setValue(real if self.decimals else int(real))
        self.spin.blockSignals(False)
        self.valueChanged.emit(real)

    def _from_spin(self, v) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(round(float(v) * self.scale))
        self.slider.blockSignals(False)
        self.valueChanged.emit(float(v))

    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, v: float) -> None:
        self.spin.setValue(v if self.decimals else int(v))
        self.slider.blockSignals(True)
        self.slider.setValue(round(v * self.scale))
        self.slider.blockSignals(False)


class Combo(QComboBox):
    """Combo box that stores data per item and never steals wheel events while scrolling."""

    def __init__(self, items: list[tuple[str, object]] | None = None):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(3)
        for text, data in items or []:
            self.addItem(text, data)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()

    def value(self):
        return self.currentData()

    def set_value(self, data) -> None:
        idx = self.findData(data)
        if idx >= 0:
            self.setCurrentIndex(idx)


class PathField(QWidget):
    changed = Signal(str)

    def __init__(self, placeholder: str = "", directory: bool = False, filter: str = "", parent=None):
        super().__init__(parent)
        self.directory = directory
        self.filter = filter
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.browse = button("Browse", icon="folder")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.browse)
        self.browse.clicked.connect(self._pick)
        self.edit.editingFinished.connect(lambda: self.changed.emit(self.edit.text()))

    def _pick(self) -> None:
        if self.directory:
            path = QFileDialog.getExistingDirectory(self, "Choose folder", self.edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose file", self.edit.text(), self.filter)
        if path:
            self.edit.setText(path)
            self.changed.emit(path)

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, v: str) -> None:
        self.edit.setText(v)


class Toast(QLabel):
    """Transient message anchored to the bottom-right of a parent widget."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setMaximumWidth(380)
        self.hide()
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.timer = QTimer(self, singleShot=True, timeout=self._fade_out)

    def show_message(self, text: str, ms: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move(parent.width() - self.width() - 24, parent.height() - self.height() - 96)
        self.raise_()
        self.show()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def _fade_out(self) -> None:
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._hide_once)
        self.anim.start()

    def _hide_once(self) -> None:
        self.anim.finished.disconnect(self._hide_once)
        self.hide()


def scroll_page(inner: QWidget):
    from PySide6.QtWidgets import QScrollArea
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(inner)
    return area


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", trailing: list[QWidget] | None = None):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(title, "PageTitle"))
        if subtitle:
            texts.addWidget(label(subtitle, "PageSubtitle"))
        lay.addLayout(texts)
        lay.addStretch(1)
        for w in trailing or []:
            lay.addWidget(w)


from PySide6.QtCore import QRect, QSize  # noqa: E402
from PySide6.QtWidgets import QLayout  # noqa: E402


class FlowLayout(QLayout):
    """Wraps children onto new lines, like inline text. Used for chips."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect, dry):
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x = rect.x()
                y += line + self._spacing
                line = 0
            if not dry:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()


def chips(labels, on_click) -> QWidget:
    holder = QWidget()
    flow = FlowLayout(holder)
    for text in labels:
        b = button(text, "chip")
        b.clicked.connect(lambda _=False, t=text: on_click(t))
        flow.addWidget(b)
    return holder


from PySide6.QtWidgets import QStackedWidget  # noqa: E402


class AdaptiveStack(QStackedWidget):
    """A stacked widget that takes the height of the visible page, not the tallest one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._fit)

    def _fit(self, *_):
        for i in range(self.count()):
            w = self.widget(i)
            policy = QSizePolicy.Preferred if i == self.currentIndex() else QSizePolicy.Ignored
            w.setSizePolicy(policy, policy)
            w.adjustSize() if i == self.currentIndex() else None
        self.adjustSize()
        self.updateGeometry()

    def addWidget(self, w):  # noqa: N802
        idx = super().addWidget(w)
        self._fit()
        return idx

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w else super().minimumSizeHint()


class HelpIcon(QLabel):
    """A small “?” that explains the setting next to it on hover (and on click, for touch/keyboard)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("HelpIcon")
        self.help = text
        self.setToolTip(f"<div style='max-width:300px'>{text}</div>")
        self.setCursor(Qt.WhatsThisCursor)
        self.setFixedSize(16, 16)
        from .theme import theme
        theme().changed.connect(lambda *_: self._paint())
        self._paint()

    def _paint(self) -> None:
        from .theme import P
        self.setPixmap(icons.pixmap("help", P().text3, 15))

    def mousePressEvent(self, e) -> None:
        from PySide6.QtWidgets import QToolTip
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), self.toolTip(), self)


class SummaryRow(QWidget):
    """Label on the left, value on the right; used for read-only settings summaries."""

    def __init__(self, title: str, value: str = "", help: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(4)
        lay.addWidget(label(title, "Muted"))
        if help:
            lay.addWidget(HelpIcon(help))
        lay.addStretch(1)
        self.value = ElidedLabel(value, mode=Qt.ElideMiddle)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.value, 3)

    def set(self, value: str) -> None:
        self.value.setText(value)


class TabBar(QWidget):
    """Underlined text tabs. Emits the selected key."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__()
        self.setObjectName("TabBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for text, key in options:
            b = QPushButton(text)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        lay.addStretch(1)
        if options:
            self.buttons[options[0][1]].setChecked(True)

    def set_value(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)
            self.changed.emit(key)


class ElidedLabel(QLabel):
    """One-line label that shortens long text with “…” and shows the full text on hover."""

    def __init__(self, text: str = "", name: str = "", mode=Qt.ElideRight):
        super().__init__()
        if name:
            self.setObjectName(name)
        self._full = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(24)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        self._full = text or ""
        self._elide()

    def text(self) -> str:
        return self._full

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, self._mode, max(self.width(), 24))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(min(fm.horizontalAdvance(self._full) + 4, 420), fm.height())


class OneOf(QWidget):
    """Shows exactly one of its panels; hidden panels take no space (unlike QStackedWidget)."""

    def __init__(self):
        super().__init__()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._panels: list[QWidget] = []
        self._current = 0

    def addWidget(self, w: QWidget) -> None:  # noqa: N802
        self._panels.append(w)
        self._lay.addWidget(w)
        w.setVisible(len(self._panels) - 1 == self._current)

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        self._current = i
        for k, w in enumerate(self._panels):
            w.setVisible(k == i)
