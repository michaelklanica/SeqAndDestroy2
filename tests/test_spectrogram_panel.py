import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
import numpy as np
from PySide6.QtWidgets import QApplication
from seqdestroy.spectrogram import Spectrogram

class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def wait(self,panel):
        deadline=time.monotonic()+10
        while panel.worker is not None or panel.dirty:
            self.app.processEvents()
            if panel.worker:panel.worker.wait(2)
            self.assertLess(time.monotonic(),deadline)
        self.app.processEvents()
    def test_reanalysis_latest_wins_zoom_and_cancel(self):
        panel=Spectrogram(); panel.resize(1100,500); panel.show()
        try:
            t=np.arange(48000)/48000; a=np.column_stack((np.sin(2*np.pi*440*t),np.sin(2*np.pi*880*t))).astype(np.float32)
            panel.set_audio(a); panel.quality.setCurrentText('Detailed'); panel.mode.setCurrentText('Transient')
            self.wait(panel); self.assertIn('Detailed / Transient',panel.status.text())
            panel.begin.setValue(.2); panel.end.setValue(.4); panel.low.setValue(200); panel.high.setValue(1000); panel.request()
            self.wait(panel); self.assertEqual(panel.canvas.bounds,(.2,.4,200.,1000.)); self.assertIsNotNone(panel.image)
            panel.grab().save('/tmp/seqdestroy-detailed.png')
            image=panel.image; panel.mode.setCurrentText('Tonal'); panel.cancel(); self.wait(panel)
            self.assertIs(panel.image,image)
        finally:panel.shutdown(); panel.close()
