"""
downloader.py — Motor de download do Music Auto Manager
Faz uso de yt-dlp para baixar e converter para MP3 via FFmpeg.
Executa downloads em thread-pool sem travar a interface.
"""

import os
import re
import shutil
import subprocess
import time
import logging
import threading
import queue
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from database import Database, compute_file_hash
from settings import settings
from utils import (
    parse_artist_title,
    canonical_artist_name,
    artist_folder_id,
    sanitize_filename,
    format_bytes,
    format_speed,
    format_eta,
    get_ffmpeg_path,
    get_ffprobe_path,
    download_ffmpeg,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumeração de status
# ---------------------------------------------------------------------------

class DownloadStatus(Enum):
    QUEUED      = "queued"
    DOWNLOADING = "downloading"
    CONVERTING  = "converting"
    SUCCESS     = "success"
    ERROR       = "error"
    SKIPPED     = "skipped"
    PAUSED      = "paused"
    CANCELLED   = "cancelled"


# ---------------------------------------------------------------------------
# Dataclass de item de fila
# ---------------------------------------------------------------------------

@dataclass
class DownloadItem:
    url: str
    quality: str = "192"
    db_id: int = -1

    # Campos preenchidos durante/após o download
    title: str = ""
    artist: str = ""
    filename: str = ""
    filepath: str = ""
    thumbnail_url: str = ""

    status: DownloadStatus = DownloadStatus.QUEUED
    error_msg: str = ""

    # Progresso
    progress: float = 0.0        # 0.0 – 100.0
    speed: float = 0.0           # bytes/s
    eta: float = 0.0             # segundos
    downloaded_bytes: float = 0.0
    total_bytes: float = 0.0

    # Controle interno
    _future: Optional[Future] = field(default=None, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Motor de download
# ---------------------------------------------------------------------------

class DownloadEngine:
    """
    Gerencia a fila de downloads e executa cada item em threads separadas.
    Thread-safe: todos os callbacks são chamados a partir das threads de worker,
    mas são seguros para enfileirar atualizações na UI via after().
    """

    def __init__(self, db: Database):
        self.db = db
        self._items: list[DownloadItem] = []
        self._lock = threading.Lock()
        self._paused = threading.Event()
        self._paused.set()  # Não pausado inicialmente
        self._stop_flag = threading.Event()

        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False

        # Callbacks registráveis pela UI
        self.on_item_update: Optional[Callable[[DownloadItem], None]] = None
        self.on_all_done: Optional[Callable[[], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

        # Verificar / baixar FFmpeg
        self._ffmpeg_path: Optional[str] = None
        self._ffprobe_path: Optional[str] = None
        self._artist_dir_cache: dict[str, Path] = {}
        self._ensure_ffmpeg()

    # -----------------------------------------------------------------------
    # FFmpeg
    # -----------------------------------------------------------------------

    def _ensure_ffmpeg(self):
        """Garante que ffmpeg e ffprobe estejam disponíveis para conversão."""
        ffmpeg_path = get_ffmpeg_path()
        ffprobe_path = get_ffprobe_path()

        if ffmpeg_path and ffprobe_path:
            self._ffmpeg_path = shutil.which(ffmpeg_path) or ffmpeg_path
            self._ffprobe_path = shutil.which(ffprobe_path) or ffprobe_path
            self._inject_ffmpeg_into_path()
            self._log(f"FFmpeg: {self._ffmpeg_path}")
            self._log(f"FFprobe: {self._ffprobe_path}")
            return

        self._log("FFmpeg/FFprobe não encontrados. Iniciando download automático...")
        success = download_ffmpeg(progress_callback=self._log)
        if success:
            self._ffmpeg_path = get_ffmpeg_path()
            self._ffprobe_path = get_ffprobe_path()
            if self._ffmpeg_path and self._ffprobe_path:
                self._inject_ffmpeg_into_path()
                self._log(f"FFmpeg instalado: {self._ffmpeg_path}")
                self._log(f"FFprobe instalado: {self._ffprobe_path}")
            else:
                self._log("AVISO: FFmpeg/FFprobe não disponíveis após instalação automática.")
        else:
            self._log("AVISO: FFmpeg/FFprobe não disponíveis — conversão MP3 pode falhar.")

    def _inject_ffmpeg_into_path(self):
        """Adiciona a pasta de ffmpeg/ffprobe ao PATH do processo atual."""
        ffmpeg_dir = self._ffmpeg_location_dir()
        if not ffmpeg_dir:
            return

        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(os.pathsep) if current_path else []
        normalized = [p.lower() for p in path_parts]
        if ffmpeg_dir.lower() not in normalized:
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path if current_path else ffmpeg_dir

    def _ffmpeg_location_dir(self) -> Optional[str]:
        """Retorna diretório adequado para ffmpeg_location contendo ffmpeg+ffprobe."""
        candidates: list[Path] = []

        if self._ffmpeg_path:
            candidates.append(Path(self._ffmpeg_path).parent)
        if self._ffprobe_path:
            candidates.append(Path(self._ffprobe_path).parent)

        # Resolver caminhos relativos vindos de PATH (ex: "ffmpeg", "ffprobe")
        resolved_ffmpeg = shutil.which("ffmpeg") if self._ffmpeg_path and Path(self._ffmpeg_path).parent == Path(".") else None
        resolved_ffprobe = shutil.which("ffprobe") if self._ffprobe_path and Path(self._ffprobe_path).parent == Path(".") else None
        if resolved_ffmpeg:
            candidates.append(Path(resolved_ffmpeg).parent)
        if resolved_ffprobe:
            candidates.append(Path(resolved_ffprobe).parent)

        for d in candidates:
            ffmpeg_ok = (d / "ffmpeg").exists() or (d / "ffmpeg.exe").exists()
            ffprobe_ok = (d / "ffprobe").exists() or (d / "ffprobe.exe").exists()
            if ffmpeg_ok and ffprobe_ok:
                return str(d)

        if self._ffmpeg_path:
            return str(Path(self._ffmpeg_path).parent)
        return None

    # -----------------------------------------------------------------------
    # Gerenciamento de itens
    # -----------------------------------------------------------------------

    def add_items(self, urls: list[str], quality: str = None) -> list[DownloadItem]:
        """Adiciona URLs à fila. Retorna os itens criados."""
        q = quality or settings.quality
        added = []
        with self._lock:
            existing_urls = {item.url for item in self._items}
            for url in urls:
                if url in existing_urls:
                    continue
                item = DownloadItem(url=url, quality=q)
                item.db_id = self.db.add_download(url, quality=q, status="queued")
                self._items.append(item)
                added.append(item)
        return added

    def get_items(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._items)

    def clear_queue(self):
        """Remove itens que não estão em progresso ativo."""
        self.stop()
        with self._lock:
            self._items.clear()

    def remove_item(self, url: str):
        with self._lock:
            self._items = [i for i in self._items if i.url != url]

    # -----------------------------------------------------------------------
    # Controle de execução
    # -----------------------------------------------------------------------

    def start(self):
        """Inicia o processamento da fila."""
        if self._running:
            return
        self._running = True
        self._stop_flag.clear()
        self._paused.set()
        max_workers = settings.max_concurrent
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dl")

        # Thread de orquestração
        orchestrator = threading.Thread(target=self._orchestrate, daemon=True)
        orchestrator.start()

    def pause(self):
        """Pausa o processamento (downloads em andamento terminam o chunk atual)."""
        self._paused.clear()
        with self._lock:
            for item in self._items:
                if item.status == DownloadStatus.DOWNLOADING:
                    item.status = DownloadStatus.PAUSED
                    self._notify(item)

    def resume(self):
        """Retoma o processamento pausado."""
        with self._lock:
            for item in self._items:
                if item.status == DownloadStatus.PAUSED:
                    item.status = DownloadStatus.QUEUED
                    self._notify(item)
        self._paused.set()

    def stop(self):
        """Para todos os downloads."""
        self._stop_flag.set()
        self._paused.set()  # Desbloquear pause para poder parar
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    # -----------------------------------------------------------------------
    # Orquestrador
    # -----------------------------------------------------------------------

    def _orchestrate(self):
        """Loop principal: enfileira itens pendentes para o thread-pool."""
        futures: list[Future] = []

        while not self._stop_flag.is_set():
            self._paused.wait()  # Bloqueia se pausado

            if self._stop_flag.is_set():
                break

            with self._lock:
                queued = [i for i in self._items if i.status == DownloadStatus.QUEUED]

            if not queued:
                # Verificar se ainda existem itens em progresso
                with self._lock:
                    active = [
                        i for i in self._items
                        if i.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONVERTING)
                    ]
                if not active:
                    # Todos concluídos
                    break
                time.sleep(0.5)
                continue

            # Verificar vagas disponíveis
            with self._lock:
                active_count = sum(
                    1 for i in self._items
                    if i.status in (DownloadStatus.DOWNLOADING, DownloadStatus.CONVERTING)
                )
            slots = settings.max_concurrent - active_count

            for item in queued[:slots]:
                if self._stop_flag.is_set():
                    break
                if self._executor is None:
                    break
                with self._lock:
                    item.status = DownloadStatus.DOWNLOADING
                future = self._executor.submit(self._download_item, item)
                item._future = future
                futures.append(future)

            time.sleep(0.3)

        self._running = False
        # Notificar UI que tudo terminou
        if self.on_all_done:
            self.on_all_done()

    # -----------------------------------------------------------------------
    # Download de um item
    # -----------------------------------------------------------------------

    def _download_item(self, item: DownloadItem):
        """Executado em thread separada para cada item."""
        try:
            self._paused.wait()  # Respeitar pause

            # Sem ffmpeg/ffprobe não há conversão para MP3.
            if not self._ffmpeg_path or not self._ffprobe_path:
                raise RuntimeError(
                    "FFmpeg/FFprobe não encontrados. Instale com: brew install ffmpeg "
                    "(macOS) ou inclua ffmpeg.exe no build do Windows."
                )

            # --- Verificar duplicata por URL ---
            if self.db.is_duplicate_by_url(item.url):
                item.status = DownloadStatus.SKIPPED
                item.error_msg = "Música já existe (URL duplicada)"
                self.db.mark_skipped(item.db_id, item.error_msg)
                self._log(f"[SKIP] {item.url} — já baixado anteriormente.")
                self._notify(item)
                return

            output_dir = Path(settings.output_folder)
            output_dir.mkdir(parents=True, exist_ok=True)

            ffmpeg_loc = self._ffmpeg_location_dir()

            # Extrair metadados com retry automático para erros de certificado no macOS.
            info, ssl_compat_mode = self._extract_info_with_fallback(item, output_dir, ffmpeg_loc)

            # Pode ser uma playlist
            entries = info.get("entries") or [info]

            if info.get("extractor_key") == "YoutubeTab" and info.get("id"):
                self._log(f"Playlist detectada: {info.get('id')} ({len(entries)} vídeos)")

            success_count = 0
            skipped_count = 0
            error_count = 0

            for entry in entries:
                if self._stop_flag.is_set():
                    break
                self._paused.wait()
                if not entry:
                    continue
                try:
                    self._process_entry(entry, item, output_dir, ffmpeg_loc, ssl_compat_mode)
                    if item.status == DownloadStatus.SUCCESS:
                        success_count += 1
                    elif item.status == DownloadStatus.SKIPPED:
                        skipped_count += 1
                    elif item.status == DownloadStatus.ERROR:
                        error_count += 1
                except Exception as entry_error:
                    # Em playlists, não interromper o lote inteiro por erro de uma faixa.
                    error_count += 1
                    item.status = DownloadStatus.ERROR
                    item.error_msg = str(entry_error)[:500]
                    self._notify(item)
                    self._log(f"[ERRO] Falha em item da playlist: {entry_error}")
                    continue

            # Status final explícito para não deixar a UI presa em estado intermediário.
            if len(entries) > 1:
                if success_count > 0:
                    item.status = DownloadStatus.SUCCESS
                    item.progress = 100.0
                elif skipped_count > 0 and error_count == 0:
                    item.status = DownloadStatus.SKIPPED
                    item.progress = 100.0
                elif error_count > 0:
                    item.status = DownloadStatus.ERROR
                    item.error_msg = item.error_msg or "Falha ao converter/baixar itens da playlist"
                self._notify(item)

        except Exception as e:
            error_str = str(e)
            if ("ffmpeg" in error_str.lower() or "ffprobe" in error_str.lower()) and "not found" in error_str.lower():
                error_str = (
                    "FFmpeg/FFprobe não encontrados. No macOS instale com: brew install ffmpeg"
                )
            item.status = DownloadStatus.ERROR
            item.error_msg = error_str[:500]
            self.db.mark_error(item.db_id, error_str)
            self._log(f"[ERRO] {item.url} — {error_str}")
            self._notify(item)

    def _extract_info_with_fallback(self, item: DownloadItem, output_dir: Path, ffmpeg_loc) -> tuple[dict, bool]:
        """
        Extrai metadados do vídeo/playlist.
        Se detectar erro SSL de certificado, tenta novamente com verificação desativada.
        Retorna: (info, ssl_compat_mode)
        """
        ydl_opts = self._build_ydl_opts(
            item,
            output_dir,
            ffmpeg_loc,
            disable_cert_check=False,
            ignore_errors=True,
            extract_flat=True,
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(item.url, download=False)
        except Exception as e:
            msg = str(e)
            if self._is_ssl_cert_error(msg):
                self._log("Erro SSL detectado. Tentando modo compatibilidade de certificado...")
                ydl_opts_ssl = self._build_ydl_opts(
                    item,
                    output_dir,
                    ffmpeg_loc,
                    disable_cert_check=True,
                    ignore_errors=True,
                    extract_flat=True,
                )
                with yt_dlp.YoutubeDL(ydl_opts_ssl) as ydl:
                    info = ydl.extract_info(item.url, download=False)
                self._log("Modo compatibilidade SSL ativo para este download.")
                if info is None:
                    raise RuntimeError("Não foi possível obter informações do vídeo.")
                return info, True
            raise

        if info is None:
            # Em playlists (youtube:tab) com ignoreerrors, falhas SSL podem retornar None sem exceção.
            self._log("Nenhum metadado retornado. Tentando modo compatibilidade SSL...")
            ydl_opts_ssl = self._build_ydl_opts(
                item,
                output_dir,
                ffmpeg_loc,
                disable_cert_check=True,
                ignore_errors=True,
                extract_flat=True,
            )
            with yt_dlp.YoutubeDL(ydl_opts_ssl) as ydl:
                info_ssl = ydl.extract_info(item.url, download=False)
            if info_ssl is None:
                raise RuntimeError("Não foi possível obter informações do vídeo/playlist.")
            self._log("Modo compatibilidade SSL ativo para este download.")
            return info_ssl, True
        return info, False

    @staticmethod
    def _is_ssl_cert_error(message: str) -> bool:
        lower = message.lower()
        markers = (
            "certificate_verify_failed",
            "unable to get local issuer certificate",
            "ssl:",
        )
        return any(m in lower for m in markers)

    @staticmethod
    def _is_unavailable_video_error(message: str) -> bool:
        lower = (message or "").lower()
        markers = (
            "private video",
            "video unavailable",
            "this video is unavailable",
            "sign in if you've been granted access",
            "deleted video",
            "premieres in",
            "members-only",
        )
        return any(m in lower for m in markers)

    def _process_entry(self, entry: dict, item: DownloadItem, output_dir: Path, ffmpeg_loc, ssl_compat_mode: bool):
        """Processa uma entrada individual (vídeo) dentro de uma playlist."""
        raw_title = entry.get("title", "Desconhecido")
        raw_title_lower = (raw_title or "").strip().lower()

        if raw_title_lower in ("private video", "deleted video"):
            item.status = DownloadStatus.SKIPPED
            item.error_msg = f"Item indisponível na playlist: {raw_title}"
            self.db.mark_skipped(item.db_id, item.error_msg)
            self._log(f"[SKIP] {raw_title} — item indisponível.")
            self._notify(item)
            return

        artist, track = parse_artist_title(raw_title)
        thumbnail = entry.get("thumbnail", "")

        # Normalizar artista para evitar várias pastas por pequenas variações.
        folder_artist = canonical_artist_name(artist)

        item.title = track
        item.artist = folder_artist
        item.thumbnail_url = thumbnail

        # --- Criar pasta do artista ---
        artist_dir = self._resolve_artist_dir(output_dir, folder_artist)
        artist_dir.mkdir(parents=True, exist_ok=True)

        safe_track = sanitize_filename(track)
        expected_file = artist_dir / f"{safe_track}.mp3"

        # --- Verificar duplicata por caminho ---
        if expected_file.exists() or self.db.is_duplicate_by_filepath(str(expected_file)):
            item.status = DownloadStatus.SKIPPED
            item.error_msg = "Música já existe"
            item.filepath = str(expected_file)
            self.db.mark_skipped(item.db_id, "Arquivo já existe")
            self._log(f"[SKIP] {raw_title} — arquivo já existe.")
            self._notify(item)
            return

        # Atualizar BD com metadados
        self.db.update_download(item.db_id, title=track, artist=folder_artist,
                                 filename=f"{safe_track}.mp3",
                                 filepath=str(expected_file))

        # --- Opções de download refinadas para esta entrada ---
        # Usar safe_track como nome do arquivo para ter correspondência garantida
        # (%(title)s pode ter caracteres diferentes dos usados na busca posterior)
        output_template = str(artist_dir / f"{safe_track}.%(ext)s")

        ydl_opts_entry = self._build_ydl_opts(
            item,
            output_dir,
            ffmpeg_loc,
            disable_cert_check=ssl_compat_mode,
        )
        ydl_opts_entry["outtmpl"] = output_template

        item.status = DownloadStatus.DOWNLOADING
        self._notify(item)

        target_url = self._entry_download_url(entry, item.url)
        try:
            with yt_dlp.YoutubeDL(ydl_opts_entry) as ydl2:
                ydl2.download([target_url])
        except DownloadError as e:
            msg = str(e)
            if self._is_unavailable_video_error(msg):
                item.status = DownloadStatus.SKIPPED
                item.error_msg = "Vídeo indisponível/privado na playlist"
                self.db.mark_skipped(item.db_id, item.error_msg)
                self._log(f"[SKIP] {raw_title} — vídeo indisponível/privado.")
                self._notify(item)
                return
            raise

        downloaded = self._find_downloaded_file(artist_dir, raw_title, safe_track)

        if downloaded and downloaded.exists():
            if downloaded.suffix.lower() != ".mp3":
                item.status = DownloadStatus.CONVERTING
                self._notify(item)
                self._convert_to_mp3(downloaded, expected_file, item.quality or settings.quality)
                downloaded.unlink(missing_ok=True)
            elif str(downloaded) != str(expected_file):
                downloaded.rename(expected_file)

            item.filepath = str(expected_file)

            # Verificação de hash
            file_hash = ""
            if settings.use_hash_check:
                file_hash = compute_file_hash(str(expected_file))
                if self.db.is_duplicate_by_hash(file_hash):
                    expected_file.unlink(missing_ok=True)
                    item.status = DownloadStatus.SKIPPED
                    item.error_msg = "Música já existe (hash duplicado)"
                    self.db.mark_skipped(item.db_id, item.error_msg)
                    self._notify(item)
                    return

            item.status = DownloadStatus.SUCCESS
            item.progress = 100.0
            self.db.mark_success(item.db_id, str(expected_file), file_hash)
            self._log(f"[OK] {folder_artist} - {track} salvo em {expected_file}")
        else:
            item.status = DownloadStatus.ERROR
            item.error_msg = "Arquivo não encontrado após download"
            self.db.mark_error(item.db_id, item.error_msg)
            self._log(f"[ERRO] {raw_title} — arquivo não encontrado após download")

        self._notify(item)

    def _resolve_artist_dir(self, output_dir: Path, artist_name: str) -> Path:
        """
        Resolve a pasta do artista reutilizando diretórios já existentes
        com o mesmo identificador canônico.
        """
        artist_name = sanitize_filename(artist_name or "Desconhecido")
        key = artist_folder_id(artist_name)

        cached = self._artist_dir_cache.get(key)
        if cached and cached.exists():
            return cached

        preferred = output_dir / artist_name
        if preferred.exists():
            self._artist_dir_cache[key] = preferred
            return preferred

        for existing in output_dir.iterdir():
            if not existing.is_dir():
                continue
            if artist_folder_id(existing.name) == key:
                self._artist_dir_cache[key] = existing
                return existing

        self._artist_dir_cache[key] = preferred
        return preferred

    @staticmethod
    def _entry_download_url(entry: dict, fallback_url: str) -> str:
        """
        Resolve a URL final para baixar uma entrada de playlist.
        Algumas entradas trazem apenas ID no campo url.
        """
        if entry.get("webpage_url"):
            return entry["webpage_url"]

        entry_url = entry.get("url")
        if isinstance(entry_url, str) and entry_url.startswith("http"):
            return entry_url

        video_id = entry.get("id")
        if isinstance(video_id, str) and video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

        return fallback_url

    def _find_downloaded_file(self, artist_dir: Path, raw_title: str, safe_track: str) -> Optional[Path]:
        """Tenta localizar o arquivo MP3 recém-baixado na pasta do artista."""
        # Tentar nome exato sanitizado primeiro
        candidate = artist_dir / f"{safe_track}.mp3"
        if candidate.exists():
            return candidate

        # Tentar pelo título original sanitizado
        raw_safe = sanitize_filename(raw_title)
        candidate2 = artist_dir / f"{raw_safe}.mp3"
        if candidate2.exists():
            return candidate2

        # Buscar qualquer .mp3 criado recentemente (últimos 60s)
        now = time.time()
        for f in artist_dir.glob("*.mp3"):
            if now - f.stat().st_mtime < 60:
                return f

        return None
        # Tentar nome exato sanitizado primeiro (caso padrão com o novo template)
        candidate = artist_dir / f"{safe_track}.mp3"
        if candidate.exists():
            return candidate

        # Tentar pelo título original sanitizado (fallback para títulos alterados pelo yt-dlp)
        raw_safe = sanitize_filename(raw_title)
        candidate2 = artist_dir / f"{raw_safe}.mp3"
        if candidate2.exists():
            return candidate2

        # Buscar qualquer .mp3 criado recentemente (últimos 5 minutos)
        now = time.time()
        recent = None
        for f in artist_dir.glob("*.mp3"):
            age = now - f.stat().st_mtime
            if age < 300:
                if recent is None or f.stat().st_mtime > recent.stat().st_mtime:
                    recent = f
        if recent:
            return recent

        # Último recurso: qualquer arquivo de áudio na pasta (sem limite de tempo)
        for ext in ("*.mp3", "*.m4a", "*.webm", "*.ogg"):
            for f in artist_dir.glob(ext):
                return f

        return None

    def _convert_to_mp3(self, source_file: Path, output_file: Path, quality: str):
        """Converte o arquivo baixado para MP3 usando ffmpeg diretamente."""
        if not self._ffmpeg_path:
            raise RuntimeError("FFmpeg não encontrado para conversão.")

        output_file.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg_exe = self._ffmpeg_path
        if ffmpeg_exe in ("ffmpeg", "ffmpeg.exe"):
            ffmpeg_exe = shutil.which("ffmpeg") or ffmpeg_exe

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i",
            str(source_file),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{quality}k",
            str(output_file),
        ]

        env = os.environ.copy()
        ffmpeg_dir = self._ffmpeg_location_dir()
        if ffmpeg_dir:
            env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        if result.returncode != 0 or not output_file.exists():
            error_output = (result.stderr or result.stdout or "Erro desconhecido do ffmpeg").strip()
            raise RuntimeError(f"Falha ao converter para MP3: {error_output[:500]}")

    # -----------------------------------------------------------------------
    # Opções do yt-dlp
    # -----------------------------------------------------------------------

    def _build_ydl_opts(
        self,
        item: DownloadItem,
        output_dir: Path,
        ffmpeg_loc,
        disable_cert_check: bool = False,
        ignore_errors: bool = False,
        extract_flat: bool = False,
    ) -> dict:
        """Constrói o dicionário de opções do yt-dlp."""
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(uploader)s - %(title)s.%(ext)s"),
            # A conversão para MP3 é feita manualmente pelo app após o download.
            # Isso evita dependência do postprocess interno do yt-dlp/ffprobe.
            "writethumbnail": False,
            "quiet": True,
            "no_warnings": False,
            "noplaylist": False,   # Aceitar playlists
            "progress_hooks": [self._make_progress_hook(item)],
            "ignoreerrors": ignore_errors,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "extract_flat": "in_playlist" if extract_flat else False,
            # Streams HLS/m3u8 funcionam melhor via ffmpeg; evita erros do tipo
            # "m3u download detected" quando o downloader nativo entra em ação.
            "hls_prefer_native": False,
            "external_downloader": "ffmpeg",
        }

        if ffmpeg_loc:
            opts["ffmpeg_location"] = ffmpeg_loc

        node_path = shutil.which("node")
        if node_path:
            # Evita warning de runtime JS ausente em versões recentes do yt-dlp.
            opts["js_runtimes"] = {"node": {"path": node_path}}

        if disable_cert_check:
            opts["nocheckcertificate"] = True

        return opts

    def _make_progress_hook(self, item: DownloadItem) -> Callable:
        """Cria um hook de progresso vinculado ao item."""
        def hook(d: dict):
            status = d.get("status")
            if status == "downloading":
                downloaded = d.get("downloaded_bytes", 0) or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0

                item.downloaded_bytes = downloaded
                item.total_bytes = total
                item.speed = speed
                item.eta = eta
                item.status = DownloadStatus.DOWNLOADING

                if total > 0:
                    item.progress = min(downloaded / total * 100, 99.0)

                self._notify(item)

            elif status == "finished":
                item.progress = 99.0
                item.status = DownloadStatus.CONVERTING
                self._notify(item)

            elif status == "error":
                item.status = DownloadStatus.ERROR
                item.error_msg = str(d.get("error", "Erro desconhecido"))
                self._notify(item)

        return hook

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _notify(self, item: DownloadItem):
        """Chama o callback de atualização da UI (thread-safe)."""
        if self.on_item_update:
            try:
                self.on_item_update(item)
            except Exception as e:
                logger.debug("Erro no callback on_item_update: %s", e)

    def _log(self, msg: str):
        logger.info(msg)
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Estatísticas em tempo real
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Retorna contadores rápidos sobre o estado atual da fila."""
        with self._lock:
            items = list(self._items)
        return {
            "total":       len(items),
            "queued":      sum(1 for i in items if i.status == DownloadStatus.QUEUED),
            "downloading": sum(1 for i in items if i.status in (
                DownloadStatus.DOWNLOADING, DownloadStatus.CONVERTING)),
            "success":     sum(1 for i in items if i.status == DownloadStatus.SUCCESS),
            "error":       sum(1 for i in items if i.status == DownloadStatus.ERROR),
            "skipped":     sum(1 for i in items if i.status == DownloadStatus.SKIPPED),
            "speed":       sum(i.speed for i in items if i.status == DownloadStatus.DOWNLOADING),
        }
