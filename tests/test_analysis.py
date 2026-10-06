import unittest
import numpy as np
from seqdestroy.analysis import analyze
from seqdestroy.engine import Cancelled

class AnalysisTests(unittest.TestCase):
    def test_close_tones(self):
        rate=48000; t=np.arange(rate)/rate
        a=.3*np.sin(2*np.pi*200*t)+.3*np.sin(2*np.pi*220*t)
        r=analyze(a,quality='Detailed',mode='Tonal',frequency_range=(170,250))
        power=r.db[:,len(r.times)//2]
        peaks=np.flatnonzero((power[1:-1]>power[:-2]) & (power[1:-1]>power[2:]))+1
        for hz in (200,220):self.assertLess(abs(r.frequencies[peaks]-hz).min(),3)
    def test_transient_timing_and_zoom(self):
        a=np.zeros(48000,np.float32); a[24000]=1
        full=analyze(a,quality='Detailed',mode='Transient')
        self.assertAlmostEqual(full.times[np.argmax(full.db.max(axis=0))],.5,delta=.002)
        zoom=analyze(a,quality='Detailed',mode='Transient',time_range=(.49,.51),frequency_range=(100,1000))
        self.assertAlmostEqual(zoom.times[0],.49); self.assertAlmostEqual(zoom.times[-1],.51)
        self.assertAlmostEqual(zoom.frequencies[0],100); self.assertAlmostEqual(zoom.frequencies[-1],1000)
    def test_quality_limits_progress_and_cancellation(self):
        a=np.zeros(48000,np.float32); results=[]
        for q,limit in [('Fast',512),('Balanced',1600),('Detailed',4096)]:
            progress=[]; r=analyze(a,quality=q,mode='Transient',progress=progress.append)
            self.assertLessEqual(r.db.shape[1],limit); self.assertEqual(progress[-1],100); results.append(r.db.shape)
        self.assertLess(results[0][0],results[-1][0]); self.assertLess(results[0][1],results[-1][1])
        with self.assertRaises(Cancelled):analyze(a,cancel=lambda:True)
    def test_rate_and_validation(self):
        r=analyze(np.zeros((100,2),np.int16),sample_rate=44100)
        self.assertEqual(r.frequencies[-1],22050); self.assertTrue(np.isfinite(r.db).all())
        for bounds in ((1,0),(-1,1),(0,2)):
            with self.assertRaises(ValueError):analyze(np.zeros(1000),time_range=bounds)
