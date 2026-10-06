import json
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np
from seqdestroy.engine import Patch,Voice,RATE,render,load_patch
from seqdestroy.analysis import spectrogram

class StereoTests(unittest.TestCase):
    def test_center_and_hard_pan(self):
        a=Voice(Patch()).block(4096)
        np.testing.assert_array_equal(a[:,0],a[:,1])
        for source in ('osc1','osc2','noise'):
            for side in (-1,1):
                p=Patch(noise=0,mix=0,pan1=side,pan2=side,noise_pan=side)
                if source=='osc2':p.mix=1
                if source=='noise':p.noise=1; p.mix=0; p.pan1=-side
                a=Voice(p).block(4096)
                if source!='noise':self.assertLess(abs(a[:,1 if side==-1 else 0]).max(),1e-10)
                self.assertGreater(abs(a[:,0 if side==-1 else 1]).max(),.001)
    def test_legacy_patch(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'old.json'; path.write_text(json.dumps({'version':1,'patch':{'mix':.8}}))
            p=load_patch(path); self.assertEqual(p.pan1,0); self.assertEqual(p.pan2,0); self.assertEqual(p.mix,.8)
    def test_hold_and_release_export(self):
        with tempfile.TemporaryDirectory() as d:
            p=Patch(release=.05)
            for hold in (.1,.3):
                path=Path(d)/'a.wav'; render(p,60,hold,path)
                with wave.open(str(path)) as w:
                    self.assertEqual(w.getnframes(),round((hold+.05)*RATE))
                    a=np.frombuffer(w.readframes(w.getnframes()),'<i2').reshape(-1,2)
                self.assertLess(abs(a[-1]).max(),10)
    def test_spectrogram_frequency_stereo_and_bounds(self):
        t=np.arange(RATE)/RATE; a=(np.sin(2*np.pi*1000*t)*20000).astype(np.int16)
        f,db=spectrogram(np.column_stack((a,-a)),max_columns=60)
        self.assertLessEqual(db.shape[1],60); self.assertTrue(np.isfinite(db).all())
        self.assertAlmostEqual(f[np.argmax(db.mean(axis=1))],1000,delta=50)
        _,silent=spectrogram(np.zeros((100,2),np.int16)); self.assertTrue((silent<=-90).all())
