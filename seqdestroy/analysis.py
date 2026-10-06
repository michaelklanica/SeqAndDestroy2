"""Bounded-memory stereo power spectrogram; no cancellation from phase averaging."""
import numpy as np
from .engine import RATE, Cancelled

def spectrogram(audio, cancel=lambda:False, max_columns=800):
    size=2048
    frequencies=np.geomspace(40,RATE/2,256)
    starts=np.linspace(0,max(0,len(audio)-size),min(max_columns,max(1,len(audio)//512)),dtype=int)
    window=np.hanning(size)
    bins=np.fft.rfftfreq(size,1/RATE)
    result=np.empty((len(frequencies),len(starts)),dtype=np.float32)
    for i,start in enumerate(starts):
        if cancel():raise Cancelled()
        block=audio[start:start+size].astype(np.float32)/32768
        if len(block)<size:block=np.pad(block,((0,size-len(block)),(0,0)))
        power=np.mean(abs(np.fft.rfft(block*window[:,None],axis=0)/(window.sum()/2))**2,axis=1)
        result[:,i]=10*np.log10(np.maximum(np.interp(frequencies,bins,power),1e-10))
    return frequencies,result
