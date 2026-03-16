.\.venv\Scripts\activate.ps1
python audiobook.py ".\El Ingenioso Hidalgo Don Quijot - Miguel de Cervantes Saavedra.epub" -o .\Quijote.mp3 -l es -c --whisper-modelo tiny
python reader.py
