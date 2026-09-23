import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from puma_trader.ui import MainWindow
from puma_trader.updater import write_install_marker


def main():
    write_install_marker()
    app = QApplication(sys.argv)
    app.setApplicationName("PUMA STOCK PRO")
    app.setStyle("Fusion")
    ico = Path(__file__).with_name("PUMA_STOCK_PRO.ico")
    svg = Path(__file__).with_name("PUMA_STOCK_PRO_ICON.svg")
    icon = ico if ico.exists() else svg
    if icon.exists():
        qicon = QIcon(str(icon))
        if not qicon.isNull():
            app.setWindowIcon(qicon)
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
