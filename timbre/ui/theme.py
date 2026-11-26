"""Design tokens and the Qt stylesheet built from them.

One accent colour, neutral surfaces, 8px spacing grid, 6/10px radii.
Every colour in the app comes from here, so light and dark stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtCore import Qt


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    rail: str
    surface: str
    surface2: str
    hover: str
    border: str
    border_strong: str
    text: str
    text2: str
    text3: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_weak: str
    success: str
    warning: str
    danger: str
    wave: str


LIGHT = Palette(
    name="light",
    bg="#F6F6F4", rail="#EFEFEC", surface="#FFFFFF", surface2="#F3F3F0", hover="#EAEAE6",
    border="#E3E3DE", border_strong="#CFCFC9",
    text="#1B1B19", text2="#5C5C57", text3="#8F8F89",
    accent="#2853D6", accent_hover="#1F45BD", accent_text="#FFFFFF", accent_weak="#E6ECFB",
    success="#1E8E52", warning="#B7791F", danger="#C93B3B", wave="#C9C9C3",
)

DARK = Palette(
    name="dark",
    bg="#131313", rail="#181818", surface="#1C1C1C", surface2="#232323", hover="#2A2A2A",
    border="#2C2C2C", border_strong="#3A3A3A",
    text="#ECECE9", text2="#A5A5A0", text3="#6E6E69",
    accent="#7B9BFF", accent_hover="#93AEFF", accent_text="#0E1530", accent_weak="#1E2A4D",
    success="#4CC38A", warning="#E3A948", danger="#F06C6C", wave="#3D3D3A",
)

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FALLBACK = "Segoe UI"


class ThemeManager(QObject):
    changed = Signal(object)  # Palette

    def __init__(self):
        super().__init__()
        self.mode = "system"
        self.palette = LIGHT
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.mode == "system" and self.apply(self.mode))

    def system_is_dark(self) -> bool:
        try:
            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            return False

    def apply(self, mode: str) -> None:
        self.mode = mode
        dark = mode == "dark" or (mode == "system" and self.system_is_dark())
        self.palette = DARK if dark else LIGHT
        app = QGuiApplication.instance()
        app.setPalette(qpalette(self.palette))
        app.setStyleSheet(stylesheet(self.palette))
        self.changed.emit(self.palette)


THEME: ThemeManager | None = None


def theme() -> ThemeManager:
    global THEME
    if THEME is None:
        THEME = ThemeManager()
    return THEME


def P() -> Palette:
    return theme().palette


def qpalette(p: Palette) -> QPalette:
    pal = QPalette()
    c = QColor
    pal.setColor(QPalette.Window, c(p.bg))
    pal.setColor(QPalette.WindowText, c(p.text))
    pal.setColor(QPalette.Base, c(p.surface))
    pal.setColor(QPalette.AlternateBase, c(p.surface2))
    pal.setColor(QPalette.Text, c(p.text))
    pal.setColor(QPalette.Button, c(p.surface))
    pal.setColor(QPalette.ButtonText, c(p.text))
    pal.setColor(QPalette.Highlight, c(p.accent))
    pal.setColor(QPalette.HighlightedText, c(p.accent_text))
    pal.setColor(QPalette.PlaceholderText, c(p.text3))
    pal.setColor(QPalette.ToolTipBase, c(p.surface))
    pal.setColor(QPalette.ToolTipText, c(p.text))
    pal.setColor(QPalette.Link, c(p.accent))
    return pal


def stylesheet(p: Palette) -> str:
    from . import icons
    chevron = icons.file_url("chevron-down", p.text2)
    check = icons.file_url("check", p.accent_text)
    return f"""
* {{ font-family: "{FONT_FAMILY}", "{FONT_FALLBACK}"; font-size: 13px; color: {p.text}; outline: 0; }}
QMainWindow, QDialog, #Page {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

/* ---------- rail ---------- */
#Rail {{ background: {p.rail}; border-right: 1px solid {p.border}; }}
#Wordmark {{ font-size: 15px; font-weight: 650; letter-spacing: 0.2px; }}
#RailButton {{ text-align: left; padding: 8px 12px; border: none; border-radius: 6px;
              color: {p.text2}; background: transparent; font-weight: 500; }}
#RailButton:hover {{ background: {p.hover}; color: {p.text}; }}
#RailButton:checked {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; }}

/* ---------- typography ---------- */
#PageTitle {{ font-size: 20px; font-weight: 650; }}
#PageSubtitle, .muted, #Muted {{ color: {p.text2}; }}
#Hint {{ color: {p.text3}; font-size: 12px; }}
#SectionTitle {{ font-size: 13px; font-weight: 600; }}
#Overline {{ color: {p.text3}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
#Value {{ color: {p.text2}; font-size: 12px; }}
#Mono {{ font-family: "Cascadia Mono", "Consolas"; font-size: 12px; color: {p.text2}; }}

/* ---------- surfaces ---------- */
#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
#Inset {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px; }}
#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}
#PlayerBar {{ background: {p.surface}; border-top: 1px solid {p.border}; }}
#SectionHeader {{ border: none; background: transparent; text-align: left; padding: 10px 0; font-weight: 600; }}
#SectionHeader:hover {{ color: {p.accent}; }}

/* ---------- buttons ---------- */
QPushButton, QToolButton {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 6px;
              padding: 6px 12px; font-weight: 500; }}
QPushButton:hover, QToolButton:hover {{ background: {p.hover}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p.text3}; border-color: {p.border}; background: {p.surface2}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.accent_text}; border: 1px solid {p.accent}; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:disabled {{ background: {p.border}; border-color: {p.border}; color: {p.text3}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {p.hover}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{ padding: 5px 8px; }}
QToolButton[variant="icon"] {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0; }}
QToolButton[variant="icon"]:hover {{ background: {p.hover}; }}
QToolButton[variant="icon"]:disabled {{ background: transparent; border-color: transparent; }}
#PlayButton {{ background: {p.text}; border-radius: 20px; }}
#PlayButton:hover {{ background: {p.text2}; }}
#PlayButton:disabled {{ background: {p.border}; }}
QPushButton[variant="danger"] {{ color: {p.danger}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {p.accent}; padding: 0; text-align: left; }}
QPushButton[variant="link"]:hover {{ text-decoration: underline; }}
QPushButton[variant="chip"] {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 12px;
              padding: 3px 10px; font-size: 12px; color: {p.text2}; }}
QPushButton[variant="chip"]:hover {{ border-color: {p.border_strong}; color: {p.text}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* segmented */
#Segmented {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 7px; }}
#Segment {{ background: transparent; border: none; border-radius: 5px; padding: 5px 10px; color: {p.text2}; font-weight: 500; }}
#Segment:hover {{ color: {p.text}; }}
#Segment:checked {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; }}
#Segment:disabled {{ color: {p.text3}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p.accent}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {p.text3}; background: {p.surface2}; }}
#Editor {{ border: none; background: transparent; font-size: 16px; padding: 4px; line-height: 150%; }}
#Editor:focus {{ border: none; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
    padding: 4px; selection-background-color: {p.accent_weak}; selection-color: {p.text}; outline: 0; }}
QSpinBox, QDoubleSpinBox {{ padding: 3px 8px; }}
/* Qt collapses the edit field of a styled spin box unless the (hidden) arrows are styled too. */
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 0px; border: none; }}
QAbstractSpinBox QLineEdit {{ padding: 0; margin: 0; border: none; background: transparent; }}
QComboBox QLineEdit {{ padding: 0; border: none; background: transparent; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.border_strong}; border-radius: 4px; background: {p.surface}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({check}); }}
QRadioButton {{ spacing: 8px; }}

QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0; border-radius: 8px;
    background: {p.surface}; border: 1px solid {p.border_strong}; }}
QSlider::handle:horizontal:hover {{ border-color: {p.accent}; }}
QSlider::sub-page:horizontal:disabled {{ background: {p.border_strong}; }}

QProgressBar {{ background: {p.border}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 2px; }}

/* ---------- lists & menus ---------- */
QListWidget, QTreeWidget, QTableWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border-radius: 6px; padding: 0; }}
QListWidget::item:hover {{ background: {p.hover}; }}
QListWidget::item:selected {{ background: {p.accent_weak}; color: {p.text}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p.hover}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSplitter::handle {{ background: transparent; }}

/* ---------- voice card ---------- */
#VoiceCard {{ background: {p.surface}; border: 1px solid {p.border_strong}; border-radius: 10px; padding: 10px 12px; text-align: left; }}
#VoiceCard:hover {{ border-color: {p.accent}; background: {p.surface}; }}
#VoiceCard[readonly="true"], #VoiceCard[readonly="true"]:hover {{ border-color: {p.border}; background: {p.surface2}; }}
#VoiceAvatar {{ background: {p.accent_weak}; border-radius: 18px; }}
#VoiceTitle {{ font-weight: 600; }}
#PickerRow {{ border-radius: 8px; }}
#PickerSection {{ color: {p.text3}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; padding: 10px 4px 4px 4px; }}

/* ---------- tabs ---------- */
#TabBar {{ border-bottom: 1px solid {p.border}; }}
#Tab {{ background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0;
        padding: 12px 4px 10px 4px; margin-right: 18px; color: {p.text2}; font-weight: 600; }}
#Tab:hover {{ color: {p.text}; }}
#Tab:checked {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
#GroupTitle {{ color: {p.text3}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; padding-top: 6px; }}
#ColHeader {{ color: {p.text3}; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; }}
#Callout {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px; padding: 10px 12px; color: {p.text2}; }}
#HelpIcon {{ background: transparent; }}

#Toast {{ background: {p.text}; color: {p.bg}; border-radius: 8px; padding: 10px 14px; }}
#Badge {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 9px; padding: 1px 8px; font-size: 11px; color: {p.text2}; }}
#BadgeAccent {{ background: {p.accent_weak}; border-radius: 9px; padding: 1px 8px; font-size: 11px; color: {p.accent}; font-weight: 600; }}
#BadgeSuccess {{ background: transparent; border: 1px solid {p.success}; border-radius: 9px; padding: 1px 8px; font-size: 11px; color: {p.success}; }}
#BadgeWarning {{ background: transparent; border: 1px solid {p.warning}; border-radius: 9px; padding: 1px 8px; font-size: 11px; color: {p.warning}; }}
#ErrorText {{ color: {p.danger}; }}
"""
