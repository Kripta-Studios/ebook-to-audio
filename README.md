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
- **NVIDIA Drivers** (v570+) & **CUDA Toolkit 12.8/13.1**

## 📦 Installation
```bash
# Clone the repo
git clone [https://github.com/YOUR_USERNAME/ebook-to-audio.git](https://github.com/YOUR_USERNAME/ebook-to-audio.git)
cd ebook-to-audio

# Create environment and install dependencies
uv venv --python 3.12
source .venv/Scripts/activate
uv pip install torch torchvision torchaudio --index-url [https://download.pytorch.org/whl/cu128](https://download.pytorch.org/whl/cu128)
uv pip install -r requirements.txt

# Usage
python audiobook.py "path/to/book.epub" -o "output/book.mp3" -l es -c -v em_alex