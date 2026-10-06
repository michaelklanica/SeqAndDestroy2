"""Reusable PCM analysis, independent of synthesizer and UI.

Accepts mono/multichannel int16 PCM or normalized floating-point audio.
Windows are centered on the reported times; boundary frames are zero-padded.
"""
from dataclasses import dataclass
import numpy as np
from .engine import RATE, Cancelled

QUALITIES = {'Fast': (512, 256, 2), 'Balanced': (1600, 512, 4), 'Detailed': (4096, 1024, 8)}
WINDOWS = {'Transient': 512, 'Tonal': 8192}

@dataclass
class Analysis:
    frequencies: np.ndarray
    times: np.ndarray
    db: np.ndarray
    window_size: int
    sample_rate: int
    quality: str
    mode: str

def analyze(audio, sample_rate=RATE, quality='Balanced', mode='Tonal',
            time_range=None, frequency_range=None, cancel=lambda:False, progress=lambda n:None,
            max_columns=None):
    audio=np.asarray(audio)
    if audio.ndim==1:audio=audio[:,None]
    if audio.ndim!=2 or not len(audio) or not audio.shape[1]:raise ValueError('Audio must contain frames and channels')
    if sample_rate<=0:raise ValueError('Sample rate must be positive')
    if quality not in QUALITIES or mode not in WINDOWS:raise ValueError('Unknown quality or mode')
    columns,rows,overlap=QUALITIES[quality]
    if max_columns is not None:columns=min(columns,max_columns)
    if columns<1:raise ValueError('Column limit must be positive')
    size=WINDOWS[mode]
    # Detailed Tonal resolves closer partials; Transient keeps a short window.
    if mode=='Tonal':size={'Fast':4096,'Balanced':8192,'Detailed':16384}[quality]
    duration=len(audio)/sample_rate
    begin,end=time_range or (0,duration)
    low,high=frequency_range or (40,sample_rate/2)
    if not 0<=begin<end<=duration:raise ValueError('Invalid time range')
    if not 0<low<high<=sample_rate/2:raise ValueError('Invalid frequency range')
    count=min(columns,max(2,int(np.ceil((end-begin)*sample_rate/(size/overlap)))+1))
    times=np.linspace(begin,end,count)
    frequencies=np.geomspace(low,high,rows)
    result=np.empty((rows,count),np.float32)
    window=np.hanning(size); bins=np.fft.rfftfreq(size,1/sample_rate)
    scale=32768 if audio.dtype==np.int16 else 1
    for i,t in enumerate(times):
        if cancel():raise Cancelled()
        center=round(t*sample_rate); start=center-size//2; stop=start+size
        left=max(0,start); right=min(len(audio),stop)
        block=np.zeros((size,audio.shape[1]),np.float32)
        if right>left:block[left-start:right-start]=audio[left:right]/scale
        power=np.mean(abs(np.fft.rfft(block*window[:,None],axis=0)/(window.sum()/2))**2,axis=1)
        result[:,i]=10*np.log10(np.maximum(np.interp(frequencies,bins,power),1e-10))
        progress(round(100*(i+1)/count))
    return Analysis(frequencies,times,result,size,sample_rate,quality,mode)

def spectrogram(audio,cancel=lambda:False,max_columns=800):
    result=analyze(audio,cancel=cancel,max_columns=max_columns)
    return result.frequencies,result.db
