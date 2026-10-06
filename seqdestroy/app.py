import sys
from pathlib import Path
from dataclasses import asdict
import numpy as np
from PySide6.QtCore import Qt,QTimer,QThread,Signal,QPointF,QEvent
from PySide6.QtGui import QPainter,QColor,QPolygonF
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QDoubleSpinBox,QSpinBox,QComboBox,QPushButton,QLabel,QFileDialog,QMessageBox,QProgressDialog,QGroupBox
from PySide6.QtMultimedia import QAudioFormat,QAudioSink,QMediaDevices
from .engine import Patch,LIMITS,Voice,RATE,render,save_patch,load_patch,Cancelled

class Plot(QWidget):
    def __init__(self,spectrum=False):
        super().__init__(); self.spectrum=spectrum; self.data=np.zeros(2048); self.setMinimumSize(300,170)
    def paintEvent(self,event):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#14212b')); p.setPen(QColor('#72dcc2'))
        p.drawText(10,20,'Spectrum: 0–24 kHz, −90 to 0 dBFS' if self.spectrum else 'Oscilloscope: recent audio')
        a=self.data
        if self.spectrum:a=np.clip((20*np.log10(np.maximum(abs(np.fft.rfft(a*np.hanning(len(a))))/(len(a)/4),1e-5))+90)/90,0,1)
        else:a=(a+1)/2
        ids=np.linspace(0,len(a)-1,min(len(a),self.width())).astype(int)
        p.drawPolyline(QPolygonF([QPointF(i*(self.width()-1)/(len(ids)-1),30+(1-a[j])*(self.height()-40)) for i,j in enumerate(ids)]))

class Export(QThread):
    progress=Signal(int); result=Signal(str)
    def __init__(self,p,note,hold,path):
        super().__init__(); self.args=(p,note,hold,path); self.cancelled=False
    def run(self):
        try:
            render(*self.args,progress=self.progress.emit,cancel=lambda:self.cancelled)
            save_patch(self.args[3]+'.patch.json',self.args[0]); self.result.emit('Saved WAV and companion patch.')
        except Cancelled:self.result.emit('Export cancelled.')
        except Exception as e:self.result.emit('Export error: '+str(e))

class Window(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('SeqAndDestroy · Sample synth'); self.resize(1100,720)
        self.controls={}; self.voice=None; self.audio=None; self.worker=None; self.project=None; self.history=np.zeros(2048); self.ticks=0
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root); buttons=QHBoxLayout(); layout.addLayout(buttons)
        for name,fn in [('Open/create project',self.project_open),('Load patch',self.load),('Save patch',self.save),('Render sample',self.export)]:
            b=QPushButton(name); b.clicked.connect(fn); buttons.addWidget(b)
        self.location=QLabel('Choose a project folder to store patches and samples.'); layout.addWidget(self.location)
        row=QHBoxLayout(); layout.addLayout(row); self.note=QSpinBox(); self.note.setRange(0,127); self.note.setValue(60)
        self.hold=QDoubleSpinBox(); self.hold.setRange(.01,120); self.hold.setValue(1)
        row.addWidget(QLabel('MIDI note')); row.addWidget(self.note); row.addWidget(QLabel('Note hold (seconds)')); row.addWidget(self.hold)
        b=QPushButton('Hold to audition · F1'); b.pressed.connect(self.start); b.released.connect(self.stop); row.addWidget(b)
        columns=QHBoxLayout(); layout.addLayout(columns); forms=[]
        for title in ['Oscillators','Filter and envelopes','Modulation']:
            group=QGroupBox(title); form=QFormLayout(group); forms.append(form); columns.addWidget(group)
        for name,value in asdict(Patch()).items():
            if isinstance(value,str):
                c=QComboBox(); c.addItems(['FM','Ring'] if name=='modulation' else ['Sine','Saw','Square','Triangle']); c.setCurrentText(value)
            else:
                c=QDoubleSpinBox(); c.setDecimals(3); c.setRange(*LIMITS[name]); c.setValue(value); c.setSingleStep(100 if name in ('cutoff','filter_env') else .01 if name in ('mix','noise','attack','decay','sustain','release','resonance') else .1)
            label=name.replace('_',' ').capitalize(); c.setAccessibleName(label); self.controls[name]=c
            index=0 if name in ('wave1','wave2','detune','mix','noise') else 1 if name in ('cutoff','resonance','attack','decay','sustain','release','filter_env') else 2
            forms[index].addRow(label,c)
        plots=QHBoxLayout(); layout.addLayout(plots); self.scope=Plot(); self.spectrum=Plot(True); plots.addWidget(self.scope); plots.addWidget(self.spectrum)
        self.status=QLabel('Hold F1 to audition · Tab to navigate · Arrow keys adjust controls'); layout.addWidget(self.status)
        self.timer=QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(20)
        QApplication.instance().installEventFilter(self)
    def eventFilter(self,obj,e):
        if e.type() in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease) and e.key()==Qt.Key.Key_F1:
            if not e.isAutoRepeat():self.start() if e.type()==QEvent.Type.KeyPress else self.stop()
            return True
        if e.type()==QEvent.Type.ApplicationDeactivate:self.stop()
        return super().eventFilter(obj,e)
    def patch(self):return Patch(**{k:c.currentText() if isinstance(c,QComboBox) else c.value() for k,c in self.controls.items()})
    def start(self):
        if self.voice and self.voice.off is None:return
        if self.audio is None:
            output=QMediaDevices.defaultAudioOutput(); fmt=QAudioFormat(); fmt.setSampleRate(RATE); fmt.setChannelCount(1); fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if output.isNull() or not output.isFormatSupported(fmt):self.status.setText('No compatible audio output. WAV export remains available.'); return
            self.audio=QAudioSink(output,fmt,self); self.audio.setBufferSize(8192); self.device=self.audio.start()
            if self.device is None:self.audio=None; self.status.setText('Audio output could not start.'); return
        self.voice=Voice(self.patch(),self.note.value()); self.status.setText('Auditioning; release the key to release the note.')
    def stop(self):
        if self.voice:self.voice.release()
    def pump(self):
        if self.voice is None:return
        n=min(2048,self.audio.bytesFree()//2)
        if n<128:return
        self.voice.p=self.patch(); a=self.voice.block(n); self.device.write((a*32767).astype('<i2').tobytes()); self.history=np.concatenate((self.history,a))[-2048:]; self.ticks+=1
        if self.ticks%3==0:
            for plot in (self.scope,self.spectrum):plot.data=self.history; plot.update()
        if self.voice.finished:self.voice=None
    def project_open(self):
        path=QFileDialog.getExistingDirectory(self,'Project folder')
        if path:
            try:
                project=Path(path)
                for name in ('samples','patches'):(project/name).mkdir(exist_ok=True)
                self.project=project; self.location.setText(str(project))
            except OSError as e:QMessageBox.warning(self,'Project error',str(e))
    def load(self):
        path,_=QFileDialog.getOpenFileName(self,'Load patch',str(self.project or Path.cwd()),'Patch (*.json)')
        if not path:return
        try:
            for k,v in asdict(load_patch(path)).items():
                c=self.controls[k]
                if isinstance(c,QComboBox):c.setCurrentText(v)
                else:c.setValue(v)
        except Exception as e:QMessageBox.warning(self,'Load error',str(e))
    def save(self):
        path,_=QFileDialog.getSaveFileName(self,'Save patch',str((self.project/'patches' if self.project else Path.cwd())/'sound.json'),'Patch (*.json)')
        if path:
            try:save_patch(path,self.patch())
            except Exception as e:QMessageBox.warning(self,'Save error',str(e))
    def export(self):
        if self.worker and self.worker.isRunning():return
        if not self.project:self.project_open()
        if not self.project:return
        path,_=QFileDialog.getSaveFileName(self,'Render sample',str(self.project/'samples'/'sample.wav'),'WAV (*.wav)')
        if not path:return
        if Path(path+'.patch.json').exists() and QMessageBox.question(self,'Replace companion patch?','Replace existing patch metadata for this sample?')!=QMessageBox.StandardButton.Yes:return
        self.dialog=QProgressDialog('Rendering note and release…','Cancel',0,100,self); self.dialog.setAutoClose(False); self.dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.worker=Export(self.patch(),self.note.value(),self.hold.value(),path); self.worker.progress.connect(self.dialog.setValue); self.worker.result.connect(self.export_done)
        self.dialog.canceled.connect(lambda:setattr(self.worker,'cancelled',True)); self.worker.start(); self.dialog.show()
    def export_done(self,message):self.dialog.close(); self.status.setText(message)
    def closeEvent(self,e):
        if self.worker and self.worker.isRunning():self.worker.cancelled=True; self.worker.wait()
        if self.audio:self.audio.stop()
        e.accept()

def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); w=Window(); w.show(); sys.exit(app.exec())
if __name__=='__main__':main()
