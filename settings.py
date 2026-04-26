"""
settings.py — Configurações persistentes do Music Auto Manager
Salva/carrega preferências em JSON + expõe constantes de tema.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"

# ---------------------------------------------------------------------------
# Valores padrão
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "output_folder": str(Path.home() / "Musicas"),
    "quality": "192",           # 128 | 192 | 320
    "theme": "dark",            # dark | light
    "download_thumbnail": True,
    "auto_start": False,
    "language": "pt",           # pt | es
    "max_concurrent": 3,        # downloads simultâneos
    "use_hash_check": False,    # verificação por hash (mais lento)
    "update_manifest_url": "",  # URL JSON de atualização
    "auto_check_updates": True,
}

# ---------------------------------------------------------------------------
# Paleta de cores (estilo Spotify / dark-pro)
# ---------------------------------------------------------------------------

DARK_THEME = {
    "bg":            "#0f0f0f",
    "bg_card":       "#1a1a2e",
    "bg_sidebar":    "#16213e",
    "bg_input":      "#0d1117",
    "accent":        "#1db954",   # verde Spotify
    "accent_hover":  "#1ed760",
    "accent2":       "#535bf2",   # roxo indigo
    "danger":        "#e74c3c",
    "warning":       "#f39c12",
    "text":          "#e0e0e0",
    "text_dim":      "#888888",
    "text_title":    "#ffffff",
    "border":        "#2a2a3e",
    "progress_bg":   "#2a2a3e",
    "progress_fill": "#1db954",
    "scrollbar":     "#333355",
}

LIGHT_THEME = {
    "bg":            "#f4f4f4",
    "bg_card":       "#ffffff",
    "bg_sidebar":    "#e8e8f0",
    "bg_input":      "#ffffff",
    "accent":        "#1db954",
    "accent_hover":  "#17a349",
    "accent2":       "#4348e0",
    "danger":        "#c0392b",
    "warning":       "#d68910",
    "text":          "#1a1a2e",
    "text_dim":      "#666677",
    "text_title":    "#0a0a1a",
    "border":        "#dde1ef",
    "progress_bg":   "#dde1ef",
    "progress_fill": "#1db954",
    "scrollbar":     "#c0c0d0",
}


# ---------------------------------------------------------------------------
# Classe de configurações
# ---------------------------------------------------------------------------

class Settings:
    """Carrega, salva e fornece acesso tipado às configurações do aplicativo."""

    def __init__(self, path: str = SETTINGS_FILE):
        self._path = Path(path)
        self._data: dict = dict(DEFAULTS)
        self.load()

    # --- Persistência ---

    def load(self):
        """Carrega configurações do arquivo JSON. Usa padrões para chaves ausentes."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Mesclar com defaults para garantir chaves novas
                self._data = {**DEFAULTS, **loaded}
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Erro ao carregar configurações: %s — usando padrões.", e)
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            self.save()

    def save(self):
        """Salva as configurações atuais no arquivo JSON."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Erro ao salvar configurações: %s", e)

    # --- Getters / Setters genéricos ---

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def set_and_save(self, key: str, value):
        self.set(key, value)
        self.save()

    # --- Propriedades tipadas ---

    @property
    def output_folder(self) -> str:
        return self._data.get("output_folder", DEFAULTS["output_folder"])

    @output_folder.setter
    def output_folder(self, value: str):
        self._data["output_folder"] = value

    @property
    def quality(self) -> str:
        return self._data.get("quality", "192")

    @quality.setter
    def quality(self, value: str):
        if value in ("128", "192", "320"):
            self._data["quality"] = value

    @property
    def theme(self) -> str:
        return self._data.get("theme", "dark")

    @theme.setter
    def theme(self, value: str):
        if value in ("dark", "light"):
            self._data["theme"] = value

    @property
    def download_thumbnail(self) -> bool:
        return bool(self._data.get("download_thumbnail", True))

    @download_thumbnail.setter
    def download_thumbnail(self, value: bool):
        self._data["download_thumbnail"] = bool(value)

    @property
    def auto_start(self) -> bool:
        return bool(self._data.get("auto_start", False))

    @auto_start.setter
    def auto_start(self, value: bool):
        self._data["auto_start"] = bool(value)

    @property
    def language(self) -> str:
        return self._data.get("language", "pt")

    @language.setter
    def language(self, value: str):
        if value in ("pt", "es"):
            self._data["language"] = value

    @property
    def max_concurrent(self) -> int:
        return int(self._data.get("max_concurrent", 3))

    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self._data["max_concurrent"] = max(1, min(int(value), 10))

    @property
    def use_hash_check(self) -> bool:
        return bool(self._data.get("use_hash_check", False))

    @use_hash_check.setter
    def use_hash_check(self, value: bool):
        self._data["use_hash_check"] = bool(value)

    def get_colors(self) -> dict:
        """Retorna o dicionário de cores do tema atual."""
        return DARK_THEME if self.theme == "dark" else LIGHT_THEME

    @property
    def update_manifest_url(self) -> str:
        return str(self._data.get("update_manifest_url", "")).strip()

    @update_manifest_url.setter
    def update_manifest_url(self, value: str):
        self._data["update_manifest_url"] = str(value or "").strip()

    @property
    def auto_check_updates(self) -> bool:
        return bool(self._data.get("auto_check_updates", True))

    @auto_check_updates.setter
    def auto_check_updates(self, value: bool):
        self._data["auto_check_updates"] = bool(value)


# ---------------------------------------------------------------------------
# Instância global (importar em outros módulos)
# ---------------------------------------------------------------------------

settings = Settings()


# ---------------------------------------------------------------------------
# Strings de internacionalização (i18n) — PT e ES
# ---------------------------------------------------------------------------

_STRINGS = {
    "pt": {
        "app_title": "MUSIC AUTO MANAGER",
        "tab_download": "Downloads",
        "tab_history": "Histórico",
        "tab_settings": "Configurações",
        "links_input_title": "Cole seus links",
        "paste_links": "Cole os links do YouTube aqui (um por linha)...",
        "mp3_quality_label": "Qualidade MP3:",
        "downloads_list_title": "Lista de Downloads",
        "global_progress": "Progresso geral:",
        "btn_add": "ADICIONAR LINKS",
        "btn_start": "INICIAR DOWNLOAD",
        "btn_pause": "PAUSAR",
        "btn_resume": "CONTINUAR",
        "btn_clear": "LIMPAR LISTA",
        "btn_open_folder": "ABRIR PASTA",
        "status_idle": "Aguardando...",
        "status_downloading": "Baixando...",
        "status_paused": "Pausado",
        "status_done": "Concluído",
        "status_error": "Erro",
        "status_skipped": "Já existe",
        "status_converting": "Convertendo...",
        "already_exists": "Música já existe",
        "all_done_title": "Downloads concluídos!",
        "all_done_msg": "Todos os downloads foram concluídos com sucesso!",
        "no_links": "Nenhum link adicionado.",
        "invalid_url": "URL inválida ignorada",
        "downloading_ffmpeg": "Baixando FFmpeg...",
        "ffmpeg_ok": "FFmpeg encontrado.",
        "ffmpeg_missing": "FFmpeg não encontrado. Baixando automaticamente...",
        "settings_saved": "Configurações salvas!",
        "output_folder": "Pasta de destino",
        "quality": "Qualidade do MP3",
        "theme": "Tema",
        "dark": "Escuro",
        "light": "Claro",
        "download_thumb": "Baixar capa (thumbnail)",
        "auto_start": "Iniciar downloads automaticamente",
        "language": "Idioma",
        "max_concurrent": "Downloads simultâneos",
        "use_hash": "Verificar duplicatas por hash",
        "btn_save_settings": "SALVAR CONFIGURAÇÕES",
        "history_title": "Histórico de Downloads",
        "today": "Hoje",
        "total": "Total",
        "errors": "Erros",
        "skipped": "Repetidas",
        "btn_clear_history": "LIMPAR HISTÓRICO",
        "btn_refresh_history": "Atualizar",
        "history_col_artist": "Artista",
        "history_col_title": "Música",
        "history_col_status": "Status",
        "history_col_quality": "Qualidade",
        "history_col_date": "Data",
        "speed": "Velocidade",
        "eta": "Tempo restante",
        "completed": "Concluídos",
        "queue": "Na fila",
        "appearance": "Aparência",
        "download_section": "Download",
        "loading": "Carregando...",
        "status_cancelled": "Cancelado",
        "invalid_youtube_urls": "Nenhuma URL válida do YouTube encontrada.",
        "clear_queue_confirm": "Limpar toda a lista de downloads?",
        "clear_history_confirm": "Deseja apagar todo o histórico?",
        "updates": "Atualizações",
        "update_manifest": "URL do manifesto",
        "auto_check_updates": "Verificar atualização ao abrir",
        "current_version": "Versão atual: {version}",
        "btn_check_updates": "VERIFICAR ATUALIZAÇÃO",
        "btn_update_now": "ATUALIZAR AGORA",
        "checking_updates": "Verificando atualizações...",
        "up_to_date": "Você já está na versão mais recente.",
        "no_update_available": "Nenhuma atualização disponível no momento.",
        "configure_manifest": "Configure a URL do manifesto de atualização.",
        "manifest_without_download": "Manifesto sem URL de download para Windows.",
        "update_link_opened": "Link de atualização aberto no navegador.",
        "update_failed": "Erro na atualização: {error}",
        "update_failed_generic": "Falha ao atualizar.",
        "update_ready_restarting": "Atualização pronta. Reiniciando aplicativo...",
        "update_downloaded_restart": "Atualização baixada. O app será reiniciado para concluir.",
        "update_available": "Nova versão disponível",
        "updating": "Baixando atualização...",
        "header_paused": "⏸  Pausado",
        "header_downloading": "⬇  Baixando {n} arquivo(s)...",
        "header_done": "✅  {n} concluído(s)",
    },
    "es": {
        "app_title": "MUSIC AUTO MANAGER",
        "tab_download": "Descargas",
        "tab_history": "Historial",
        "tab_settings": "Ajustes",
        "links_input_title": "Pega tus enlaces",
        "paste_links": "Pega los enlaces de YouTube aquí (uno por línea)...",
        "mp3_quality_label": "Calidad MP3:",
        "downloads_list_title": "Lista de descargas",
        "global_progress": "Progreso general:",
        "btn_add": "AÑADIR ENLACES",
        "btn_start": "INICIAR DESCARGA",
        "btn_pause": "PAUSAR",
        "btn_resume": "CONTINUAR",
        "btn_clear": "LIMPIAR LISTA",
        "btn_open_folder": "ABRIR CARPETA",
        "status_idle": "Esperando...",
        "status_downloading": "Descargando...",
        "status_paused": "Pausado",
        "status_done": "Completado",
        "status_error": "Error",
        "status_skipped": "Ya existe",
        "status_converting": "Convirtiendo...",
        "already_exists": "La música ya existe",
        "all_done_title": "¡Descargas completadas!",
        "all_done_msg": "¡Todas las descargas se completaron con éxito!",
        "no_links": "Ningún enlace añadido.",
        "invalid_url": "URL inválida ignorada",
        "downloading_ffmpeg": "Descargando FFmpeg...",
        "ffmpeg_ok": "FFmpeg encontrado.",
        "ffmpeg_missing": "FFmpeg no encontrado. Descargando automáticamente...",
        "settings_saved": "¡Ajustes guardados!",
        "output_folder": "Carpeta de destino",
        "quality": "Calidad del MP3",
        "theme": "Tema",
        "dark": "Oscuro",
        "light": "Claro",
        "download_thumb": "Descargar portada (thumbnail)",
        "auto_start": "Iniciar descargas automáticamente",
        "language": "Idioma",
        "max_concurrent": "Descargas simultáneas",
        "use_hash": "Verificar duplicados por hash",
        "btn_save_settings": "GUARDAR AJUSTES",
        "history_title": "Historial de Descargas",
        "today": "Hoy",
        "total": "Total",
        "errors": "Errores",
        "skipped": "Repetidas",
        "btn_clear_history": "BORRAR HISTORIAL",
        "btn_refresh_history": "Actualizar",
        "history_col_artist": "Artista",
        "history_col_title": "Canción",
        "history_col_status": "Estado",
        "history_col_quality": "Calidad",
        "history_col_date": "Fecha",
        "speed": "Velocidad",
        "eta": "Tiempo restante",
        "completed": "Completados",
        "queue": "En cola",
        "appearance": "Apariencia",
        "download_section": "Descarga",
        "loading": "Cargando...",
        "status_cancelled": "Cancelado",
        "invalid_youtube_urls": "No se encontró ninguna URL válida de YouTube.",
        "clear_queue_confirm": "¿Limpiar toda la lista de descargas?",
        "clear_history_confirm": "¿Deseas borrar todo el historial?",
        "updates": "Actualizaciones",
        "update_manifest": "URL del manifiesto",
        "auto_check_updates": "Buscar actualización al iniciar",
        "current_version": "Versión actual: {version}",
        "btn_check_updates": "BUSCAR ACTUALIZACIÓN",
        "btn_update_now": "ACTUALIZAR AHORA",
        "checking_updates": "Buscando actualizaciones...",
        "up_to_date": "Ya tienes la versión más reciente.",
        "no_update_available": "No hay actualizaciones disponibles en este momento.",
        "configure_manifest": "Configura la URL del manifiesto de actualización.",
        "manifest_without_download": "Manifesto sin URL de descarga para Windows.",
        "update_link_opened": "Enlace de actualización abierto en el navegador.",
        "update_failed": "Error en la actualización: {error}",
        "update_failed_generic": "Fallo al actualizar.",
        "update_ready_restarting": "Actualización lista. Reiniciando la aplicación...",
        "update_downloaded_restart": "Actualización descargada. La app se reiniciará para finalizar.",
        "update_available": "Nueva versión disponible",
        "updating": "Descargando actualización...",
        "header_paused": "⏸  En pausa",
        "header_downloading": "⬇  Descargando {n} archivo(s)...",
        "header_done": "✅  {n} completado(s)",
    }
}


def t(key: str) -> str:
    """Retorna a string traduzida para o idioma atual."""
    lang = settings.language
    return _STRINGS.get(lang, _STRINGS["pt"]).get(key, key)
