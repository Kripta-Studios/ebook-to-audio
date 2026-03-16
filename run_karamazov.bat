@echo off
echo Activando entorno virtual uv...
call .venv\Scripts\activate
echo Lanzando audiolibro: Los Hermanos Karamazov
python audiobook.py ".\Karamazov.epub" -o ".\Karamazov_Audio\Karamazov.mp3" -l es -c -v em_alex --whisper-modelo small
pause