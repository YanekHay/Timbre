"""A small, consistent line-icon set (24px grid, 1.75 stroke), recoloured per theme."""

from __future__ import annotations

import weakref
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="{c}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"'
_F = 'fill="{c}" stroke="none"'

PATHS = {
    "studio": f'<g {_S}><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2"/></g>',
    "batch": f'<g {_S}><rect x="4" y="4" width="16" height="5" rx="1.5"/><rect x="4" y="11" width="16" height="4" rx="1.2"/>'
             f'<rect x="4" y="17" width="16" height="3" rx="1"/></g>',
    "voices": f'<g {_S}><circle cx="9" cy="8" r="3.5"/><path d="M3 20c.8-3.4 3.2-5.5 6-5.5s5.2 2.1 6 5.5"/>'
              f'<path d="M17.5 6.5a4 4 0 0 1 0 5M20 4a7.5 7.5 0 0 1 0 10"/></g>',
    "history": f'<g {_S}><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></g>',
    "devices": f'<g {_S}><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx=".8"/>'
               f'<path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/></g>',
    "settings": f'<g {_S}><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></g>',
    "play": f'<path {_F} d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/>',
    "pause": f'<g {_F}><rect x="6.5" y="5" width="4" height="14" rx="1"/><rect x="13.5" y="5" width="4" height="14" rx="1"/></g>',
    "stop": f'<rect {_F} x="6" y="6" width="12" height="12" rx="2"/>',
    "folder": f'<path {_S} d="M3.5 7.5A2 2 0 0 1 5.5 5.5h3.6l2 2h7.4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "copy": f'<g {_S}><rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/></g>',
    "plus": f'<path {_S} d="M12 5v14M5 12h14"/>',
    "x": f'<path {_S} d="M6 6l12 12M18 6L6 18"/>',
    "trash": f'<g {_S}><path d="M4.5 7h15M10 4h4M6.5 7l.8 11.2a2 2 0 0 0 2 1.8h5.4a2 2 0 0 0 2-1.8L17.5 7"/></g>',
    "download": f'<g {_S}><path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/></g>',
    "upload": f'<g {_S}><path d="M12 15V4M7.5 8.5L12 4l4.5 4.5M5 19.5h14"/></g>',
    "refresh": f'<g {_S}><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/></g>',
    "chevron-down": f'<path {_S} d="M6.5 9.5L12 15l5.5-5.5"/>',
    "chevron-right": f'<path {_S} d="M9.5 6.5L15 12l-5.5 5.5"/>',
    "check": '<path fill="none" stroke="{c}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M5.5 12.5l4 4 9-9"/>',
    "mic": f'<g {_S}><rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5"/></g>',
    "file": f'<g {_S}><path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/><path d="M14 3.5V8h4.5M9 13h6M9 16.5h4"/></g>',
    "save": f'<g {_S}><path d="M5.5 4.5h10l3 3v10a2 2 0 0 1-2 2h-11a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2z"/><path d="M8.5 4.5v4h6v-4M8 19.5v-5h8v5"/></g>',
    "tag": f'<g {_S}><path d="M3.5 12.2V5.5a2 2 0 0 1 2-2h6.7l8.3 8.3a2 2 0 0 1 0 2.8l-5.9 5.9a2 2 0 0 1-2.8 0z"/><circle cx="8.5" cy="8.5" r="1.3"/></g>',
    "bolt": f'<path {_S} d="M13 3.5L5.5 13.5h6l-1 7 7.5-10h-6z"/>',
    "cpu": f'<g {_S}><rect x="4.5" y="4.5" width="15" height="15" rx="2.5"/><path d="M9 9h6v6H9z"/></g>',
    "external": f'<g {_S}><path d="M13.5 4.5h6v6M19.5 4.5l-8 8M17.5 13.5v4a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h4"/></g>',
    "dot": f'<circle {_F} cx="12" cy="12" r="4"/>',
    "volume": f'<g {_S}><path d="M4.5 9.5v5h3.5l4.5 4v-13l-4.5 4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/></g>',
    "logo": '<rect x="1" y="1" width="22" height="22" rx="6" fill="{c}"/>'
            '<g fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round">'
            '<path d="M6.5 10.5v3M9.5 8v8M12.5 6v12M15.5 9v6M18 11v2"/></g>',
}

_cache: dict[tuple, QIcon] = {}
_bindings: list[tuple[weakref.ref, str, str, int]] = []
_dir: Path | None = None


def svg(name: str, color: str) -> bytes:
    body = PATHS[name].replace("{c}", color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode()


def pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    from .theme import P
    color = color or P().text2
    key = (name, color, size)
    if key not in _cache:
        _cache[key] = QIcon(pixmap(name, color, size))
    return _cache[key]


def file_url(name: str, color: str) -> str:
    """Write the icon to a cache dir so stylesheets can reference it (e.g. combo arrows)."""
    global _dir
    if _dir is None:
        from ..paths import cache_dir
        _dir = cache_dir() / "icons"
        _dir.mkdir(parents=True, exist_ok=True)
    path = _dir / f"{name}-{color.strip('#')}.svg"
    if not path.exists():
        path.write_bytes(svg(name, color))
    return path.as_posix()


def bind(widget, name: str, role: str = "text2", size: int = 18) -> None:
    """Set an icon that follows the theme. role is a Palette attribute name."""
    from .theme import P
    widget.setIcon(icon(name, getattr(P(), role), size))
    widget.setIconSize(QSize(size, size))
    _bindings[:] = [b for b in _bindings if b[0]() is not None and b[0]() is not widget]
    _bindings.append((weakref.ref(widget), name, role, size))


def refresh_all() -> None:
    from .theme import P
    alive = []
    for ref, name, role, size in _bindings:
        w = ref()
        if w is None:
            continue
        try:
            w.setIcon(icon(name, getattr(P(), role), size))
        except RuntimeError:  # deleted C++ object
            continue
        alive.append((ref, name, role, size))
    _bindings[:] = alive
