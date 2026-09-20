import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from puma_trader.ui import MainWindow
from puma_trader.swing_chart import SwingChart
from puma_trader.performance import DEVICE_PROFILE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PUMA STOCK PRO")
    app.setStyle("Fusion")
    if DEVICE_PROFILE.low_power:
        for effect in (Qt.UI_AnimateCombo, Qt.UI_AnimateTooltip, Qt.UI_FadeTooltip):
            app.setEffectEnabled(effect, False)

    win = MainWindow()
    if DEVICE_PROFILE.very_low_power:
        # Keep the entire history loaded and pannable; only the initial viewport
        # is narrower so the first paint is cheaper on 4 GB / old APU laptops.
        for chart in win.findChildren(SwingChart):
            chart.view_bars = min(chart.view_bars, 100)
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
