import tempfile, unittest, wave
from pathlib import Path
import numpy as np
from seqdestroy.engine import Patch,Voice,RATE,render,save_patch,load_patch,Cancelled
class EngineTests(unittest.TestCase):
    def test_pitch_release(self):
        v=Voice(Patch(wave1='Sine',mix=0,noise=0,filter_env=0,cutoff=12000,attack=.001,decay=.001,sustain=1,release=.05),69)
        a=v.block(RATE)[4800:,0]; freq=np.argmax(abs(np.fft.rfft(a)))*RATE/len(a)
        self.assertAlmostEqual(freq,440,delta=2); v.release(); a=v.block(3000); self.assertTrue(v.finished); self.assertTrue((a[-1]==0).all())
    def test_render_patch(self):
        with tempfile.TemporaryDirectory() as d:
            p=Patch(release=.1); path=Path(d)/'a.wav'; progress=[]; render(p,60,.1,path,progress.append)
            with wave.open(str(path)) as w:
                self.assertEqual(w.getnchannels(),2); self.assertEqual(w.getnframes(),9600); self.assertEqual(w.getframerate(),RATE); self.assertGreater(abs(np.frombuffer(w.readframes(9600),dtype='<i2')).max(),100)
            self.assertEqual(progress[-1],100); save_patch(Path(d)/'p.json',p); self.assertEqual(load_patch(Path(d)/'p.json'),p)
    def test_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.wav'; path.write_bytes(b'original')
            with self.assertRaises(Cancelled):render(Patch(),60,1,path,cancel=lambda:True)
            self.assertEqual(path.read_bytes(),b'original'); self.assertEqual(len(list(Path(d).iterdir())),1)
    def test_stability(self):
        for mode in ('FM','Ring'):
            a=Voice(Patch(resonance=.9,cutoff=12000,filter_env=10000,modulation=mode,mod_amount=5,drive=8),100).block(10000)
            self.assertTrue(np.isfinite(a).all()); self.assertLessEqual(abs(a).max(),.75)
