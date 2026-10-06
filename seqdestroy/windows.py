"""Persistent, independent visualization windows owned by the synth window."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow


class VisualizationWindow(QMainWindow):
    def __init__(self, owner, title, plot, settings, key, offset):
        super().__init__(owner, Qt.WindowType.Window)
        self.setWindowTitle('SeqAndDestroy · ' + title)
        self.setCentralWidget(plot)
        self.settings, self.key, self.offset = settings, key, offset
        self.action = QAction(title, owner)
        self.action.setCheckable(True)
        self.action.toggled.connect(self.toggle)
        self.reset_position()
        geometry = settings.value(f'visualizations/{key}/geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.ensure_on_screen()
        self.action.setChecked(settings.value(f'visualizations/{key}/visible', True, type=bool))

    def ensure_on_screen(self):
        # Require the title bar to be reachable, even after a monitor is unplugged.
        frame = self.frameGeometry()
        title = frame.adjusted(0, 0, 0, -max(0, frame.height()-35))
        if not any(screen.availableGeometry().contains(title) for screen in QApplication.screens()):
            self.reset_position()

    def reset_position(self):
        screen = self.parentWidget().screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if self.isMaximized() or self.isMinimized():
            self.showNormal()
        self.resize(min(850, area.width()-40), min(330, area.height()-40))
        self.move(area.x()+min(30+self.offset*40,max(0,area.width()-self.width())),
                  area.y()+min(60+self.offset*90,max(0,area.height()-self.height())))

    def toggle(self, visible):
        if visible:
            self.ensure_on_screen()
            self.show()
            self.raise_()
        else:
            self.hide()

    def closeEvent(self, event):
        self.action.setChecked(False)
        event.ignore()  # Closing hides; the same widget and analysis remain available.

    def save(self):
        self.settings.setValue(f'visualizations/{self.key}/geometry', self.saveGeometry())
        self.settings.setValue(f'visualizations/{self.key}/visible', self.action.isChecked())
