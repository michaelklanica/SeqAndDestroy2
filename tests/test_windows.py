import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from seqdestroy.app import Window


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=QSettings(str(Path(self.tmp.name)/'layout.ini'),QSettings.Format.IniFormat)
        self.window=Window(settings=self.settings)
        self.window.show(); self.app.processEvents()

    def tearDown(self):
        self.window.close(); self.tmp.cleanup()

    def test_close_and_reopen(self):
        plot=self.window.visualizations['scope']
        self.assertTrue(plot.isWindow()); self.assertTrue(plot.isVisible())
        plot.close(); self.app.processEvents()
        self.assertFalse(plot.isVisible()); self.assertFalse(plot.action.isChecked())
        self.assertTrue(self.window.isVisible())
        plot.action.trigger(); self.app.processEvents()
        self.assertTrue(plot.isVisible()); self.assertIs(plot.centralWidget(),self.window.scope)

    def test_layout_persists_and_owner_closes_all(self):
        scope=self.window.visualizations['scope']; scope.resize(610,270); scope.move(45,55)
        self.window.visualizations['spectrum'].action.setChecked(False)
        self.app.processEvents(); size=scope.size()
        self.window.close()
        self.assertTrue(all(not w.isVisible() for w in self.window.visualizations.values()))
        self.window=Window(settings=self.settings); self.window.show(); self.app.processEvents()
        self.assertEqual(self.window.visualizations['scope'].size(),size)
        self.assertFalse(self.window.visualizations['spectrum'].action.isChecked())
        self.assertFalse(self.window.visualizations['spectrum'].isVisible())

    def test_hidden_plots_skip_refresh_and_defer_image(self):
        for w in self.window.visualizations.values():w.action.setChecked(False)
        with patch.object(self.window.scope,'update') as scope, patch.object(self.window.spectrum,'update') as spectrum:
            self.window.display_audio(np.ones((1000,2),np.float32))
            scope.assert_not_called(); spectrum.assert_not_called()
        graph=self.window.spectrogram
        graph.set_data(np.full((256,8),-30,np.float32),1)
        self.assertIsNone(graph.image); self.assertIsNotNone(graph.pending_data)
        self.window.visualizations['spectrogram'].action.setChecked(True); self.app.processEvents()
        self.assertIsNotNone(graph.image); self.assertIsNone(graph.pending_data)

    def test_reset_and_recovery_preserve_visibility(self):
        scope=self.window.visualizations['scope']; scope.move(-20000,-20000)
        scope.ensure_on_screen()
        self.assertTrue(any(s.availableGeometry().intersects(scope.frameGeometry()) for s in self.app.screens()))
        self.window.visualizations['spectrum'].action.setChecked(False)
        self.window.reset_visualization_positions(); self.window.bring_visualizations_forward()
        self.assertFalse(self.window.visualizations['spectrum'].isVisible())
