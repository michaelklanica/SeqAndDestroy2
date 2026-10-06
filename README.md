# SeqAndDestroy

An initial native desktop sample-synth prototype for Linux Mint. Sequencing and expanded analysis are planned, not implemented yet.

## Run on Linux Mint 22.3

Use Python 3.12 or later. From this checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m seqdestroy.app
```

If Mint reports that venv is unavailable, install its `python3-venv` package. Qt's X11 backend may require the Mint packages `libxcb-cursor0` and `libxkbcommon-x11-0` if they are absent.

## First sound

1. Open/create a project by choosing a folder. The app uses `patches/` and `samples/` beneath it; reopening that folder reuses those files.
2. Hold F1 or the audition button for a manually sustained note. F1 deliberately ignores the timed hold duration. MIDI note 60 is middle C. Release to hear the envelope release. Tab navigates controls; arrow keys adjust values. Controls also accept typed numbers.
3. Adjust oscillator waveforms, mix, noise, filter, envelope, LFO, drive, and FM/ring modulation. Detune is in cents, cutoff and filter envelope depth in Hz, envelope times in seconds, LFO pitch depth in semitones. Ring modulation reaches full depth at an amount of 1; higher values currently have the same effect.
4. Set oscillator 1, oscillator 2, and noise pan independently: −1 is left, 0 is centered, +1 is right. Centered defaults feed both output channels. Older patches load with centered pans.
5. Press **Timed preview / F2** to render and play the selected hold duration plus release. Preview snapshots the controls and uses exactly the same PCM rendering as export. Use Stop preview to stop playback. Rendering and analysis run in the background with cancellation.
6. Save a patch as JSON or load an existing patch.
7. Choose note-hold time and Render sample. The output is stereo 48 kHz, 16-bit PCM WAV, including the amplitude release. Rendering shows progress and supports cancellation. Each WAV has a companion `.wav.patch.json` which can be loaded using Load patch.

Export cancellation leaves an existing destination WAV untouched. Do not delete companion patch files if you want to recall a sound. Keep projects outside the source checkout.

## Prototype limits

- Audition is monophonic. Audio output must support 48 kHz stereo PCM. No physical output device is available in cloud testing; audition and MPC import need testing on the user's hardware.
- Waveform and linear-frequency spectrum show the mono average of recent playback. The full-sample spectrogram uses combined stereo power, a logarithmic frequency axis (40 Hz–24 kHz), and brightness for −90 to 0 dBFS. It updates after timed preview or export; a playhead follows timed preview. Analysis is capped at 800 time columns to bound memory, so very long samples have reduced time detail. Pitch/confidence, harmonic analysis, sample browsing, sequencer, and loop export are future stages.
- The initial filter envelope shares amplitude envelope timing; independent filter envelope controls are still to come.
- This first DSP implementation uses Python and processes preview blocks on the GUI thread. It is not a finished low-latency audio engine. Heavy modulation may alias; parameter changes are not smoothed yet. Real-time performance and audio quality need refinement and measurement on Mint before calling this production-ready.
- Export runs on a worker thread. WAV and patch are separate saves; an error saving metadata can leave a valid WAV without its companion patch.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests check fundamental frequency, release and hold duration, stereo output and panning, legacy patch compatibility, cancellation preserving existing files, extreme modulation stability, spectrogram frequency detection, exact preview/export PCM equality, and headless GUI rendering.

## Agreed next stages

Complete and refine sound creation first, then add a project sample pool and step sequencer, followed by expanded analysis and workflow tuning. Sequencer tracks share tempo and overall duration but have independent meters. Calculate the earliest shared complete-bar boundary; warn about excessive export duration and size, with revise/cancel options. Support multiple samples per track, overlap by default, directional choke rules, triplets and 1/128 subdivisions. Loop export offers seamless tail wrapping or an extended tail. Imported-recording transformation comes later.
