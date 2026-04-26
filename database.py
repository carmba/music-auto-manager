"""
database.py — Camada de banco de dados SQLite do Music Auto Manager
Gerencia histórico de downloads, duplicatas e estatísticas.
"""

import sqlite3
import hashlib
import logging
from pathlib import Path
from datetime import date, datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_FILE = "music_manager.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL,
    title       TEXT,
    artist      TEXT,
    filename    TEXT,
    filepath    TEXT,
    file_hash   TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending',
    quality     TEXT,
    error_msg   TEXT,
    downloaded_at TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_downloads_url      ON downloads(url);
CREATE INDEX IF NOT EXISTS idx_downloads_filepath ON downloads(filepath);
CREATE INDEX IF NOT EXISTS idx_downloads_file_hash ON downloads(file_hash);
CREATE INDEX IF NOT EXISTS idx_downloads_status   ON downloads(status);
"""


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

class Database:
    """Gerencia todas as operações no banco de dados SQLite."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        """Cria as tabelas se ainda não existirem."""
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLES)
        logger.info("Banco de dados inicializado: %s", self.db_path)

    @contextmanager
    def _get_conn(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # Verificação de duplicatas
    # -----------------------------------------------------------------------

    def is_duplicate_by_url(self, url: str) -> bool:
        """Retorna True se uma URL já foi baixada com sucesso."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM downloads WHERE url = ? AND status = 'success' LIMIT 1",
                (url,)
            ).fetchone()
            return row is not None

    def is_duplicate_by_filepath(self, filepath: str) -> bool:
        """Retorna True se o arquivo já existe no banco."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM downloads WHERE filepath = ? AND status = 'success' LIMIT 1",
                (filepath,)
            ).fetchone()
            return row is not None

    def is_duplicate_by_hash(self, file_hash: str) -> bool:
        """Retorna True se um arquivo com o mesmo hash já foi registrado."""
        if not file_hash:
            return False
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM downloads WHERE file_hash = ? AND status = 'success' LIMIT 1",
                (file_hash,)
            ).fetchone()
            return row is not None

    # -----------------------------------------------------------------------
    # Inserir / Atualizar registros
    # -----------------------------------------------------------------------

    def add_download(
        self,
        url: str,
        title: str = "",
        artist: str = "",
        filename: str = "",
        filepath: str = "",
        quality: str = "192",
        status: str = "pending",
    ) -> int:
        """Insere um novo registro de download. Retorna o ID inserido."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO downloads (url, title, artist, filename, filepath, quality, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (url, title, artist, filename, filepath, quality, status)
            )
            return cursor.lastrowid

    def update_download(self, download_id: int, **kwargs):
        """
        Atualiza campos de um registro de download.
        Campos aceitos: title, artist, filename, filepath, file_hash,
                        status, error_msg, downloaded_at
        """
        allowed = {
            "title", "artist", "filename", "filepath",
            "file_hash", "status", "error_msg", "downloaded_at"
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [download_id]
        with self._get_conn() as conn:
            conn.execute(
                f"UPDATE downloads SET {set_clause} WHERE id = ?",
                values
            )

    def mark_success(self, download_id: int, filepath: str, file_hash: str = ""):
        self.update_download(
            download_id,
            status="success",
            filepath=filepath,
            file_hash=file_hash,
            downloaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def mark_error(self, download_id: int, error_msg: str):
        self.update_download(
            download_id,
            status="error",
            error_msg=error_msg[:1000],
            downloaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def mark_skipped(self, download_id: int, reason: str = "Duplicado"):
        self.update_download(
            download_id,
            status="skipped",
            error_msg=reason,
            downloaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # -----------------------------------------------------------------------
    # Consultas de histórico
    # -----------------------------------------------------------------------

    def get_history(self, limit: int = 200, offset: int = 0) -> list[dict]:
        """Retorna os registros mais recentes do histórico."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, url, title, artist, filename, status, error_msg,
                          quality, downloaded_at, created_at
                   FROM downloads
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Retorna estatísticas gerais do banco."""
        today = date.today().isoformat()
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'success'"
            ).fetchone()[0]

            today_count = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'success' AND downloaded_at LIKE ?",
                (f"{today}%",)
            ).fetchone()[0]

            errors = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'error'"
            ).fetchone()[0]

            skipped = conn.execute(
                "SELECT COUNT(*) FROM downloads WHERE status = 'skipped'"
            ).fetchone()[0]

        return {
            "total": total,
            "today": today_count,
            "errors": errors,
            "skipped": skipped,
        }

    def get_all_filepaths(self) -> set[str]:
        """Retorna todos os caminhos de arquivo já registrados com sucesso."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT filepath FROM downloads WHERE status = 'success' AND filepath != ''"
            ).fetchall()
            return {r[0] for r in rows}

    def clear_history(self):
        """Remove todos os registros do histórico."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM downloads")
        logger.warning("Histórico de downloads apagado.")


# ---------------------------------------------------------------------------
# Utilitário de hash de arquivo
# ---------------------------------------------------------------------------

def compute_file_hash(filepath: str, algorithm: str = "md5") -> str:
    """Calcula o hash de um arquivo para verificação de duplicatas."""
    h = hashlib.new(algorithm)
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        logger.warning("Não foi possível calcular hash de %s: %s", filepath, e)
        return ""
