"""
main.py — Ponto de entrada do Music Auto Manager
Inicializa logging, banco de dados, motor de download e interface gráfica.
"""

import sys
import os
import logging
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Garantir que o diretório do app esteja no sys.path (necessário para .exe)
# ─────────────────────────────────────────────────────────────────────────────
_app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
sys.path.insert(0, str(_app_dir))
os.chdir(str(_app_dir))  # Trabalhar no diretório do app para paths relativos

# ─────────────────────────────────────────────────────────────────────────────
# Imports do projeto (após ajuste de path)
# ─────────────────────────────────────────────────────────────────────────────
from utils import setup_logging
from database import Database
from downloader import DownloadEngine
from settings import settings
from ui import MusicAutoManagerApp
from app_meta import APP_VERSION


def main():
    # Configurar logging
    setup_logging("logs.txt")
    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("MUSIC AUTO MANAGER — iniciando")
    logger.info("Versão app: %s", APP_VERSION)
    logger.info("Versão Python: %s", sys.version)
    logger.info("Diretório app: %s", _app_dir)

    # Inicializar banco de dados
    db = Database("music_manager.db")

    # Inicializar motor de download
    engine = DownloadEngine(db)

    # Criar e executar a interface gráfica
    app = MusicAutoManagerApp(db=db, engine=engine)
    app.mainloop()

    # Encerrar graciosamente
    if engine.is_running:
        engine.stop()
    logger.info("MUSIC AUTO MANAGER — encerrado")


if __name__ == "__main__":
    main()
