"""Standalone analysis panel reusable for samples, tracks or mixed sequences."""
import numpy as np
from PySide6.QtCore import Qt,QThread,Signal,QPointF,QRectF,QTimer
from PySide6.QtGui import QPainter,QColor,QImage
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QDoubleSpinBox,QLabel,QPushButton,QProgressBar
from .analysis import analyze
from .engine import RATE,Cancelled

class AnalysisWorker(QThread):
    ready=Signal(object); progress=Signal(int); error=Signal(str)
    def __init__(self,audio,options):
        super().__init__(); self.audio=audio; self.options=options; self.cancelled=False
    def run(self):
        try:
            result=analyze(self.audio,**self.options,cancel=lambda:self.cancelled,progress=self.progress.emit)
            if not self.cancelled:self.ready.emit(result)
        except Cancelled:pass
        except Exception as e:self.error.emit(str(e))

class Canvas(QWidget):
    def __init__(self):
        super().__init__(); self.setMinimumSize(420,210); self.image=None; self.duration=0; self.position=None; self.pending_data=None
        self.bounds=(0,1,40,RATE/2)
    def set_data(self,db,duration,bounds=None):
        self.duration=duration
        if bounds is not None:self.bounds=bounds
        if not self.isVisible():self.pending_data=(db,duration,bounds); return
        self.pending_data=None
        level=np.clip((db[::-1]+90)/90,0,1)
        rgb=np.stack((255*level**.6,220*level**1.5,100*level**3),axis=-1).astype(np.uint8)
        h,w,_=rgb.shape; self.image=QImage(rgb.data,w,h,3*w,QImage.Format.Format_RGB888).copy(); self.update()
    def showEvent(self,e):
        if self.pending_data is not None:self.set_data(*self.pending_data)
        super().showEvent(e)
    def paintEvent(self,e):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#14212b')); p.setPen(QColor('#c2ddd8'))
        p.drawText(10,18,'Stereo power · logarithmic Hz · dark −90 / bright 0 dBFS')
        area=QRectF(60,30,self.width()-80,self.height()-60)
        begin,end,low,high=self.bounds
        if self.image:p.drawImage(area,self.image)
        else:p.drawText(65,65,'Render or use Timed preview to supply audio.')
        for hz in np.geomspace(low,high,5):
            y=area.bottom()-np.log(hz/low)/np.log(high/low)*area.height()
            p.drawText(2,int(y),f'{hz:.0f}')
        p.drawText(60,self.height()-8,f'{begin:.3f} s'); p.drawText(self.width()-110,self.height()-8,f'{end:.3f} s')
        if self.position is not None and begin<=self.position<=end:
            x=area.left()+(self.position-begin)/(end-begin)*area.width(); p.setPen(QColor('white')); p.drawLine(QPointF(x,area.top()),QPointF(x,area.bottom()))

class Spectrogram(QWidget):
    def __init__(self):
        super().__init__(); self.audio=None; self.sample_rate=RATE; self.worker=None; self.dirty=False; self.closing=False; self.generation=0
        layout=QVBoxLayout(self); options=QHBoxLayout(); layout.addLayout(options)
        self.quality=QComboBox(); self.quality.addItems(['Fast','Balanced','Detailed']); self.quality.setCurrentText('Balanced')
        self.mode=QComboBox(); self.mode.addItems(['Transient','Tonal']); self.mode.setCurrentText('Tonal')
        for label,control in [('Quality',self.quality),('Mode',self.mode)]:
            options.addWidget(QLabel(label)); options.addWidget(control); control.setAccessibleName(label)
        self.cancel_button=QPushButton('Cancel analysis'); options.addWidget(self.cancel_button); self.cancel_button.clicked.connect(self.cancel)
        ranges=QHBoxLayout(); layout.addLayout(ranges)
        self.begin=self.spin(ranges,'Start (s)',0,120,0,3); self.end=self.spin(ranges,'End (s)',0,120,1,3)
        self.low=self.spin(ranges,'Low (Hz)',1,24000,40,1); self.high=self.spin(ranges,'High (Hz)',1,24000,24000,1)
        apply=QPushButton('Analyze / zoom'); apply.clicked.connect(self.request); ranges.addWidget(apply)
        reset=QPushButton('Full range'); reset.clicked.connect(self.reset_range); ranges.addWidget(reset)
        self.canvas=Canvas(); layout.addWidget(self.canvas)
        self.progress=QProgressBar(); layout.addWidget(self.progress)
        self.status=QLabel('Render or preview a sample. Select a time/frequency range to inspect it.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.quality.currentTextChanged.connect(self.request); self.mode.currentTextChanged.connect(self.request)
    @staticmethod
    def spin(layout,label,lo,hi,value,decimals):
        layout.addWidget(QLabel(label)); control=QDoubleSpinBox(); control.setDecimals(decimals); control.setRange(lo,hi); control.setValue(value); control.setAccessibleName(label); layout.addWidget(control); return control
    @property
    def image(self):return self.canvas.image
    @property
    def pending_data(self):return self.canvas.pending_data
    @property
    def duration(self):return self.canvas.duration
    @property
    def position(self):return self.canvas.position
    @position.setter
    def position(self,value):self.canvas.position=value; self.canvas.update() if self.canvas.isVisible() else None
    def set_data(self,db,duration):self.canvas.set_data(db,duration,(0,duration,40,self.sample_rate/2))
    def set_audio(self,audio,sample_rate=RATE):
        self.audio=audio; self.sample_rate=sample_rate; self.canvas.duration=len(audio)/sample_rate
        self.canvas.image=None; self.canvas.pending_data=None
        self.begin.setMaximum(self.duration); self.end.setMaximum(self.duration); self.low.setMaximum(sample_rate/2); self.high.setMaximum(sample_rate/2)
        self.reset_range()
    def reset_range(self):
        self.begin.setValue(0); self.end.setValue(self.duration or 1); self.low.setValue(40); self.high.setValue(self.sample_rate/2); self.request()
    def request(self,*args):
        if self.audio is None:return
        self.generation+=1; self.dirty=True
        if self.worker is not None:self.worker.cancelled=True; return
        self.launch()
    def launch(self):
        if self.closing or not self.dirty:return
        self.dirty=False; token=self.generation
        options=dict(sample_rate=self.sample_rate,quality=self.quality.currentText(),mode=self.mode.currentText(),time_range=(self.begin.value(),self.end.value()),frequency_range=(self.low.value(),self.high.value()))
        # End controls round to milliseconds; keep the exact endpoint inside the audio.
        options['time_range']=(options['time_range'][0],min(options['time_range'][1],self.duration))
        worker=AnalysisWorker(self.audio,options); self.worker=worker
        self.progress.setValue(0); self.status.setText('Analyzing… previous image remains until the new analysis is ready.')
        worker.progress.connect(lambda n:self.progress.setValue(n) if token==self.generation else None)
        worker.ready.connect(lambda result:self.accept(result) if token==self.generation and not self.closing else None)
        worker.error.connect(lambda message:self.status.setText(message) if token==self.generation else None)
        worker.finished.connect(self.finished); worker.start()
    def accept(self,result):
        self.canvas.set_data(result.db,self.duration,(result.times[0],result.times[-1],result.frequencies[0],result.frequencies[-1]))
        step=(result.times[-1]-result.times[0])/max(1,len(result.times)-1)
        self.status.setText(f'{result.quality} / {result.mode} · {result.window_size/result.sample_rate*1000:.1f} ms window · {result.sample_rate/result.window_size:.2f} Hz FFT spacing · {step*1000:.2f} ms time steps · {result.db.shape[1]} × {result.db.shape[0]} cells')
    def finished(self):
        worker=self.worker; self.worker=None
        if worker:worker.deleteLater()
        if self.dirty and not self.closing:QTimer.singleShot(0,self.launch)
    def cancel(self):
        self.generation+=1; self.dirty=False
        if self.worker:self.worker.cancelled=True
        self.status.setText('Analysis cancelled; previous completed image retained.')
    def shutdown(self):
        self.closing=True; self.cancel()
        if self.worker:self.worker.wait()
