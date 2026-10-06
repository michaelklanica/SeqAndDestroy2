import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from seqdestroy.spectrogram import Spectrogram
from seqdestroy.charts import Plot

class GestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.panel=Spectrogram(); self.panel.resize(1200,600); self.panel.show()
        self.panel.set_audio(np.zeros((48000,2),np.int16)); self.wait()
    def tearDown(self):self.panel.shutdown(); self.panel.close()
    def wait(self):
        deadline=time.monotonic()+10
        while self.panel.worker is not None or self.panel.dirty or self.panel.mouse_timer.isActive():
            self.app.processEvents(); QTest.qWait(5)
            self.assertLess(time.monotonic(),deadline)
        self.app.processEvents()
    def test_wheel_anchor_and_fields(self):
        c=self.panel.canvas; point=c.area().center(); old=c.coords(point)
        event=QWheelEvent(point,point,QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        self.app.sendEvent(c,event); self.wait()
        begin,end,low,high=c.bounds
        self.assertAlmostEqual(end-begin,.8,places=5)
        new=c.coords(point); self.assertAlmostEqual(old[0],new[0],places=5); self.assertAlmostEqual(old[1],new[1],places=2)
        self.assertAlmostEqual(self.panel.begin.value(),begin); self.assertAlmostEqual(self.panel.high.value(),high)
    def test_rectangle_pan_and_reset(self):
        c=self.panel.canvas; area=c.area()
        first=QPoint(int(area.left()+area.width()*.25),int(area.top()+area.height()*.25))
        last=QPoint(int(area.left()+area.width()*.75),int(area.top()+area.height()*.75))
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=first); QTest.mouseMove(c,last); QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=last); self.wait()
        before=c.bounds; self.assertLess(before[1]-before[0],.6)
        center=c.area().center().toPoint(); shifted=center+QPoint(40,0)
        QTest.mousePress(c,Qt.MouseButton.RightButton,pos=center); QTest.mouseMove(c,shifted); QTest.mouseRelease(c,Qt.MouseButton.RightButton,pos=shifted); self.wait()
        self.assertLess(c.bounds[0],before[0]); self.assertAlmostEqual(c.bounds[1]-c.bounds[0],before[1]-before[0],places=5)
        QTest.mouseDClick(c,Qt.MouseButton.LeftButton,pos=center); self.wait()
        np.testing.assert_allclose(c.bounds,(0,1,40,24000))
    def test_mapping_limits_and_paint(self):
        c=self.panel.canvas; area=c.area()
        np.testing.assert_allclose(c.coords(area.bottomLeft()),(0,40))
        np.testing.assert_allclose(c.coords(area.topRight()),(1,24000))
        c.emit_range((-10,10,.01,100000)); self.wait()
        self.assertGreaterEqual(c.bounds[0],0); self.assertLessEqual(c.bounds[1],1)
        self.assertGreaterEqual(c.bounds[2],1); self.assertLessEqual(c.bounds[3],24000)
        QTest.mouseMove(c,c.area().center().toPoint()); self.assertFalse(self.panel.grab().isNull()); self.panel.grab().save('/tmp/seqdestroy-axes.png')
        for spectrum in (False,True):
            plot=Plot(spectrum); plot.resize(700,350); plot.show(); QTest.mouseMove(plot,plot.area().center().toPoint())
            self.assertFalse(plot.grab().isNull()); plot.close()
