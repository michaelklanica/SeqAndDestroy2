"""Standalone analysis panel reusable for samples, tracks or mixed sequences."""
import numpy as np
from PySide6.QtCore import Qt,QThread,Signal,QPointF,QRectF,QTimer
from PySide6.QtGui import QPainter,QColor,QImage,QLinearGradient
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QDoubleSpinBox,QLabel,QPushButton,QProgressBar
from .charts import axes
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
    range_requested=Signal(object)
    reset_requested=Signal()
    def __init__(self):
        super().__init__(); self.setMinimumSize(420,210); self.image=None; self.duration=0; self.position=None; self.pending_data=None
        self.bounds=(0,1,40,RATE/2); self.limits=(0,1,1,RATE/2); self.gesture_bounds=None
        self.cursor=None; self.drag_start=None; self.drag_end=None; self.drag_button=None; self.db=None
        self.setMouseTracking(True)
        self.setToolTip('Wheel: zoom at pointer · left drag: select region · right drag: pan · double-click: full range')
    def set_data(self,db,duration,bounds=None):
        self.duration=duration; self.db=db; self.gesture_bounds=None
        if bounds is not None:self.bounds=bounds
        if not self.isVisible():self.pending_data=(db,duration,bounds); return
        self.pending_data=None
        level=np.clip((db[::-1]+90)/90,0,1)
        rgb=np.stack((255*level**.6,220*level**1.5,100*level**3),axis=-1).astype(np.uint8)
        h,w,_=rgb.shape; self.image=QImage(rgb.data,w,h,3*w,QImage.Format.Format_RGB888).copy(); self.update()
    def showEvent(self,e):
        if self.pending_data is not None:self.set_data(*self.pending_data)
        super().showEvent(e)
    def area(self):return QRectF(65,35,self.width()-155,self.height()-105)
    def coords(self,point,bounds=None):
        area=self.area(); begin,end,low,high=bounds or self.bounds
        x=np.clip((point.x()-area.left())/area.width(),0,1)
        y=np.clip((area.bottom()-point.y())/area.height(),0,1)
        return begin+x*(end-begin), np.exp(np.log(low)+y*np.log(high/low))
    def emit_range(self,bounds):
        begin,end,low,high=bounds; tmin,tmax,fmin,fmax=self.limits
        def fit(a,b,lo,hi,minimum):
            width=min(hi-lo,max(minimum,b-a)); a=min(max(a,lo),hi-width); return a,a+width
        begin,end=fit(begin,end,tmin,tmax,.001)
        low,high=np.exp(fit(np.log(low),np.log(high),np.log(fmin),np.log(fmax),.001))
        self.gesture_bounds=(float(begin),float(end),float(low),float(high))
        self.range_requested.emit(self.gesture_bounds)
    def wheelEvent(self,e):
        if self.image is None or not self.area().contains(e.position()):e.ignore(); return
        delta=e.angleDelta().y() or e.pixelDelta().y()
        if not delta:return
        bounds=self.gesture_bounds or self.bounds; t,f=self.coords(e.position(),bounds)
        begin,end,low,high=bounds; factor=1.25**(-np.clip(delta/120,-4,4))
        self.emit_range((t+(begin-t)*factor,t+(end-t)*factor,
                         np.exp(np.log(f)+(np.log(low)-np.log(f))*factor),
                         np.exp(np.log(f)+(np.log(high)-np.log(f))*factor)))
        e.accept()
    def mousePressEvent(self,e):
        if self.image is not None and self.area().contains(e.position()) and e.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            self.drag_start=e.position(); self.drag_end=e.position(); self.drag_button=e.button()
    def mouseMoveEvent(self,e):
        self.cursor=e.position()
        if self.drag_start is not None:self.drag_end=e.position()
        self.update()
    def mouseReleaseEvent(self,e):
        if self.drag_start is None:return
        start=self.drag_start; end=e.position(); button=self.drag_button
        self.drag_start=None; self.drag_end=None; self.update()
        if abs(start.x()-end.x())<4 and abs(start.y()-end.y())<4:return
        t0,f0=self.coords(start); t1,f1=self.coords(end)
        if button==Qt.MouseButton.LeftButton:
            if abs(start.x()-end.x())<4 or abs(start.y()-end.y())<4:return
            self.emit_range((min(t0,t1),max(t0,t1),min(f0,f1),max(f0,f1)))
        else:
            begin,finish,low,high=self.bounds
            self.emit_range((begin+t0-t1,finish+t0-t1,low*f0/f1,high*f0/f1))
    def mouseDoubleClickEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:self.drag_start=None; self.drag_end=None; self.reset_requested.emit()
    def leaveEvent(self,e):self.cursor=None; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#14212b')); area=self.area()
        begin,end,low,high=self.bounds
        if self.image:p.drawImage(area,self.image)
        else:
            p.setPen(QColor('#c2ddd8')); p.drawText(70,65,'Render or use Timed preview to supply audio.')
        axes(p,area,(begin,end),(low,high),'Time (s)','Frequency (Hz)',True)
        bar=QRectF(area.right()+18,area.top(),14,area.height()); gradient=QLinearGradient(bar.bottomLeft(),bar.topLeft())
        for value in np.linspace(0,1,20):gradient.setColorAt(float(value),QColor(int(255*value**.6),int(220*value**1.5),int(100*value**3)))
        p.fillRect(bar,gradient); p.setPen(QColor('#c2ddd8'))
        p.drawText(int(bar.left()),20,'dBFS')
        for db in (-90,-60,-30,0):p.drawText(int(bar.right()+4),int(bar.bottom()-(db+90)/90*bar.height()+4),str(db))
        if self.position is not None and begin<=self.position<=end:
            x=area.left()+(self.position-begin)/(end-begin)*area.width(); p.setPen(QColor('white')); p.drawLine(QPointF(x,area.top()),QPointF(x,area.bottom()))
        if self.drag_start is not None and self.drag_button==Qt.MouseButton.LeftButton:
            selection=QRectF(self.drag_start,self.drag_end).normalized().intersected(area)
            p.fillRect(selection,QColor(100,210,220,65)); p.setPen(QColor('white')); p.drawRect(selection)
        if self.cursor is not None and area.contains(self.cursor) and self.db is not None:
            t,hz=self.coords(self.cursor)
            row=int(np.clip(round(np.log(hz/low)/np.log(high/low)*(self.db.shape[0]-1)),0,self.db.shape[0]-1))
            col=int(np.clip(round((t-begin)/(end-begin)*(self.db.shape[1]-1)),0,self.db.shape[1]-1))
            p.setPen(QColor('#c2ddd8')); p.drawText(65,self.height()-8,f'{t:.4f} s · {hz:.2f} Hz · {self.db[row,col]:.2f} dBFS (nearest cell)')

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
        self.begin=self.spin(ranges,'Start (s)',0,120,0,6); self.end=self.spin(ranges,'End (s)',0,120,1,6)
        self.low=self.spin(ranges,'Low (Hz)',1,24000,40,4); self.high=self.spin(ranges,'High (Hz)',1,24000,24000,4)
        apply=QPushButton('Analyze / zoom'); apply.clicked.connect(self.request); ranges.addWidget(apply)
        reset=QPushButton('Full range'); reset.clicked.connect(self.reset_range); ranges.addWidget(reset)
        self.canvas=Canvas(); layout.addWidget(self.canvas,1)
        self.mouse_timer=QTimer(self); self.mouse_timer.setSingleShot(True); self.mouse_timer.setInterval(120); self.mouse_timer.timeout.connect(self.request)
        self.canvas.range_requested.connect(self.mouse_range); self.canvas.reset_requested.connect(self.reset_range)
        hint=QLabel('Wheel: zoom · Left drag: select · Right drag: pan · Double-click: full range'); layout.addWidget(hint)
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
        self.canvas.limits=(0,self.duration,1,sample_rate/2)
        self.canvas.image=None; self.canvas.pending_data=None
        self.begin.setMaximum(self.duration); self.end.setMaximum(self.duration); self.low.setMaximum(sample_rate/2); self.high.setMaximum(sample_rate/2)
        self.reset_range()
    def mouse_range(self,bounds):
        if self.audio is None:return
        for control,value in zip((self.begin,self.end,self.low,self.high),bounds):control.setValue(value)
        self.generation+=1
        if self.worker:self.worker.cancelled=True
        self.dirty=False
        self.mouse_timer.start()
    def reset_range(self):
        self.mouse_timer.stop()
        self.canvas.gesture_bounds=None
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
        self.mouse_timer.stop()
        self.generation+=1; self.dirty=False
        if self.worker:self.worker.cancelled=True
        self.status.setText('Analysis cancelled; previous completed image retained.')
    def shutdown(self):
        self.closing=True; self.cancel()
        if self.worker:self.worker.wait()
