"""Shared chart scales and live audio plots."""
import numpy as np
from PySide6.QtCore import QPointF,QRectF
from PySide6.QtGui import QPainter,QColor,QPolygonF
from PySide6.QtWidgets import QWidget
from .engine import RATE

def number(value):
    return f'{value/1000:g}k' if abs(value)>=1000 else f'{value:.4g}'

def axes(p,area,xlimits,ylimits,xlabel,ylabel,log_y=False):
    nx=max(2,min(8,int(area.width()/95)+1)); ny=max(2,min(6,int(area.height()/45)+1))
    xs=np.linspace(*xlimits,nx)
    ys=np.geomspace(*ylimits,ny) if log_y else np.linspace(*ylimits,ny)
    for i,x in enumerate(xs):
        px=area.left()+i/(nx-1)*area.width()
        p.setPen(QColor('#38505b')); p.drawLine(QPointF(px,area.top()),QPointF(px,area.bottom()))
        p.setPen(QColor('#c2ddd8')); p.drawText(QRectF(px-36,area.bottom()+4,72,18),0x84,number(x))
    for i,y in enumerate(ys):
        py=area.bottom()-i/(ny-1)*area.height()
        p.setPen(QColor('#38505b')); p.drawLine(QPointF(area.left(),py),QPointF(area.right(),py))
        p.setPen(QColor('#c2ddd8')); p.drawText(QRectF(0,py-9,area.left()-7,18),0x82,number(y))
    p.drawText(QRectF(area.left(),area.bottom()+24,area.width(),18),0x84,xlabel)
    p.drawText(5,18,ylabel)

class Plot(QWidget):
    def __init__(self,spectrum=False):
        super().__init__(); self.spectrum=spectrum; self.data=np.zeros(2048); self.cursor=None
        self.setMinimumSize(360,230); self.setMouseTracking(True)
    def area(self):return QRectF(60,35,self.width()-80,self.height()-105)
    def mouseMoveEvent(self,e):self.cursor=e.position(); self.update()
    def leaveEvent(self,e):self.cursor=None; self.update()
    def values(self):
        if self.spectrum:
            return 20*np.log10(np.maximum(abs(np.fft.rfft(self.data*np.hanning(len(self.data))))/(len(self.data)/4),1e-5))
        return self.data
    def paintEvent(self,e):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#14212b')); area=self.area(); a=self.values()
        xmax=RATE/2 if self.spectrum else (len(a)-1)/RATE*1000
        lo,hi=(-90,0) if self.spectrum else (-1,1)
        axes(p,area,(0,xmax),(lo,hi),'Frequency (Hz)' if self.spectrum else 'Elapsed time in recent buffer (ms)','Level (dBFS)' if self.spectrum else 'Amplitude')
        if not self.spectrum:
            p.setPen(QColor('#8aa1ab')); p.drawLine(QPointF(area.left(),area.center().y()),QPointF(area.right(),area.center().y()))
        ids=np.linspace(0,len(a)-1,min(len(a),max(2,int(area.width())))).astype(int)
        p.setPen(QColor('#72dcc2')); p.drawPolyline(QPolygonF([QPointF(area.left()+i*area.width()/(len(ids)-1),area.bottom()-(np.clip(a[j],lo,hi)-lo)/(hi-lo)*area.height()) for i,j in enumerate(ids)]))
        if self.cursor is not None and area.contains(self.cursor):
            fraction=(self.cursor.x()-area.left())/area.width(); index=round(fraction*(len(a)-1))
            x=index*xmax/(len(a)-1)
            text=f'{x:.2f} Hz · {a[index]:.2f} dBFS' if self.spectrum else f'{x:.3f} ms · amplitude {a[index]:.4f}'
            p.drawText(60,self.height()-8,text)
