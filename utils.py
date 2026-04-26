"""
utils.py — Utilitários gerais do Music Auto Manager
Funções auxiliares: sanitização, detecção de artista/título, FFmpeg, etc.
"""

import os
import re
import sys
import platform
import subprocess
import unicodedata
import zipfile
import tarfile
import urllib.request
import logging
from urllib.parse import parse_qs, urlparse
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sanitização de nomes de arquivo
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos de um nome de arquivo/pasta."""
    # Caracteres proibidos no Windows: \ / : * ? " < > |
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    # Remover caracteres de controle
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # Substituir múltiplos espaços por um único
    name = re.sub(r'\s+', ' ', name).strip()
    # Limitar comprimento
    if len(name) > 200:
        name = name[:200].strip()
    return name or "Desconhecido"


# ---------------------------------------------------------------------------
# Detecção de Artista / Título a partir do título do vídeo
# ---------------------------------------------------------------------------

# Padrões comuns: "Artista - Título", "Artista – Título", "Artista — Título"
_SEPARATOR_PATTERN = re.compile(r'\s*[-–—]\s*', re.UNICODE)

# Palavras que indicam que a parte antes do separador NÃO é um artista
_JUNK_PREFIXES = {
    'official', 'official video', 'official audio', 'lyrics', 'lyric video',
    'music video', 'mv', 'hd', 'hq', '4k', 'audio', 'video', 'letra',
    'clipe oficial', 'clipe', 'visualizer'
}

# Tags de sufixo a remover do título
_SUFFIX_TAGS = re.compile(
    r'\s*[\(\[\{]?\s*('
    r'official\s*(music\s*)?video|official\s*audio|official\s*lyric\s*video|'
    r'lyrics?\s*video|lyrics?|visualizer|hd|hq|4k|'
    r'clipe\s*oficial|letra\s*oficial|letra|clipe|'
    r'audio\s*oficial|live\s*performance|live|acoustic|'
    r'explicit|clean\s*version|radio\s*edit|extended\s*version|'
    r'feat\.?.*?|ft\.?.*?'
    r')\s*[\)\]\}]?\s*$',
    re.IGNORECASE | re.UNICODE
)

_ARTIST_SPLIT_PATTERN = re.compile(
    r'\s*(?:,|/|\\|\||\+|&|\bx\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b)\s*',
    re.IGNORECASE,
)


def parse_artist_title(raw_title: str) -> tuple[str, str]:
    """
    Tenta detectar (artista, título) a partir do título do vídeo do YouTube.
    
    Retorna:
        (artista, titulo) — ambos sanitizados.
        Se não conseguir separar, artista = "Desconhecido", titulo = título limpo.
    """
    # Limpar tags de sufixo
    title = _SUFFIX_TAGS.sub('', raw_title).strip()

    parts = _SEPARATOR_PATTERN.split(title, maxsplit=1)

    if len(parts) == 2:
        artist_candidate = parts[0].strip()
        track_candidate = parts[1].strip()
        # Rejeitar se o candidato a artista parecer uma tag genérica
        if artist_candidate.lower() not in _JUNK_PREFIXES and len(artist_candidate) >= 2:
            return sanitize_filename(artist_candidate), sanitize_filename(track_candidate)

    # Não conseguiu separar — título completo como nome da música
    return "Desconhecido", sanitize_filename(title or raw_title)


def canonical_artist_name(artist: str) -> str:
    """
    Retorna o nome canônico do artista para uso em pasta.
    Em colaborações, usa o primeiro artista para evitar múltiplas pastas
    para a mesma música por pequenas variações de escrita.
    """
    artist = sanitize_filename(artist or "Desconhecido")

    # Remover arroba de menção (@Artista)
    artist = artist.replace("@", " ").strip()

    # Pegar o primeiro artista quando houver colaborações
    parts = [p.strip() for p in _ARTIST_SPLIT_PATTERN.split(artist) if p.strip()]
    main_artist = parts[0] if parts else artist

    # Limpar conteúdo final entre parênteses em nomes do tipo "Artista (Oficial)"
    main_artist = re.sub(r'\s*[\(\[].*?[\)\]]\s*$', '', main_artist).strip()

    return sanitize_filename(main_artist or "Desconhecido")


def artist_folder_id(artist: str) -> str:
    """
    Gera um identificador estável para comparar pastas de artista
    ignorando acentos, pontuação e diferenças de caixa.
    """
    canonical = canonical_artist_name(artist).lower()
    canonical = unicodedata.normalize("NFKD", canonical)
    canonical = "".join(ch for ch in canonical if not unicodedata.combining(ch))
    canonical = re.sub(r'[^a-z0-9\s]', ' ', canonical)
    canonical = re.sub(r'\s+', ' ', canonical).strip()
    return canonical


# ---------------------------------------------------------------------------
# Localização do FFmpeg
# ---------------------------------------------------------------------------

def get_runtime_base_dir() -> Path:
    """
    Retorna o diretório base de recursos em runtime.

    - Em PyInstaller onefile, usa sys._MEIPASS (arquivos extraídos temporariamente)
    - Em app congelado onedir, usa a pasta do executável
    - Em desenvolvimento, usa a pasta do projeto
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)

    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent

    return Path(__file__).parent

def get_ffmpeg_dir() -> Path:
    """Retorna o diretório onde o FFmpeg será armazenado dentro do projeto."""
    return get_runtime_base_dir() / "ffmpeg_bin"


def _find_local_binary(candidates: list[str]) -> str | None:
    """Procura executável no diretório bundled e ao lado do .exe quando frozen."""
    search_dirs = [get_ffmpeg_dir()]

    if getattr(sys, 'frozen', False):
        exe_base = Path(sys.executable).parent
        search_dirs.extend(
            [
                exe_base / "ffmpeg_bin",
                exe_base / "_internal" / "ffmpeg_bin",
            ]
        )

    for base_dir in search_dirs:
        for name in candidates:
            path = base_dir / name
            if path.exists():
                return str(path)

    return None


def get_ffmpeg_path() -> str | None:
    """
    Retorna o caminho do executável ffmpeg, ou None se não encontrado.
    Verifica primeiro no diretório local, depois no PATH do sistema.
    """
    system = platform.system()

    # Nomes possíveis do executável
    candidates = ["ffmpeg.exe", "ffmpeg"] if system == "Windows" else ["ffmpeg"]

    # 1) Verificar no diretório bundled/local
    local_match = _find_local_binary(candidates)
    if local_match:
        return local_match

    # 2) Verificar no PATH do sistema
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        if result.returncode == 0:
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def get_ffprobe_path() -> str | None:
    """
    Retorna o caminho do executável ffprobe, ou None se não encontrado.
    Verifica primeiro no diretório local, depois no PATH do sistema.
    """
    system = platform.system()
    candidates = ["ffprobe.exe", "ffprobe"] if system == "Windows" else ["ffprobe"]

    local_match = _find_local_binary(candidates)
    if local_match:
        return local_match

    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if result.returncode == 0:
            return "ffprobe"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def download_ffmpeg(progress_callback=None) -> bool:
    """
    Baixa o FFmpeg automaticamente para o diretório local.
    progress_callback(msg: str) — chamado com mensagens de progresso.
    Retorna True se bem-sucedido.
    """
    system = platform.system()
    dest_dir = get_ffmpeg_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    def report(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    if system == "Windows":
        # URL do binário estático do FFmpeg para Windows (gyan.dev)
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = dest_dir / "ffmpeg.zip"
        report("Baixando FFmpeg para Windows...")
        try:
            def reporthook(block, block_size, total):
                if total > 0 and progress_callback:
                    pct = min(block * block_size * 100 // total, 100)
                    progress_callback(f"Baixando FFmpeg... {pct}%")

            urllib.request.urlretrieve(url, zip_path, reporthook=reporthook)
            report("Extraindo FFmpeg...")
            with zipfile.ZipFile(zip_path, 'r') as z:
                for member in z.namelist():
                    if member.endswith("ffmpeg.exe") or member.endswith("ffprobe.exe"):
                        data = z.read(member)
                        filename = Path(member).name
                        (dest_dir / filename).write_bytes(data)
            zip_path.unlink(missing_ok=True)
            report("FFmpeg instalado com sucesso!")
            return True
        except Exception as e:
            report(f"Erro ao baixar FFmpeg: {e}")
            return False

    elif system == "Darwin":
        # macOS — orientar via brew (não faz sentido fazer bundle para Mac se compilamos no Windows)
        report("No macOS, instale o FFmpeg via: brew install ffmpeg")
        return False

    else:
        report("Sistema não suportado para download automático do FFmpeg.")
        return False


# ---------------------------------------------------------------------------
# Formatar tamanho de bytes
# ---------------------------------------------------------------------------

def format_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    return f"{format_bytes(bytes_per_sec)}/s"


def format_eta(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:  # NaN
        return "?"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"


# ---------------------------------------------------------------------------
# Validação de URLs do YouTube
# ---------------------------------------------------------------------------

_YOUTUBE_URL_REGEX = re.compile(
    r'(?:(?:https?://)?(?:www\.|m\.)?)'
    r'(?:youtube\.com/(?:watch\?[^\s]+|playlist\?[^\s]+|shorts/[\w-]+)|youtu\.be/[\w-]+)',
    re.IGNORECASE,
)


def _cleanup_url(url: str) -> str:
    """Remove pontuações comuns que podem vir coladas ao final da URL."""
    return url.strip().rstrip('.,;:!?)\]}>\"\'')


def is_valid_youtube_url(url: str) -> bool:
    """Retorna True se a URL parece ser um link válido do YouTube."""
    url = normalize_url(_cleanup_url(url))
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if not any(h in host for h in ("youtube.com", "youtu.be")):
        return False

    if "youtu.be" in host:
        return bool(path.strip("/"))

    if path == "/watch":
        query = parse_qs(parsed.query)
        return bool(query.get("v"))

    if path == "/playlist":
        query = parse_qs(parsed.query)
        return bool(query.get("list"))

    if path.startswith("/shorts/"):
        return len(path.split("/")) >= 3

    return False


def normalize_url(url: str) -> str:
    """Garante que a URL tenha o esquema https://."""
    url = _cleanup_url(url)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_urls_from_text(text: str) -> list[str]:
    """
    Extrai todas as URLs válidas do YouTube de um bloco de texto (uma por linha ou separadas por espaço).
    """
    candidates = _YOUTUBE_URL_REGEX.findall(text or "")

    # Fallback para caso de uma URL por linha sem match no regex principal
    if not candidates:
        candidates = [line.strip() for line in (text or "").splitlines() if line.strip()]

    urls: list[str] = []
    seen: set[str] = set()

    for raw in candidates:
        normalized = normalize_url(raw)
        if is_valid_youtube_url(normalized) and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    return urls


# ---------------------------------------------------------------------------
# Setup de logging
# ---------------------------------------------------------------------------

def setup_logging(log_file: str = "logs.txt"):
    """Configura o sistema de logging para arquivo e console."""
    log_path = Path(log_file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )
