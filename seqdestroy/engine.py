"""Deterministic, chunked synthesis. No GUI or audio device required."""
from dataclasses import dataclass, asdict
import json
import math
import os
from pathlib import Path
import tempfile
import wave
import numpy as np

RATE = 48000

@dataclass
class Patch:
    wave1: str = 'Saw'
    wave2: str = 'Sine'
    detune: float = 7.0
    mix: float = 0.35
    noise: float = 0.03
    pan1: float = 0.0
    pan2: float = 0.0
    noise_pan: float = 0.0
    cutoff: float = 3500.0
    resonance: float = 0.15
    attack: float = 0.01
    decay: float = 0.2
    sustain: float = 0.65
    release: float = 0.4
    filter_env: float = 1200.0
    lfo_rate: float = 2.0
    lfo_depth: float = 0.0
    drive: float = 1.0
    modulation: str = 'FM'
    mod_amount: float = 0.0

LIMITS = {
 'pan1':(-1,1), 'pan2':(-1,1), 'noise_pan':(-1,1),
 'detune':(-100,100), 'mix':(0,1), 'noise':(0,1), 'cutoff':(40,12000),
 'resonance':(0,0.9), 'attack':(0.001,3), 'decay':(0.001,3),
 'sustain':(0,1), 'release':(0.01,5), 'filter_env':(0,10000),
 'lfo_rate':(0.1,30), 'lfo_depth':(0,24), 'drive':(1,8), 'mod_amount':(0,5)}

def validate(p):
    for name,(lo,hi) in LIMITS.items():
        v=getattr(p,name)
        if not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
            raise ValueError(f'Invalid {name}: expected {lo}–{hi}')
    if p.wave1 not in ('Sine','Saw','Square','Triangle') or p.wave2 not in ('Sine','Saw','Square','Triangle'):
        raise ValueError('Unknown oscillator waveform')
    if p.modulation not in ('FM','Ring'): raise ValueError('Unknown modulation mode')
    return p

def save_patch(path,p):
    validate(p)
    Path(path).write_text(json.dumps({'version':1,'patch':asdict(p)},indent=2))

def load_patch(path):
    data=json.loads(Path(path).read_text())
    if data.get('version')!=1: raise ValueError('Unsupported patch version')
    return validate(Patch(**data['patch']))

def osc(phase,kind,step):
    t=phase%1
    if kind=='Sine': return math.sin(2*math.pi*t)
    if kind=='Triangle': return 1-4*abs(t-0.5)
    def blep(x):
        if x<step:
            x/=step
            return x+x-x*x-1
        if x>1-step:
            x=(x-1)/step
            return x*x+x+x+1
        return 0
    if kind=='Saw': return 2*t-1-blep(t)
    return (1 if t<0.5 else -1)+blep(t)-blep((t+0.5)%1)

class Voice:
    def __init__(self,p,note=60,rate=RATE):
        self.p=validate(p); self.rate=rate; self.freq=440*2**((note-69)/12)
        self.i=0; self.phase1=0.; self.phase2=0.; self.low=[0.,0.]; self.band=[0.,0.]
        self.off=None; self.off_level=0.; self.rng=np.random.default_rng(42)
    def env(self,t):
        p=self.p
        if t<p.attack: return t/p.attack
        return p.sustain+(1-p.sustain)*max(0,1-(t-p.attack)/p.decay)
    def release(self):
        if self.off is None:
            self.off=self.i; self.off_level=self.env(self.i/self.rate)
    @property
    def finished(self):
        return self.off is not None and self.i-self.off>=round(self.p.release*self.rate)
    def block(self,n):
        p=self.p; out=np.empty((n,2),dtype=np.float32); noise=self.rng.uniform(-1,1,n)
        gains=[(math.cos((pan+1)*math.pi/4), math.sin((pan+1)*math.pi/4)) for pan in (p.pan1,p.pan2,p.noise_pan)]
        for j in range(n):
            t=self.i/self.rate; e=self.env(t)
            if self.off is not None: e=self.off_level*max(0,1-(self.i-self.off)/(p.release*self.rate))
            f=self.freq*2**(p.lfo_depth*math.sin(2*math.pi*p.lfo_rate*t)/12)
            d1=min(f/self.rate,0.4); d2=min(f*2**(p.detune/1200)/self.rate,0.4)
            b=osc(self.phase2,p.wave2,d2)
            a=osc(self.phase1+(p.mod_amount*b/(2*math.pi) if p.modulation=='FM' else 0),p.wave1,d1)
            if p.modulation=='Ring': a*=1-min(p.mod_amount,1)+min(p.mod_amount,1)*b
            g=math.tan(math.pi*min(16000,p.cutoff+p.filter_env*e)/self.rate)
            k=2-1.9*p.resonance
            for ch in range(2):
                x=((1-p.mix)*a*gains[0][ch]+p.mix*b*gains[1][ch]+p.noise*noise[j]*gains[2][ch])/(1+p.noise)
                v1=(self.band[ch]+g*(x-self.low[ch]))/(1+g*(g+k)); v2=self.low[ch]+g*v1
                self.band[ch]=2*v1-self.band[ch]; self.low[ch]=2*v2-self.low[ch]
                out[j,ch]=0.75*math.tanh(v2*p.drive)*e
            self.phase1=(self.phase1+d1)%1; self.phase2=(self.phase2+d2)%1; self.i+=1
        return out

class Cancelled(Exception): pass

def render(p,note,hold,path,progress=lambda x:None,cancel=lambda:False):
    if not 0<=note<=127 or not math.isfinite(hold) or not 0.01<=hold<=120:
        raise ValueError('Note must be 0–127 and hold duration 0.01–120 seconds')
    v=Voice(p,note); held=round(hold*RATE); total=held+round(p.release*RATE)
    path=Path(path); fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.wav'); os.close(fd)
    try:
        with wave.open(tmp,'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
            while v.i<total:
                if cancel(): raise Cancelled()
                if v.i>=held: v.release()
                n=min(2048,total-v.i,held-v.i if v.i<held else total-v.i)
                a=v.block(n); w.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())
                progress(int(100*v.i/total))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
