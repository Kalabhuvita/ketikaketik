"""Dua palet lengkap untuk Ketikaketik: day dan night.

Warna tidak pernah di-hardcode di widget mana pun; semuanya lewat THEMES.
"""
from PySide6.QtGui import QColor, QPalette

THEMES = {
    "day": {
        "bg": "#f2ede2",        # jendela / sidebar
        "base": "#fbf8f0",      # area editor
        "fg": "#2b2a26",
        "alt": "#e9e2d2",
        "border": "#d8d0bd",
        "dim": "#9a9385",
        "sel_bg": "#aecdf0",
        "sel_fg": "#101418",
        "match": "#ffe98a",
        "match_active": "#ffb347",
        "match_fg": "#1a1a1a",
        "code_bg": "#ece5d4",
        "accent": "#8a6a2f",
        "heading": "#1d1b17",
        "gutter_fg": "#a89f8c",
        "flash": "#ffcf5c",
        "danger": "#a33a2a",
        "danger_bg": "#f7e2db",
    },
    "night": {
        "bg": "#1d1d1b",
        "base": "#232320",
        "fg": "#d7d2c6",
        "alt": "#2a2a27",
        "border": "#44443e",
        "dim": "#98938a",
        "sel_bg": "#4a6a95",
        "sel_fg": "#eae8e1",
        "match": "#5c5020",
        "match_active": "#b5761f",
        "match_fg": "#f2eee3",
        "code_bg": "#2e2e2a",
        "accent": "#c8a95f",
        "heading": "#f0ece0",
        "gutter_fg": "#7a756a",
        "flash": "#7a6124",
        "danger": "#e08a72",
        "danger_bg": "#3a2622",
    },
}

THEME_LABEL = {"day": "Day (cream)", "night": "Night (warm dark)"}


def colors(name: str) -> dict:
    return THEMES.get(name, THEMES["day"])


def palette_for(name: str) -> QPalette:
    c = colors(name)
    p = QPalette()
    p.setColor(QPalette.Window, QColor(c["bg"]))
    p.setColor(QPalette.WindowText, QColor(c["fg"]))
    p.setColor(QPalette.Base, QColor(c["base"]))
    p.setColor(QPalette.AlternateBase, QColor(c["alt"]))
    p.setColor(QPalette.Text, QColor(c["fg"]))
    p.setColor(QPalette.Button, QColor(c["bg"]))
    p.setColor(QPalette.ButtonText, QColor(c["fg"]))
    p.setColor(QPalette.Highlight, QColor(c["sel_bg"]))
    p.setColor(QPalette.HighlightedText, QColor(c["sel_fg"]))
    p.setColor(QPalette.ToolTipBase, QColor(c["alt"]))
    p.setColor(QPalette.ToolTipText, QColor(c["fg"]))
    p.setColor(QPalette.PlaceholderText, QColor(c["dim"]))
    p.setColor(QPalette.Link, QColor(c["accent"]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["dim"]))
    return p


def stylesheet_for(name: str) -> str:
    c = colors(name)
    return f"""
    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:hover {{ background: {c['dim']}; }}
    QLineEdit, QComboBox, QSpinBox {{
        background: {c['base']}; color: {c['fg']};
        border: 1px solid {c['border']}; border-radius: 4px; padding: 3px 6px;
        selection-background-color: {c['sel_bg']}; selection-color: {c['sel_fg']};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QListWidget, QTreeWidget, QTextBrowser {{
        background: {c['base']}; color: {c['fg']};
        border: 1px solid {c['border']};
        selection-background-color: {c['sel_bg']}; selection-color: {c['sel_fg']};
    }}
    QListWidget::item, QTreeWidget::item {{ padding: 3px 2px; }}
    QMenuBar {{ background: {c['bg']}; color: {c['fg']}; }}
    QMenuBar::item:selected {{ background: {c['alt']}; }}
    QMenu {{ background: {c['bg']}; color: {c['fg']}; border: 1px solid {c['border']}; }}
    QMenu::item:selected {{ background: {c['sel_bg']}; color: {c['sel_fg']}; }}
    QToolTip {{ background: {c['alt']}; color: {c['fg']}; border: 1px solid {c['border']}; }}
    QStatusBar {{ background: {c['bg']}; color: {c['dim']}; }}
    QStatusBar QLabel {{ color: {c['dim']}; padding: 0 6px; }}
    QScrollBar:vertical {{ background: {c['alt']}; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 28px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['dim']}; }}
    QScrollBar:horizontal {{ background: {c['alt']}; height: 11px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 28px; border-radius: 5px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolButton {{ background: transparent; color: {c['fg']}; border: 1px solid transparent;
                   border-radius: 4px; padding: 3px 6px; }}
    QToolButton:hover {{ background: {c['alt']}; border: 1px solid {c['border']}; }}
    QToolButton:checked {{ background: {c['sel_bg']}; color: {c['sel_fg']}; }}
    QPushButton {{ background: {c['alt']}; color: {c['fg']}; border: 1px solid {c['border']};
                   border-radius: 4px; padding: 5px 12px; }}
    QPushButton:hover {{ background: {c['sel_bg']}; color: {c['sel_fg']}; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; }}
    QTabBar::tab {{ background: {c['bg']}; color: {c['dim']}; padding: 5px 10px; }}
    QTabBar::tab:selected {{ background: {c['base']}; color: {c['fg']}; }}
    """


def apply_theme(app, name: str) -> None:
    app.setPalette(palette_for(name))
    app.setStyleSheet(stylesheet_for(name))