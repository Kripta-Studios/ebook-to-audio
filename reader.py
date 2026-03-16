"""
reader.py — Audiobook reader with synchronized word highlighting
Requires: pip install PyQt6 PyMuPDF ebooklib beautifulsoup4

Usage:
    python reader.py                        # opens dialog to choose a file
    python reader.py book.epub              # opens directly
    python reader.py book.epub --audio-dir ./audios   # folder with MP3s
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path

import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from PyQt6.QtCore import (
    Qt, QTimer, QUrl, pyqtSignal, QThread, QObject, QSize,
)
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat, QKeySequence,
    QIcon, QAction, QPalette, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTextEdit, QLabel, QPushButton, QSlider, QLineEdit,
    QFileDialog, QToolBar, QStatusBar, QComboBox,
    QScrollArea, QFrame, QSpinBox, QMessageBox, QDialog,
    QDialogButtonBox, QProgressBar,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


# ─────────────────────────────────────────────────────────────────────────────
# PALETA Y ESTILOS
# ─────────────────────────────────────────────────────────────────────────────
DARK_BG       = "#0f1117"
PANEL_BG      = "#161b27"
BORDER        = "#252d3d"
ACCENT        = "#4e8ef7"
ACCENT_HOVER  = "#6ba3ff"
TEXT_PRIMARY  = "#e8eaf0"
TEXT_SECONDARY= "#7a8499"
HIGHLIGHT_BG  = "#4e8ef733"
HIGHLIGHT_FG  = "#ffffff"
ACTIVE_WORD   = "#ffd166"
ACTIVE_WORD_BG= "#ffd16622"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 2px;
}}
/* Side panel */
QListWidget {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}
QListWidget::item:selected {{
    background: {ACCENT};
    color: white;
}}
QListWidget::item:hover:!selected {{
    background: {BORDER};
}}
/* Text area */
QTextEdit {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 24px 32px;
    font-size: 17px;
    line-height: 1.8;
    color: {TEXT_PRIMARY};
    selection-background-color: {HIGHLIGHT_BG};
}}
/* Toolbar */
QToolBar {{
    background: {PANEL_BG};
    border-bottom: 1px solid {BORDER};
    padding: 6px 12px;
    spacing: 8px;
}}
QToolBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
/* Buttons */
QPushButton {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT_PRIMARY};
    padding: 8px 16px;
    font-size: 13px;
    min-width: 80px;
}}
QPushButton:hover {{
    background: {BORDER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {ACCENT};
    color: white;
}}
QPushButton#play_btn {{
    background: {ACCENT};
    border: none;
    color: white;
    font-size: 18px;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    border-radius: 24px;
}}
QPushButton#play_btn:hover {{
    background: {ACCENT_HOVER};
}}
/* Progress slider */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: white;
    border: 2px solid {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT};
}}
/* Speed slider */
QSlider#speed_slider::groove:horizontal {{
    height: 3px;
    background: {BORDER};
    border-radius: 1px;
}}
QSlider#speed_slider::sub-page:horizontal {{
    background: #7c5cbf;
    border-radius: 1px;
}}
QSlider#speed_slider::handle:horizontal {{
    background: white;
    border: 2px solid #7c5cbf;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
/* Search */
QLineEdit {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 6px 12px;
    font-size: 13px;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
/* Status bar */
QStatusBar {{
    background: {PANEL_BG};
    border-top: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
    font-size: 12px;
    padding: 2px 8px;
}}
/* ComboBox */
QComboBox {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 10px;
    font-size: 12px;
    min-width: 80px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
/* Section labels */
QLabel#section_label {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 4px 4px 4px;
}}
QLabel#time_label {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-family: 'Consolas', monospace;
    min-width: 90px;
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN DE TEXTO
# ─────────────────────────────────────────────────────────────────────────────
def extraer_capitulos_epub(ruta):
    libro = epub.read_epub(ruta)
    capitulos = []
    for item in libro.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            sopa = BeautifulSoup(item.get_content(), "html.parser")
            # Chapter title
            h = sopa.find(["h1", "h2", "h3"])
            titulo = h.get_text(strip=True) if h else f"Chapter {len(capitulos)+1}"
            texto  = sopa.get_text(separator=" ")
            if len(texto.strip()) > 150:
                capitulos.append({"titulo": titulo, "texto": texto.strip()})
    return capitulos

def extraer_capitulos_pdf(ruta, paginas_por_parte=20):
    doc = fitz.open(ruta)
    capitulos = []
    texto_actual = ""
    for i, pagina in enumerate(doc):
        texto_actual += pagina.get_text("text") + "\n"
        if (i + 1) % paginas_por_parte == 0:
            capitulos.append({
                "titulo": f"Pages {i+2-paginas_por_parte}–{i+1}",
                "texto":  texto_actual.strip()
            })
            texto_actual = ""
    if texto_actual.strip():
        n = len(capitulos) * paginas_por_parte
        capitulos.append({
            "titulo": f"Pages {n+1}–end",
            "texto":  texto_actual.strip()
        })
    return capitulos


# ─────────────────────────────────────────────────────────────────────────────
# BUSCADOR DE ARCHIVOS DE AUDIO Y TIMESTAMPS
# ─────────────────────────────────────────────────────────────────────────────
def encontrar_audio_para_capitulo(libro_path, cap_index, audio_dir=None):
    """
    Finds the MP3 and JSON file corresponding to a chapter.
    Strategy: looks for files containing _cap_XX in the same directory
    as the book, or in audio_dir if specified.
    """
    base_dir = audio_dir or os.path.dirname(libro_path)
    libro_nombre = Path(libro_path).stem

    for ext in (".mp3", ".wav", ".ogg", ".flac"):
        patron = os.path.join(base_dir, f"{libro_nombre}_cap_{cap_index+1:02d}{ext}")
        if os.path.exists(patron):
            json_path = patron.rsplit(".", 1)[0] + ".json"
            return patron, (json_path if os.path.exists(json_path) else None)

    # Fallback: busca cualquier archivo _cap_XX
    for f in sorted(os.listdir(base_dir)):
        if f"_cap_{cap_index+1:02d}" in f and f.endswith((".mp3", ".wav", ".ogg", ".flac")):
            full = os.path.join(base_dir, f)
            json_path = full.rsplit(".", 1)[0] + ".json"
            return full, (json_path if os.path.exists(json_path) else None)

    return None, None

def encontrar_audio_libro_completo(libro_path, audio_dir=None):
    base_dir = audio_dir or os.path.dirname(libro_path)
    libro_nombre = Path(libro_path).stem
    for ext in (".mp3", ".wav", ".ogg", ".flac"):
        candidato = os.path.join(base_dir, libro_nombre + ext)
        if os.path.exists(candidato):
            json_path = candidato.rsplit(".", 1)[0] + ".json"
            return candidato, (json_path if os.path.exists(json_path) else None)
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET DE TEXTO CON SUBRAYADO
# ─────────────────────────────────────────────────────────────────────────────
class TextoLector(QTextEdit):
    palabra_clickada = pyqtSignal(int)  # index of the word in the JSON

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.palabras_json = []      # list of {word, start, end}
        self.indice_activo = -1
        self.posiciones    = []      # [(start_pos, end_pos)] in document
        self._texto_completo = ""
        # Add internal margin (viewport margins) to the document
        self.setViewportMargins(40, 0, 40, 0)  # Left, Top, Right, Bottom

        # Comfortable reading font
        font = QFont("Georgia", 17)
        font.setStyleHint(QFont.StyleHint.Serif)
        self.setFont(font)

    def cargar_texto(self, texto, palabras_json=None):
        self._texto_completo = texto
        self.palabras_json   = palabras_json or []
        self.indice_activo   = -1
        self.setPlainText(texto)

        if palabras_json:
            self._calcular_posiciones()

    def _calcular_posiciones(self):
        """
        Maps each entry in the words JSON to its position in the QTextEdit.
        Uses sequential search to avoid mismatches with repeated words.
        """
        self.posiciones = []
        texto = self._texto_completo
        prev_cursor_pos = 0
        cursor_pos = 0

        for entrada in self.palabras_json:
            word = entrada["word"]
            # Eliminar puntuación de los extremos para buscar
            word_clean = re.sub(r"^[^\w]+|[^\w]+$", "", word)
            if not word_clean:
                self.posiciones.append(None)
                continue

            idx = texto.lower().find(word_clean.lower(), cursor_pos)
            if idx == -1:
                # Intentar sin límite de cursor (por si Whisper reordenó)
                idx = texto.lower().find(word_clean.lower())

            if idx != -1 and idx < (prev_cursor_pos + 100):
                self.posiciones.append((idx, idx + len(word_clean)))
                cursor_pos = idx + len(word_clean)
                prev_cursor_pos = cursor_pos
            else:
                self.posiciones.append(None)

    
    def resaltar_palabra(self, indice):
        if indice == self.indice_activo:
            return
        doc = self.document()

        # Quitar resaltado anterior
        if 0 <= self.indice_activo < len(self.posiciones):
            pos = self.posiciones[self.indice_activo]
            if pos:
                cur = QTextCursor(doc)
                cur.setPosition(pos[0])
                cur.setPosition(pos[1], QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(0, 0, 0, 0))
                fmt.setForeground(QColor(TEXT_PRIMARY))
                fmt.setFontWeight(QFont.Weight.Normal)
                cur.setCharFormat(fmt)

        self.indice_activo = indice

        # Aplicar nuevo resaltado
        if 0 <= indice < len(self.posiciones):
            pos = self.posiciones[indice]
            if pos:
                cur = QTextCursor(doc)
                cur.setPosition(pos[0])
                cur.setPosition(pos[1], QTextCursor.MoveMode.KeepAnchor)

                # Definimos el formato siempre dentro del rango de uso
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(ACTIVE_WORD_BG))
                fmt.setForeground(QColor(ACTIVE_WORD))
                # fmt.setFontWeight(QFont.Weight.Bold) # Desactiva si el texto sigue saltando
                
                # Aplicamos el formato antes de calcular el scroll
                cur.setCharFormat(fmt)

                # --- Centering logic ---
                # Use a 0ms timer to ensure Qt has rendered the change
                # and the position calculation is accurate.
                rect = self.cursorRect(cur)
                scrollbar = self.verticalScrollBar()
                viewport_height = self.viewport().height()
                
                posicion_ideal = scrollbar.value() + rect.top() - (viewport_height // 2) + (rect.height() // 2)
                scrollbar.setValue(posicion_ideal)

    def quitar_resaltado(self):
        if self.indice_activo >= 0:
            self.resaltar_palabra(-1)
        self.indice_activo = -1
        # Limpiar todo el formato
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(0, 0, 0, 0))
        fmt.setForeground(QColor(TEXT_PRIMARY))
        fmt.setFontWeight(QFont.Weight.Normal)
        cur.setCharFormat(fmt)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.palabras_json:
            # Encontrar qué palabra se clickó
            cursor = self.cursorForPosition(event.pos())
            click_pos = cursor.position()
            for i, pos in enumerate(self.posiciones):
                if pos and pos[0] <= click_pos <= pos[1]:
                    self.palabra_clickada.emit(i)
                    break

    def buscar_texto(self, query):
        """Resalta todas las ocurrencias y va a la primera."""
        if not query:
            self.quitar_resaltado()
            return 0
        # Usar find() de Qt
        self.moveCursor(QTextCursor.MoveOperation.Start)
        count = 0
        while self.find(query):
            count += 1
        # Volver al inicio y hacer el primer find
        self.moveCursor(QTextCursor.MoveOperation.Start)
        self.find(query)
        return count

    def ir_a_posicion_porcentaje(self, pct):
        """Scroll al porcentaje dado del documento."""
        sb = self.verticalScrollBar()
        sb.setValue(int(sb.maximum() * pct / 100))


# ─────────────────────────────────────────────────────────────────────────────
# VENTANA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
class ReaderWindow(QMainWindow):
    def __init__(self, libro_path=None, audio_dir=None):
        super().__init__()
        self.libro_path    = libro_path
        self.audio_dir     = audio_dir
        self.capitulos     = []        # [{titulo, texto}]
        self.cap_actual    = -1
        self.palabras_json = []        # timestamps del capítulo actual
        self.indice_actual = 0         # índice de palabra actual en JSON

        self._timer_highlight = QTimer(self)
        self._timer_highlight.setInterval(50)  # 50ms de resolución
        self._timer_highlight.timeout.connect(self._actualizar_highlight)

        self._seekando = False  # true mientras el usuario arrastra el slider
        self._reproduccion_continua = True  # pasar al siguiente cap automáticamente

        self._setup_ui()
        self._setup_media()
        self._setup_shortcuts()

        if libro_path:
            self._abrir_libro(libro_path)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("Audiobook Reader")
        self.setMinimumSize(900, 600)
        self.resize(1400, 850)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top toolbar ───────────────────────────────────────────────────
        self._setup_toolbar()

        # ── Main splitter ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)

        # Left panel: index + search
        left = QWidget()
        left.setFixedWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 8, 12)
        left_layout.setSpacing(8)

        lbl_buscar = QLabel("SEARCH")
        lbl_buscar.setObjectName("section_label")
        left_layout.addWidget(lbl_buscar)

        buscar_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in text...")
        self.search_input.returnPressed.connect(self._buscar)
        buscar_row.addWidget(self.search_input)
        btn_buscar = QPushButton("↵")
        btn_buscar.setFixedWidth(36)
        btn_buscar.clicked.connect(self._buscar)
        buscar_row.addWidget(btn_buscar)
        left_layout.addLayout(buscar_row)

        self.search_count_label = QLabel("")
        self.search_count_label.setObjectName("section_label")
        left_layout.addWidget(self.search_count_label)

        lbl_indice = QLabel("TABLE OF CONTENTS")
        lbl_indice.setObjectName("section_label")
        left_layout.addWidget(lbl_indice)

        self.lista_capitulos = QListWidget()
        self.lista_capitulos.currentRowChanged.connect(self._cambiar_capitulo)
        left_layout.addWidget(self.lista_capitulos)

        splitter.addWidget(left)

        # Right panel: text
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 12, 12, 0)
        right_layout.setSpacing(8)

        self.texto = TextoLector()
        self.texto.palabra_clickada.connect(self._saltar_a_palabra)
        right_layout.addWidget(self.texto)

        splitter.addWidget(right)
        splitter.setSizes([260, 1140])

        # ── Playback panel ────────────────────────────────────────────────
        self._setup_player_panel(root_layout)

        # ── Status bar ────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Open a book to get started  ·  Ctrl+O")

    def _setup_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)

        btn_open = QPushButton("📂  Open book")
        btn_open.clicked.connect(self._dialogo_abrir)
        tb.addWidget(btn_open)

        btn_audio_dir = QPushButton("🎵  Open audio folder")
        btn_audio_dir.clicked.connect(self._dialogo_audio_dir)
        tb.addWidget(btn_audio_dir)

        tb.addSeparator()

        tb.addWidget(QLabel("  Font size:"))
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 36)
        self.font_size.setValue(17)
        self.font_size.valueChanged.connect(self._cambiar_fuente)
        tb.addWidget(self.font_size)

        tb.addSeparator()

        # Font selector
        tb.addWidget(QLabel("  Font:"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Georgia", "Times New Roman", "Segoe UI",
                                   "Consolas", "Calibri", "Palatino Linotype"])
        self.font_combo.currentTextChanged.connect(self._cambiar_fuente)
        tb.addWidget(self.font_combo)

        tb.addSeparator()

        # Night / day mode
        self.btn_tema = QPushButton("☀️  Day")
        self.btn_tema.clicked.connect(self._toggle_tema)
        self._modo_oscuro = True
        tb.addWidget(self.btn_tema)

        tb.addSeparator()

        # Continuous playback
        self.btn_continua = QPushButton("🔁  Auto-play: ON")
        self.btn_continua.setCheckable(True)
        self.btn_continua.setChecked(True)
        self.btn_continua.clicked.connect(self._toggle_continua)
        self.btn_continua.setStyleSheet(
            f"QPushButton:checked {{ background: #2a4a2a; border-color: #4caf50; color: #4caf50; }}"
        )
        tb.addWidget(self.btn_continua)

        self.btn_sync = QPushButton("🎯  Sync: ON")
        self.btn_sync.setCheckable(True)
        self.btn_sync.setChecked(True)
        self.btn_sync.clicked.connect(self._toggle_sync)
        self.btn_sync.setStyleSheet(
            f"QPushButton:checked {{ background: #2a3a4a; border-color: {ACCENT}; color: {ACCENT}; }}"
        )
        tb.addWidget(self.btn_sync)

    def _setup_player_panel(self, parent_layout):
        panel = QWidget()
        panel.setFixedHeight(110)
        panel.setStyleSheet(f"background:{PANEL_BG}; border-top: 1px solid {BORDER};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(6)

        # Progress bar
        progress_row = QHBoxLayout()
        self.time_label = QLabel("0:00")
        self.time_label.setObjectName("time_label")
        self.time_total_label = QLabel("0:00")
        self.time_total_label.setObjectName("time_label")
        self.time_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderPressed.connect(lambda: setattr(self, "_seekando", True))
        self.progress_slider.sliderReleased.connect(self._seek)
        self.progress_slider.sliderMoved.connect(self._preview_tiempo)

        progress_row.addWidget(self.time_label)
        progress_row.addWidget(self.progress_slider)
        progress_row.addWidget(self.time_total_label)
        layout.addLayout(progress_row)

        # Controls
        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        # Retroceder 10s
        btn_back = QPushButton("⏮ 10s")
        btn_back.setFixedWidth(70)
        btn_back.clicked.connect(lambda: self._saltar_segundos(-10))
        controls_row.addWidget(btn_back)

        # Play/Pause
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("play_btn")
        self.btn_play.clicked.connect(self._toggle_play)
        controls_row.addWidget(self.btn_play)

        # Adelantar 10s
        btn_fwd = QPushButton("10s ⏭")
        btn_fwd.setFixedWidth(70)
        btn_fwd.clicked.connect(lambda: self._saltar_segundos(10))
        controls_row.addWidget(btn_fwd)

        controls_row.addStretch()

        # Speed
        controls_row.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setObjectName("speed_slider")
        self.speed_slider.setRange(50, 300)  # 0.5x – 2.0x
        self.speed_slider.setValue(100)
        self.speed_slider.setFixedWidth(140)
        self.speed_slider.valueChanged.connect(self._cambiar_velocidad)
        controls_row.addWidget(self.speed_slider)

        self.speed_label = QLabel("1.0×")
        self.speed_label.setObjectName("time_label")
        self.speed_label.setFixedWidth(40)
        controls_row.addWidget(self.speed_label)

        controls_row.addStretch()

        # Volume
        controls_row.addWidget(QLabel("Vol:"))
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self._cambiar_volumen)
        controls_row.addWidget(self.vol_slider)

        # Previous / next chapter
        controls_row.addStretch()
        btn_prev_cap = QPushButton("◀ Ch")
        btn_prev_cap.setFixedWidth(70)
        btn_prev_cap.clicked.connect(self._cap_anterior)
        controls_row.addWidget(btn_prev_cap)

        btn_next_cap = QPushButton("Ch ▶")
        btn_next_cap.setFixedWidth(70)
        btn_next_cap.clicked.connect(self._cap_siguiente)
        controls_row.addWidget(btn_next_cap)

        layout.addLayout(controls_row)
        parent_layout.addWidget(panel)

    def _setup_media(self):
        self.player  = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.audio_out.setVolume(0.8)
        self.player.setAudioOutput(self.audio_out)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+O"), self, self._dialogo_abrir)
        QShortcut(QKeySequence("Space"),  self, self._toggle_play)
        QShortcut(QKeySequence("Left"),   self, lambda: self._saltar_segundos(-5))
        QShortcut(QKeySequence("Right"),  self, lambda: self._saltar_segundos(5))
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_buscar)
        QShortcut(QKeySequence("Ctrl+Up"),   self, self._cap_anterior)
        QShortcut(QKeySequence("Ctrl+Down"), self, self._cap_siguiente)

    # ── Book opening ──────────────────────────────────────────────────────
    def _dialogo_abrir(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open book", "",
            "Books (*.epub *.pdf);;EPUB (*.epub);;PDF (*.pdf)"
        )
        if path:
            self._abrir_libro(path)

    def _dialogo_audio_dir(self):
        """Open a folder picker to set the audio directory at runtime."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select audio folder", self.audio_dir or ""
        )
        if folder:
            self.audio_dir = folder
            self.status.showMessage(f"Audio folder: {folder}")
            # Reload current chapter to pick up the new audio path
            if self.cap_actual >= 0:
                self._cambiar_capitulo(self.cap_actual)

    def _abrir_libro(self, path):
        self.libro_path = path
        self.player.stop()
        self._timer_highlight.stop()

        try:
            if path.lower().endswith(".epub"):
                self.capitulos = extraer_capitulos_epub(path)
            elif path.lower().endswith(".pdf"):
                self.capitulos = extraer_capitulos_pdf(path)
            else:
                QMessageBox.warning(self, "Error", "Unsupported format.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error opening file", str(e))
            return

        # Populate index
        self.lista_capitulos.blockSignals(True)
        self.lista_capitulos.clear()
        for i, cap in enumerate(self.capitulos):
            item = QListWidgetItem(f"{i+1}. {cap['titulo']}")
            self.lista_capitulos.addItem(item)
        self.lista_capitulos.blockSignals(False)

        nombre = Path(path).name
        self.setWindowTitle(f"Reader — {nombre}")
        self.status.showMessage(f"Book loaded: {nombre}  ·  {len(self.capitulos)} chapters")

        # Ir al primer capítulo
        self.lista_capitulos.setCurrentRow(0)

    def _cambiar_capitulo(self, row):
        if row < 0 or row >= len(self.capitulos):
            return
        self.cap_actual = row
        self.player.stop()
        self._timer_highlight.stop()
        self.btn_play.setText("▶")

        cap = self.capitulos[row]

        # Buscar audio y timestamps
        audio_path, json_path = encontrar_audio_para_capitulo(
            self.libro_path, row, self.audio_dir
        )
        # Fallback: libro completo
        if not audio_path:
            audio_path, json_path = encontrar_audio_libro_completo(
                self.libro_path, self.audio_dir
            )

        # Cargar timestamps si existen
        palabras = []
        if json_path:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                palabras = data.get("palabras", [])
            except Exception:
                pass

        self.palabras_json = palabras
        self.indice_actual = 0
        self.texto.cargar_texto(cap["texto"], palabras if palabras else None)

        # Cargar audio
        if audio_path:
            self.player.setSource(QUrl.fromLocalFile(audio_path))
            estado = "▶ Ready"
            self.status.showMessage(
                f"Chapter {row+1}: {cap['titulo']}  ·  Audio: {Path(audio_path).name}"
                + (f"  ·  {len(palabras)} timestamps" if palabras else "  ·  No timestamps")
            )
        else:
            self.player.setSource(QUrl())
            self.status.showMessage(
                f"Chapter {row+1}: {cap['titulo']}  ·  No audio found"
            )

    # ── Playback ──────────────────────────────────────────────────────
    def _toggle_play(self):
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self._timer_highlight.stop()
        else:
            self.player.play()
            if self.palabras_json:
                self._timer_highlight.start()

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸")
        else:
            self.btn_play.setText("▶")

        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._timer_highlight.stop()
            self.texto.quitar_resaltado()

            # Reproducción continua: pasar al siguiente capítulo automáticamente
            if self._reproduccion_continua:
                row = self.lista_capitulos.currentRow()
                siguiente = row + 1
                if siguiente < self.lista_capitulos.count():
                    # Pequeña pausa de 800ms antes de arrancar el siguiente cap
                    QTimer.singleShot(800, lambda: self._avanzar_capitulo(siguiente))
                else:
                    self.status.showMessage("✓ End of book.")

    def _avanzar_capitulo(self, row):
        """Switches to the given chapter and starts playback."""
        self.lista_capitulos.setCurrentRow(row)
        # _cambiar_capitulo is already called via the currentRowChanged signal,
        # but the player needs one tick to load the source before play()
        QTimer.singleShot(200, self._autoplay)

    def _autoplay(self):
        """Starts playback if audio is loaded."""
        if self.player.source().isValid():
            self.player.play()
            if self.palabras_json:
                self._timer_highlight.start()

    def _on_position_changed(self, pos_ms):
        if not self._seekando:
            duracion = self.player.duration()
            if duracion > 0:
                self.progress_slider.setValue(int(pos_ms / duracion * 1000))
            self.time_label.setText(self._fmt_tiempo(pos_ms))

    def _on_duration_changed(self, dur_ms):
        self.time_total_label.setText(self._fmt_tiempo(dur_ms))

    def _seek(self):
        self._seekando = False
        duracion = self.player.duration()
        if duracion > 0:
            pos = int(self.progress_slider.value() / 1000 * duracion)
            self.player.setPosition(pos)
            # Actualizar índice de palabra
            self._actualizar_indice_por_tiempo(pos / 1000)

    def _preview_tiempo(self, val):
        duracion = self.player.duration()
        if duracion > 0:
            t = int(val / 1000 * duracion)
            self.time_label.setText(self._fmt_tiempo(t))

    def _saltar_segundos(self, secs):
        pos = self.player.position() + secs * 1000
        pos = max(0, min(pos, self.player.duration()))
        self.player.setPosition(int(pos))
        self._actualizar_indice_por_tiempo(pos / 1000)

    def _cambiar_velocidad(self, val):
        speed = val / 100.0
        self.player.setPlaybackRate(speed)
        self.speed_label.setText(f"{speed:.1f}×")

    def _cambiar_volumen(self, val):
        self.audio_out.setVolume(val / 100.0)

    # ── Synchronized highlighting ─────────────────────────────────────────
    def _actualizar_highlight(self):
        # Si el botón de sync está desactivado, no hacemos nada
        if not self.btn_sync.isChecked():
            return
            
        if not self.palabras_json:
            return
        t = self.player.position() / 1000.0
        self._actualizar_indice_por_tiempo(t)

    def _actualizar_indice_por_tiempo(self, t_secs):
        if not self.palabras_json:
            return
        # Binary search for the current word index
        lo, hi = 0, len(self.palabras_json) - 1
        idx = 0
        while lo <= hi:
            mid = (lo + hi) // 2
            p = self.palabras_json[mid]
            if p["start"] <= t_secs <= p["end"]:
                idx = mid
                break
            elif p["end"] < t_secs:
                idx = mid
                lo = mid + 1
            else:
                hi = mid - 1

        self.indice_actual = idx
        self.texto.resaltar_palabra(idx)

    def _saltar_a_palabra(self, indice):
        """User clicked a word — jump to that point in the audio."""
        if indice < len(self.palabras_json):
            t_ms = int(self.palabras_json[indice]["start"] * 1000)
            self.player.setPosition(t_ms)
            self.indice_actual = indice
            self.texto.resaltar_palabra(indice)
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()
                self._timer_highlight.start()

    # ── Chapter navigation ────────────────────────────────────────────────
    def _cap_anterior(self):
        row = self.lista_capitulos.currentRow()
        if row > 0:
            self.lista_capitulos.setCurrentRow(row - 1)

    def _cap_siguiente(self):
        row = self.lista_capitulos.currentRow()
        if row < self.lista_capitulos.count() - 1:
            self.lista_capitulos.setCurrentRow(row + 1)

    # ── Search ────────────────────────────────────────────────────────
    def _buscar(self):
        query = self.search_input.text().strip()
        if not query:
            self.texto.quitar_resaltado()
            self.search_count_label.setText("")
            return
        count = self.texto.buscar_texto(query)
        if count > 0:
            self.search_count_label.setText(f"{count} match(es)")
        else:
            self.search_count_label.setText("No results")

    def _focus_buscar(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ── Appearance ────────────────────────────────────────────────────
    def _toggle_sync(self, checked):
        if checked:
            self.btn_sync.setText("🎯  Sync: ON")
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._timer_highlight.start()
        else:
            self.btn_sync.setText("🔓  Free scroll")
            self.texto.quitar_resaltado()

    def _cambiar_fuente(self):
        familia = self.font_combo.currentText()
        tamaño  = self.font_size.value()
        font = QFont(familia, tamaño)
        self.texto.setFont(font)

    def _toggle_continua(self, checked):
        self._reproduccion_continua = checked
        if checked:
            self.btn_continua.setText("🔁  Auto-play: ON")
        else:
            self.btn_continua.setText("⏹  Auto-play: OFF")

    def _toggle_tema(self):
        if self._modo_oscuro:
            # Day mode
            self.texto.setStyleSheet(
                f"background: #faf8f2; color: #1a1a2e; "
                f"border: 1px solid #ddd; border-radius: 8px; "
                f"padding: 24px 32px; font-size: 17px;"
            )
            self.btn_tema.setText("🌙  Night")
            self._modo_oscuro = False
        else:
            self.texto.setStyleSheet("")
            self.btn_tema.setText("☀️  Day")
            self._modo_oscuro = True

    # ── Utilities ─────────────────────────────────────────────────────
    @staticmethod
    def _fmt_tiempo(ms):
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Audiobook reader with synchronized word highlighting"
    )
    parser.add_argument("libro", nargs="?", help="Path to PDF or EPUB")
    parser.add_argument("--audio-dir", default=None,
                        help="Folder to search for MP3s (default: same folder as the book)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Audiobook Reader")
    app.setStyleSheet(STYLESHEET)

    window = ReaderWindow(
        libro_path=args.libro,
        audio_dir=args.audio_dir,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()