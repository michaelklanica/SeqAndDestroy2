import json
import tempfile
import unittest
import wave
from pathlib import Path
from dataclasses import replace
import numpy as np
from seqdestroy.engine import Patch,Voice,RATE,load_patch,save_patch,render,validate

class FilterEnvelopeTests(unittest.TestCase):
    def test_independent_envelope_stages(self):
        v=Voice(Patch(attack=.01,decay=.02,sustain=.8,filter_attack=.2,filter_decay=.4,filter_sustain=.25))
        self.assertAlmostEqual(v.filter_envelope(.1),.5)
        self.assertAlmostEqual(v.filter_envelope(.2),1)
        self.assertAlmostEqual(v.filter_envelope(.4),.625)
        self.assertAlmostEqual(v.filter_envelope(1),.25)
        self.assertAlmostEqual(v.env(1),.8)
    def test_filter_changes_audio_but_zero_depth_does_not(self):
        p=Patch(cutoff=200,filter_env=8000,noise=0,attack=.001,decay=.001,sustain=1,filter_attack=.001,filter_decay=.001,filter_sustain=1)
        other=replace(p,filter_attack=2,filter_sustain=0)
        a=Voice(p).block(12000); b=Voice(other).block(12000)
        self.assertGreater(np.mean((a-b)**2),.001)
        np.testing.assert_array_equal(Voice(replace(p,filter_env=0)).block(1000),Voice(replace(other,filter_env=0)).block(1000))
    def test_early_release_uses_each_current_level(self):
        v=Voice(Patch(attack=.1,filter_attack=.2,release=.1,filter_release=.5))
        v.block(2400); v.release()
        self.assertAlmostEqual(v.off_level,.5); self.assertAlmostEqual(v.filter_off_level,.25)
        a=v.block(4801); self.assertTrue(v.finished); self.assertTrue((a[-1]==0).all())
    def test_filter_release_changes_tail_not_file_duration(self):
        p=Patch(cutoff=200,filter_env=8000,attack=.001,decay=.001,sustain=1,release=.2,filter_attack=.001,filter_decay=.001,filter_sustain=1)
        voices=[Voice(replace(p,filter_release=r)) for r in (.01,1)]
        for v in voices:v.block(4800); v.release()
        self.assertGreater(np.mean((voices[0].block(4800)-voices[1].block(4800))**2),.001)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.wav'; render(replace(p,filter_release=5),60,.1,path)
            with wave.open(str(path)) as f:self.assertEqual(f.getnframes(),14400)
    def test_old_patch_migration_and_new_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'p.json'; path.write_text(json.dumps({'version':1,'patch':{'attack':.3,'decay':.7,'sustain':.2,'release':1.2}}))
            p=load_patch(path)
            for key in ('attack','decay','sustain','release'):self.assertEqual(getattr(p,key),getattr(p,'filter_'+key))
            p.filter_decay=.123; save_patch(path,p); self.assertEqual(json.loads(path.read_text())['version'],2); self.assertEqual(load_patch(path),p)
    def test_reject_invalid_filter_values(self):
        for key,value in [('filter_attack',0),('filter_decay',float('nan')),('filter_sustain',2),('filter_release',-1)]:
            with self.assertRaises(ValueError):validate(replace(Patch(),**{key:value}))
