# Ebook-to-Audiobook with GPU Acceleration (RTX 50-series)

Convert EPUB and PDF files into high-quality audiobooks using **Kokoro v1.0** for TTS and **OpenAI Whisper** for word-level timestamps.

## 🚀 Features
- **GPU Accelerated**: Fully optimized for NVIDIA RTX 5070 Ti (Blackwell) using CUDA 13.1 and cuDNN 9.
- **Multilingual**: Supports ES, EN, FR, IT, PT, JA, ZH.
- **Exact Timestamps**: Creates `.json` files with word-level timing derived directly from Kokoro's audio samples — no drift, no Whisper required.
- **Smart Resuming**: Automatically detects finished chapters and resumes where it left off.

## 🛠 Prerequisites
- **Python 3.12** (Recommended for CUDA stability)
- **uv** (Fast Python package manager)
- **FFmpeg** & **eSpeak-NG**
- **NVIDIA Drivers** (v570+) & **CUDA Toolkit 13.1** (or 12.8)

## 📦 Installation
```bash
# Clone the repo
git clone [https://github.com/Kripta-Studios/ebook-to-audio.git](https://github.com/Kripta-Studios/ebook-to-audio.git)
cd ebook-to-audio

# Create environment and install dependencies
uv venv --python 3.12
# On Windows:
.venv\Scripts\activate
# Install Torch with CUDA 12.8 support (compatible with RTX 50-series)
uv pip install torch torchvision torchaudio --index-url [https://download.pytorch.org/whl/cu128](https://download.pytorch.org/whl/cu128)
uv pip install -r requirements.txt
````

## 📥 Model Setup (Required)

Since the model files are large, they are not included in this repository. Please download them and place them in the root directory:

1.  **Kokoro v1.0**:
      - Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from [Hugging Face](https://www.google.com/search?q=https://huggingface.co/hexgrad/Kokoro-82M/tree/main/onnx).
2.  **Whisper** *(only required for German/Piper)*:
      - No manual download required. The script downloads the model automatically on first use when processing a DE book.

## 📖 Usage

```bash
python audiobook.py "path/to/book.epub" -o "output/filename.mp3" -l es -c -v em_alex
```

  - `-c`: Generate one file per chapter (Recommended for long books).
  - `-v`: Voice selection (e.g., `em_alex`, `ef_dora`).
  - `-l`: Language code (`es`, `en`, `fr`, etc.).
  - `--sin-timestamps`: Skip `.json` generation (faster, timestamps won't work in reader).
  - `--whisper-modelo`: Whisper model size — **only relevant for German (`-l de`)** via Piper.

## 📖 Usage Examples

### Standard Book
```bash
python audiobook.py "book.epub" -o "output/book.mp3" -l es -v em_alex
```

### Large Books (e.g., The Brothers Karamazov)
For massive books, use the `-c` flag to generate one file per chapter. This enables smart resuming if the process is interrupted.
```bash
python audiobook.py "Karamazov.epub" -o "Karamazov_Audio/Karamazov.mp3" -l es -c -v em_alex
```

### 2\. Launch the Synchronized Reader

The reader will automatically find the `.mp3` and `.json` files in the output directory.

```bash
# With audio directory specified via argument
python reader.py "Karamazov.epub" --audio-dir "./Karamazov_Audio"

# On Windows — equivalent shorthand (audio folder only, no book path)
python .\reader.py --audio-dir .\Karamazov_Audio\
```

> **Tip:** When using `--audio-dir` without a book path, the reader will prompt you to open the EPUB/PDF via the **📂 Open book** button in the toolbar. You can also click **🎵 Open audio folder** to change the audio directory at any time from the UI.

**Reader Shortcuts:**

  - `Space`: Play/Pause.
  - `Left/Right`: Seek 5 seconds.
  - `Ctrl + O`: Open book dialog.
  - `Ctrl + F`: Focus search bar.
  - `Click on any word`: Jump audio to that specific word.



## 🔧 Troubleshooting: Blackwell GPU & Windows DLLs

If you are using an **RTX 50-series (Blackwell)** card on Windows, you might encounter `OSError` or `WinError 126/127`. This is caused by version conflicts between the system's CUDA and PyTorch's internal libraries.

To fix this, the script manually links the following paths:

  - `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin`
  - `C:\Program Files\NVIDIA\CUDNN\v9.20\bin\12.9\x64`

**If your installation paths are different, update the `rutas_gpu` list inside `audiobook.py`.**