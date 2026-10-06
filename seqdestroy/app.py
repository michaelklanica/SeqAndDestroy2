import sys
import tempfile
import wave
from pathlib import Path
from dataclasses import asdict
import numpy as np
from PySide6.QtCore import Qt,QTimer,QThread,Signal,QPointF,QEvent,QBuffer,QByteArray,QIODevice,QRectF,QSettings
from PySide6.QtGui import QPainter,QColor,QPolygonF,QImage
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QDoubleSpinBox,QSpinBox,QComboBox,QPushButton,QLabel,QFileDialog,QMessageBox,QProgressDialog,QGroupBox
from PySide6.QtMultimedia import QAudioFormat,QAudioSink,QMediaDevices
from .charts import Plot
from .windows import VisualizationWindow
from .spectrogram import Spectrogram
from .engine import Patch,LIMITS,Voice,RATE,render,save_patch,load_patch,Cancelled

class Export(QThread):
    progress=Signal(int); result=Signal(str); prepared=Signal(object,object,bool)
    def __init__(self,p,note,hold,path=None):
        super().__init__(); self.args=(p,note,hold,path); self.cancelled=False
    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix='seqdestroy-') as folder:
                path=self.args[3] or str(Path(folder)/'preview.wav')
                render(*self.args[:3],path,progress=lambda n:self.progress.emit(int(n*.8)),cancel=lambda:self.cancelled)
                if self.args[3]:save_patch(path+'.patch.json',self.args[0])
                with wave.open(path) as wav:audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').reshape(-1,2).copy()
                db=None  # Analysis is scheduled independently by the visualization panel.
                if self.cancelled:raise Cancelled()
                self.prepared.emit(audio,db,self.args[3] is None); self.progress.emit(100)
                self.result.emit('Timed preview ready.' if self.args[3] is None else 'Saved WAV and companion patch; spectrogram analysis scheduled.')
        except Cancelled:self.result.emit('Cancelled. Any export already completed remains saved.')
        except Exception as e:self.result.emit('Render/analysis error: '+str(e))

class Window(QMainWindow):
    def __init__(self,settings=None):
        super().__init__(); self.setWindowTitle('SeqAndDestroy · Sample synth'); self.resize(1150,470)
        self.settings=settings if settings is not None else QSettings("SeqAndDestroy", "SeqAndDestroy2")
        self.controls={}; self.voice=None; self.audio=None; self.worker=None; self.project=None; self.history=np.zeros(2048); self.ticks=0; self.preview_buffer=None; self.preview_audio=None; self.pending=b''
        root=QWidget(); self.setCentralWidget(root); layout=QVBoxLayout(root); buttons=QHBoxLayout(); layout.addLayout(buttons)
        for name,fn in [('Open/create project',self.project_open),('Load patch',self.load),('Save patch',self.save),('Render sample',self.export),('Timed preview · F2',self.preview),('Stop preview',self.stop_preview)]:
            b=QPushButton(name); b.clicked.connect(fn); buttons.addWidget(b)
        self.location=QLabel('Choose a project folder to store patches and samples.'); layout.addWidget(self.location)
        row=QHBoxLayout(); layout.addLayout(row); self.note=QSpinBox(); self.note.setRange(0,127); self.note.setValue(60)
        self.hold=QDoubleSpinBox(); self.hold.setRange(.01,120); self.hold.setValue(1)
        row.addWidget(QLabel('MIDI note')); row.addWidget(self.note); row.addWidget(QLabel('Timed preview / export hold (seconds)')); row.addWidget(self.hold)
        b=QPushButton('Hold to audition · F1'); b.pressed.connect(self.start); b.released.connect(self.stop); row.addWidget(b)
        columns=QHBoxLayout(); layout.addLayout(columns); forms=[]
        for title in ['Oscillators','Filter and envelopes','Modulation']:
            group=QGroupBox(title); form=QFormLayout(group); forms.append(form); columns.addWidget(group)
        for name,value in asdict(Patch()).items():
            if isinstance(value,str):
                c=QComboBox(); c.addItems(['FM','Ring'] if name=='modulation' else ['Sine','Saw','Square','Triangle']); c.setCurrentText(value)
            else:
                c=QDoubleSpinBox(); c.setDecimals(3); c.setRange(*LIMITS[name]); c.setValue(value); c.setSingleStep(100 if name in ('cutoff','filter_env') else .01 if name in ('mix','noise','attack','decay','sustain','release','resonance') else .1)
            label={'pan1':'Osc 1 pan (−1 L / +1 R)','pan2':'Osc 2 pan (−1 L / +1 R)','noise_pan':'Noise pan (−1 L / +1 R)'}.get(name,name.replace('_',' ').capitalize()); c.setAccessibleName(label); self.controls[name]=c
            index=0 if name in ('wave1','wave2','detune','mix','noise','pan1','pan2','noise_pan') else 1 if name in ('cutoff','resonance','attack','decay','sustain','release','filter_env') else 2
            forms[index].addRow(label,c)
        self.scope=Plot(); self.spectrum=Plot(True); self.spectrogram=Spectrogram()
        self.visualizations={}
        view=self.menuBar().addMenu('&View')
        for offset,(key,title,plot) in enumerate((('scope','Oscilloscope',self.scope),('spectrum','Spectrum analyzer',self.spectrum),('spectrogram','Spectrogram',self.spectrogram))):
            window=VisualizationWindow(self,title,plot,self.settings,key,offset)
            self.visualizations[key]=window
            view.addAction(window.action)
        view.addSeparator()
        view.addAction('Bring visible visualizations to front',self.bring_visualizations_forward)
        view.addAction('Reset window positions',self.reset_visualization_positions)
        self.status=QLabel('Hold F1 to audition · Tab to navigate · Arrow keys adjust controls'); layout.addWidget(self.status)
        self.timer=QTimer(self); self.timer.timeout.connect(self.pump); self.timer.start(20)
        QApplication.instance().installEventFilter(self)
    def bring_visualizations_forward(self):
        for window in self.visualizations.values():
            if window.action.isChecked():
                if window.isMinimized():window.showNormal()
                window.ensure_on_screen(); window.raise_(); window.activateWindow()
    def reset_visualization_positions(self):
        for window in self.visualizations.values():window.reset_position()
    def eventFilter(self,obj,e):
        if e.type()==QEvent.Type.KeyPress and e.key()==Qt.Key.Key_F2:
            if not e.isAutoRepeat():self.preview()
            return True
        if e.type() in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease) and e.key()==Qt.Key.Key_F1:
            if not e.isAutoRepeat():self.start() if e.type()==QEvent.Type.KeyPress else self.stop()
            return True
        if e.type()==QEvent.Type.ApplicationDeactivate:self.stop()
        return super().eventFilter(obj,e)
    def patch(self):return Patch(**{k:c.currentText() if isinstance(c,QComboBox) else c.value() for k,c in self.controls.items()})
    def setup_audio(self):
        if self.audio:self.audio.stop(); self.audio.deleteLater(); self.audio=None
        output=QMediaDevices.defaultAudioOutput(); fmt=QAudioFormat(); fmt.setSampleRate(RATE); fmt.setChannelCount(2); fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if output.isNull() or not output.isFormatSupported(fmt):
            self.status.setText('No compatible 48 kHz stereo output. Rendering and analysis remain available.'); return False
        self.audio=QAudioSink(output,fmt,self); self.audio.setBufferSize(16384)
        return True
    def start(self):
        if self.worker and self.worker.isRunning():return
        if self.voice and self.voice.off is None:return
        self.stop_preview()
        if not self.setup_audio():return
        self.device=self.audio.start()
        if self.device is None:self.status.setText('Could not start audio output.'); return
        self.pending=b''; self.voice=Voice(self.patch(),self.note.value()); self.status.setText('F1 sustain: release the key to release the note. Use F2 for the timed duration.')
    def stop(self):
        if self.voice:self.voice.release()
    def stop_preview(self):
        self.voice=None; self.pending=b''
        if self.audio:self.audio.stop()
        if self.preview_buffer:self.preview_buffer.close(); self.preview_buffer.deleteLater()
        self.preview_buffer=None; self.preview_audio=None
        self.spectrogram.position=None
        if self.spectrogram.isVisible():self.spectrogram.update()
    def display_audio(self,a):
        visible=[plot for plot in (self.scope,self.spectrum) if plot.isVisible() and not plot.window().isMinimized()]
        if not visible:return
        self.history=np.concatenate((self.history,a.mean(axis=1)))[-2048:]
        for plot in visible:plot.data=self.history; plot.update()
    def pump(self):
        if self.preview_buffer is not None:
            position=self.audio.processedUSecs()/1000000; index=int(position*RATE)
            self.spectrogram.position=position
            if self.spectrogram.isVisible() and not self.spectrogram.window().isMinimized():self.spectrogram.update()
            a=self.preview_audio[max(0,index-2048):index]
            if len(a):self.display_audio(a.astype(np.float32)/32768)
            if index>=len(self.preview_audio):self.stop_preview()
            return
        if self.voice is None:return
        if self.pending:
            written=self.device.write(self.pending)
            if written>0:self.pending=self.pending[written:]
            return
        if self.voice.finished:self.voice=None; return
        n=min(2048,self.audio.bytesFree()//4)
        if n<128:return
        self.voice.p=self.patch(); a=self.voice.block(n); self.pending=(a*32767).astype('<i2').tobytes(); self.ticks+=1
        if self.ticks%3==0:self.display_audio(a)
    def preview(self):
        if self.worker and self.worker.isRunning():return
        self.begin_render()
    def begin_render(self,path=None):
        self.stop_preview()
        self.dialog=QProgressDialog('Rendering stereo sound…','Cancel',0,100,self)
        self.dialog.setAutoClose(False); self.dialog.setAutoReset(False); self.dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.worker=Export(self.patch(),self.note.value(),self.hold.value(),path)
        self.worker.progress.connect(self.dialog.setValue); self.worker.result.connect(self.export_done); self.worker.prepared.connect(self.prepared)
        self.dialog.canceled.connect(lambda:setattr(self.worker,'cancelled',True)); self.worker.start(); self.dialog.show()
    def prepared(self,a,db,preview):
        self.spectrogram.set_audio(a,RATE)
        self.display_audio(a[:2048].astype(np.float32)/32768)
        if preview and self.setup_audio():
            self.preview_audio=a; self.preview_buffer=QBuffer(self); self.preview_buffer.setData(QByteArray(a.tobytes()))
            self.preview_buffer.open(QIODevice.OpenModeFlag.ReadOnly); self.audio.start(self.preview_buffer)

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
        self.begin_render(path)
    def export_done(self,message):
        self.dialog.close()
        if message!='Timed preview ready.' or self.preview_buffer is not None:self.status.setText(message)
    def closeEvent(self,e):
        self.spectrogram.shutdown()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
        for window in self.visualizations.values():
            window.save(); window.hide()
        self.settings.sync()
        if self.worker and self.worker.isRunning():self.worker.cancelled=True; self.worker.wait()
        if self.audio:self.audio.stop()
        e.accept()

def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); w=Window(); w.show(); sys.exit(app.exec())
if __name__=='__main__':main()
