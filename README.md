# Timbre

A Windows desktop app for local, private text to speech, built on **Ming-3.0-tts-0.5B**
(inclusionAI, MIT). Write text, choose or design a voice, and export studio-quality audio.

## Features

- **Voices**
  - Built-in presets
  - Voice design from a written description
  - Free-form delivery instructions
  - Zero-shot cloning from a short recording, with emotion or prosody (speed, pitch, volume) control
  - A voice library for reusing voices
- **Full control**
  - Generation: guidance, variation, temperature, chunking, decode steps, paragraph pauses, seed
  - Profiles: save, import and export complete setups
- **Output**
  - WAV (16/24/32-bit float), FLAC, MP3 and Ogg
  - 16–48 kHz, mono or stereo
  - Loudness (LUFS) or peak normalisation, with a ceiling limiter
  - Fades, padding, a rumble filter and file-name templates
- **Any GPU**
  - Hardware is read from the Windows driver registry: NVIDIA, AMD, Intel, Qualcomm and others.
  - Timbre installs the matching PyTorch build: CUDA, ROCm, Intel XPU, DirectML or CPU.
  - You choose the device and precision (BF16/FP16/FP32) and can watch live VRAM use.
  - You can also point Timbre at your own Python environment.
- **History** of every take, with search, playback and one-click reuse of its settings.

## Architecture

```
Timbre.exe (Qt 6 / PySide6 UI, no torch)
   │  JSON lines over stdin/stdout
   ▼
engine/worker.py (runs in the per-GPU runtime: %LOCALAPPDATA%\Timbre\runtimes\<variant>)
   ├─ devices.py      CUDA / ROCm / XPU / DirectML / CPU discovery, memory stats
   ├─ ming_backend.py download with progress, load, synthesis, cancel, progress
   ├─ postprocess.py  resample, loudness, limiter, fades, padding, encoding
   └─ vendor/ming     Ming-3.0-tts runtime (MIT), patched to run on any device/dtype
```

The engine runs as a separate process for three reasons:

- The window stays responsive while audio generates.
- A crash or out-of-memory error can't take the UI down.
- Each GPU family gets its own PyTorch build, with no single huge bundle.

## Run from source

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-ui.txt
.venv\Scripts\python run.py
```

Running from source, Timbre reuses a nearby `.venv` that already has torch. Otherwise its
setup screen installs the right runtime.

## Build the installer

The installer ships the model weights (about 2.8 GB). They are not stored in git, so fetch them once:

```powershell
pip install "huggingface_hub[cli]"
hf download inclusionAI/Ming-3.0-tts-0.5B --local-dir models\Ming-3.0-tts-0.5B --exclude "*.pdf" "figures/*" "README.md"
```

Then build:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The build script produces:

- `dist\Timbre\`: the app folder.
- `dist\Timbre-Setup-0.1.0.exe`: the installer, built when Inno Setup 6 is present (`winget install JRSoftware.InnoSetup`).

The installer is per-user, needs no admin rights, and asks on uninstall whether to remove downloaded runtimes.

## Support status

| Runtime | Status |
|---|---|
| NVIDIA CUDA | Tested (RTX 3060 Laptop, BF16) |
| CPU | Tested (i7-11800H, FP32, installed through the app's own runtime installer) |
| AMD ROCm, Intel XPU, DirectML | Preview: the install sources come from AMD/Intel/PyTorch and are listed in `runtimes.json`. Untested on real hardware. |

Only clone voices you own or have permission to use.
