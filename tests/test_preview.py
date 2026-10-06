import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from seqdestroy.app import Export, Window
import numpy as np

class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def run_worker(self,worker):
        output=[]; errors=[]
        worker.prepared.connect(lambda a,db,preview:output.append((a,db,preview)))
        worker.result.connect(errors.append)
        worker.start()
        while worker.isRunning():self.app.processEvents(); worker.wait(5)
        self.app.processEvents()
        self.assertTrue(output,errors)
        return output[0]
    def test_preview_matches_export(self):
        from seqdestroy.engine import Patch
        p=Patch(pan1=-.5,pan2=.8,release=.05)
        preview=self.run_worker(Export(p,65,.12))
        with tempfile.TemporaryDirectory() as d:
            exported=self.run_worker(Export(p,65,.12,str(Path(d)/'a.wav')))
        np.testing.assert_array_equal(preview[0],exported[0]); self.assertIsNone(preview[1]); self.assertIsNone(exported[1])
        self.assertTrue(preview[2]); self.assertFalse(exported[2])
    def test_window_analysis(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        settings=QSettings(str(Path(temp.name)/'layout.ini'),QSettings.Format.IniFormat)
        w=Window(settings=settings); w.show(); self.app.processEvents()
        w.prepared(np.zeros((4800,2),np.int16),np.full((256,10),-100,np.float32),False)
        self.assertAlmostEqual(w.spectrogram.duration,.1)
        self.assertFalse(w.grab().isNull()); w.grab().save('/tmp/seqdestroy-stereo.png'); w.close()
