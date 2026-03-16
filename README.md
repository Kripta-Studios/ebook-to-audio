# Ebook-to-Audiobook with GPU Acceleration (RTX 50-series)

Convert EPUB and PDF files into high-quality audiobooks using **Kokoro v1.0** for TTS and **OpenAI Whisper** for word-level timestamps.

## 🚀 Features
- **GPU Accelerated**: Fully optimized for NVIDIA RTX 5070 Ti (Blackwell) using CUDA 13.1 and cuDNN 9.
- **Multilingual**: Supports ES, EN, FR, IT, PT, JA, ZH.
- **Timestamp Generation**: Creates `.json` files with word-level timing for synchronized text-audio apps.
- **Smart Resuming**: Automatically detects finished chapters and resumes where it left off.

## 🛠 Prerequisites
- **Python 3.12** (Recommended for CUDA stability)
- **uv** (Fast Python package manager)
- **FFmpeg** & **eSpeak-NG**
- **NVIDIA Drivers** (v570+) & **CUDA Toolkit 13.1** (or 12.8)

## 📦 Installation
```bash
# Clone the repo
git clone [https://github.com/YOUR_USERNAME/ebook-to-audio.git](https://github.com/YOUR_USERNAME/ebook-to-audio.git)
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
2.  **Whisper**:
      - No manual download required. The script downloads the model (e.g., `small`) automatically on first use.

## 📖 Usage

```bash
python audiobook.py "path/to/book.epub" -o "output/filename.mp3" -l es -c -v em_alex --whisper-modelo small
```

  - `-c`: Generate one file per chapter (Recommended for long books).
  - `-v`: Voice selection (e.g., `em_alex`, `ef_dora`).
  - `-l`: Language code (`es`, `en`, `fr`, etc.).

## 🔧 Troubleshooting: Blackwell GPU & Windows DLLs

If you are using an **RTX 50-series (Blackwell)** card on Windows, you might encounter `OSError` or `WinError 126/127`. This is caused by version conflicts between the system's CUDA and PyTorch's internal libraries.

To fix this, the script manually links the following paths:

  - `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin`
  - `C:\Program Files\NVIDIA\CUDNN\v9.20\bin\12.9\x64`

**If your installation paths are different, update the `rutas_gpu` list inside `audiobook.py`.**

````
