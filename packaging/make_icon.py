"""Render the app icon (packaging/timbre.ico) from the same SVG the app uses."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QByteArray, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

app = QGuiApplication([])
from timbre.ui.icons import svg  # noqa: E402

out = ROOT / "packaging" / "timbre.ico"
renderer = QSvgRenderer(QByteArray(svg("logo", "#2853D6")))
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
renderer.render(p)
p.end()
if not img.save(str(out), "ICO"):
    img.save(str(out.with_suffix(".png")), "PNG")
    print("ICO writer unavailable; wrote PNG instead")
else:
    print(f"wrote {out}")
