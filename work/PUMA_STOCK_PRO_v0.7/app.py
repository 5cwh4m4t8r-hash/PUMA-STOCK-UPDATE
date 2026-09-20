import sys
from PySide6.QtWidgets import QApplication
from puma_trader.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PUMA STOCK PRO")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
