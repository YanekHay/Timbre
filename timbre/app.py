"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    try:  # taskbar groups under our own icon instead of python.exe
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Timbre.Desktop")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Timbre")
    app.setOrganizationName("Timbre")
    from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

    class _Style(QProxyStyle):
        """Fusion, with tooltips that appear quickly: the help icons rely on them."""

        def styleHint(self, hint, option=None, widget=None, data=None):
            if hint == QStyle.SH_ToolTip_WakeUpDelay:
                return 250
            if hint == QStyle.SH_ToolTip_FallAsleepDelay:
                return 4000
            return super().styleHint(hint, option, widget, data)

    app.setStyle(_Style(QStyleFactory.create("Fusion")))
    font = QFont("Segoe UI Variable Text")
    font.setPointSizeF(9.75)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)

    from .controller import Controller
    from .ui.main_window import MainWindow
    from .ui.theme import theme

    controller = Controller()
    theme().apply(controller.settings.theme)
    window = MainWindow(controller)
    window.show()
    controller.start_engine()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
