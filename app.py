import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from puma_trader.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PUMA STOCK PRO")
    app.setStyle("Fusion")
    icon_path = Path(__file__).with_name("PUMA_STOCK_PRO_ICON.svg")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
