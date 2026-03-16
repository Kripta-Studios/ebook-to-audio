@echo off
echo Activating virtual environment in uv...
call .venv\Scripts\activate
echo Starting audiobook in Spanish: Los Hermanos Karamazov
python audiobook.py ".\Karamazov.epub" -o ".\Karamazov_Audio\Karamazov.mp3" -l es -c -v em_alex
pause