"""
ui.py — Interface gráfica do Music Auto Manager
Construída com CustomTkinter — tema escuro estilo Spotify.
Totalmente não-bloqueante: usa after() para atualizações da UI.
"""

import os
import sys
import threading
import subprocess
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.filedialog as filedialog
import io
import logging
import webbrowser
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from settings import settings, t
from downloader import DownloadEngine, DownloadItem, DownloadStatus
from database import Database
from utils import extract_urls_from_text, format_speed, format_eta, format_bytes
from updater import (
    check_for_update,
    download_update_exe,
    can_self_update_windows,
    schedule_windows_exe_swap,
)
from app_meta import APP_VERSION

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes de layout
# ─────────────────────────────────────────────────────────────────────────────

FONT_TITLE    = ("Segoe UI", 22, "bold")
FONT_HEADER   = ("Segoe UI", 13, "bold")
FONT_BODY     = ("Segoe UI", 11)
FONT_SMALL    = ("Segoe UI", 10)
FONT_MONO     = ("Consolas", 10)
CORNER_RADIUS = 12
PAD           = 10

# ─────────────────────────────────────────────────────────────────────────────
# Classe principal da janela
# ─────────────────────────────────────────────────────────────────────────────

class MusicAutoManagerApp(ctk.CTk):

    def __init__(self, db: Database, engine: DownloadEngine):
        super().__init__()

        self.db = db
        self.engine = engine
        self.colors = settings.get_colors()

        # Registrar callbacks do motor
        self.engine.on_item_update = self._on_item_update
        self.engine.on_all_done    = self._on_all_done
        self.engine.on_log         = self._on_log

        # Mapa de widgets de progresso por URL
        self._item_rows: dict[str, "_ItemRow"] = {}
        self._update_info: Optional[dict] = None
        self._update_busy = False

        self._setup_ctk_theme()
        self._build_window()
        self._build_ui()

        # Suporte a drag-and-drop (Win32 / compatível)
        self._setup_dnd()

        # Atualizar stats a cada segundo
        self.after(1000, self._tick_stats)

        # Checagem automática de atualização (não bloqueante)
        self.after(1500, self._auto_check_updates)

    # ─────────────────────────────────────────────────────────────────────
    # Tema
    # ─────────────────────────────────────────────────────────────────────

    def _setup_ctk_theme(self):
        ctk.set_appearance_mode("dark" if settings.theme == "dark" else "light")
        ctk.set_default_color_theme("green")

    # ─────────────────────────────────────────────────────────────────────
    # Janela
    # ─────────────────────────────────────────────────────────────────────

    def _build_window(self):
        self.title(t("app_title"))
        self.geometry("1100x760")
        self.minsize(900, 620)
        self.configure(fg_color=self.colors["bg"])

        # Ícone — tenta carregar icon.ico se existir
        icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # Layout principal
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        c = self.colors

        # ── Header ───────────────────────────────────────────────────────
        self._header = ctk.CTkFrame(self, fg_color=c["bg_sidebar"], corner_radius=0, height=64)
        self._header.pack(fill="x", side="top")
        self._header.pack_propagate(False)

        ctk.CTkLabel(
            self._header,
            text="🎵  " + t("app_title"),
            font=FONT_TITLE,
            text_color=c["accent"],
        ).pack(side="left", padx=24, pady=14)

        # Badge de status global
        self._lbl_global_status = ctk.CTkLabel(
            self._header,
            text="",
            font=FONT_SMALL,
            text_color=c["text_dim"],
        )
        self._lbl_global_status.pack(side="right", padx=20)

        # ── Tabs (notebook) ───────────────────────────────────────────────
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=c["bg"],
            segmented_button_fg_color=c["bg_card"],
            segmented_button_selected_color=c["accent"],
            segmented_button_selected_hover_color=c["accent_hover"],
            segmented_button_unselected_color=c["bg_card"],
            segmented_button_unselected_hover_color=c["bg_sidebar"],
            text_color=c["text"],
            corner_radius=CORNER_RADIUS,
        )
        self._tabs.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        for tab_key in ("tab_download", "tab_history", "tab_settings"):
            self._tabs.add(t(tab_key))

        self._build_tab_download()
        self._build_tab_history()
        self._build_tab_settings()

    # ─────────────────────────────────────────────────────────────────────
    # Aba 1 — Downloads
    # ─────────────────────────────────────────────────────────────────────

    def _build_tab_download(self):
        tab = self._tabs.tab(t("tab_download"))
        tab.configure(fg_color=self.colors["bg"])
        c = self.colors

        # ── Painel esquerdo (entrada) ─────────────────────────────────────
        left = ctk.CTkFrame(tab, fg_color=c["bg_card"], corner_radius=CORNER_RADIUS)
        left.pack(side="left", fill="y", padx=(0, 6), pady=0)
        left.pack_propagate(False)
        left.configure(width=340)

        ctk.CTkLabel(left, text=f"📋  {t('links_input_title')}", font=FONT_HEADER,
                     text_color=c["text_title"]).pack(anchor="w", padx=14, pady=(14, 4))

        # Área de texto para links
        self._txt_links = ctk.CTkTextbox(
            left,
            font=FONT_MONO,
            fg_color=c["bg_input"],
            text_color=c["text"],
            border_color=c["border"],
            border_width=1,
            corner_radius=8,
            wrap="none",
            height=200,
        )
        self._txt_links.pack(fill="x", padx=10, pady=(0, 8))
        self._txt_links.insert("1.0", t("paste_links"))
        self._txt_links.bind("<FocusIn>", self._clear_placeholder)
        self._txt_links.bind("<Control-v>", lambda e: self.after(50, self._auto_add_if_valid))

        # Seletor de qualidade
        quality_frame = ctk.CTkFrame(left, fg_color="transparent")
        quality_frame.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(quality_frame, text=t("mp3_quality_label"), font=FONT_SMALL,
                     text_color=c["text_dim"]).pack(side="left")
        self._quality_var = tk.StringVar(value=settings.quality)
        ctk.CTkOptionMenu(
            quality_frame,
            values=["128", "192", "320"],
            variable=self._quality_var,
            fg_color=c["bg_input"],
            button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            dropdown_fg_color=c["bg_card"],
            text_color=c["text"],
            font=FONT_SMALL,
            width=80,
        ).pack(side="right")

        # Botão ADICIONAR
        self._btn_add = ctk.CTkButton(
            left,
            text=t("btn_add"),
            font=FONT_HEADER,
            fg_color=c["accent2"],
            hover_color="#6366f1",
            corner_radius=CORNER_RADIUS,
            height=40,
            command=self._add_links,
        )
        self._btn_add.pack(fill="x", padx=10, pady=(0, 6))

        # Separador
        ctk.CTkFrame(left, fg_color=c["border"], height=1).pack(fill="x", padx=10, pady=4)

        # Botões de controle
        self._btn_start = ctk.CTkButton(
            left, text=t("btn_start"),
            font=FONT_HEADER,
            fg_color=c["accent"],
            hover_color=c["accent_hover"],
            corner_radius=CORNER_RADIUS,
            height=44,
            command=self._start_downloads,
        )
        self._btn_start.pack(fill="x", padx=10, pady=(4, 4))

        self._btn_pause = ctk.CTkButton(
            left, text=t("btn_pause"),
            font=FONT_BODY,
            fg_color=c["warning"],
            hover_color="#e67e22",
            corner_radius=CORNER_RADIUS,
            height=36,
            command=self._toggle_pause,
        )
        self._btn_pause.pack(fill="x", padx=10, pady=(0, 4))

        self._btn_clear = ctk.CTkButton(
            left, text=t("btn_clear"),
            font=FONT_BODY,
            fg_color=c["danger"],
            hover_color="#c0392b",
            corner_radius=CORNER_RADIUS,
            height=36,
            command=self._clear_queue,
        )
        self._btn_clear.pack(fill="x", padx=10, pady=(0, 4))

        self._btn_open = ctk.CTkButton(
            left, text=t("btn_open_folder"),
            font=FONT_BODY,
            fg_color=c["bg_sidebar"],
            hover_color=c["border"],
            corner_radius=CORNER_RADIUS,
            height=34,
            command=self._open_output_folder,
        )
        self._btn_open.pack(fill="x", padx=10, pady=(0, 10))

        # ── Stats rápidas ─────────────────────────────────────────────────
        self._stats_frame = ctk.CTkFrame(left, fg_color=c["bg_sidebar"], corner_radius=8)
        self._stats_frame.pack(fill="x", padx=10, pady=(0, 10))

        stats_labels = [
            ("completed", f"✅ {t('completed')}", "0"),
            ("queue",     f"⏳ {t('queue')}",    "0"),
            ("errors",    f"❌ {t('errors')}",   "0"),
            ("speed",     f"⚡ {t('speed')}",    "0 KB/s"),
        ]
        self._stat_vars: dict[str, tk.StringVar] = {}
        for key, label, initial in stats_labels:
            row = ctk.CTkFrame(self._stats_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(row, text=label, font=FONT_SMALL, text_color=c["text_dim"],
                         width=110, anchor="w").pack(side="left")
            var = tk.StringVar(value=initial)
            self._stat_vars[key] = var
            ctk.CTkLabel(row, textvariable=var, font=FONT_SMALL,
                         text_color=c["text"]).pack(side="right")

        # ── Painel direito (lista de downloads) ───────────────────────────
        right = ctk.CTkFrame(tab, fg_color=c["bg_card"], corner_radius=CORNER_RADIUS)
        right.pack(side="right", fill="both", expand=True)

        # Cabeçalho da lista
        list_header = ctk.CTkFrame(right, fg_color=c["bg_sidebar"], corner_radius=0, height=36)
        list_header.pack(fill="x", padx=0, pady=0)
        list_header.pack_propagate(False)
        ctk.CTkLabel(list_header, text=t("downloads_list_title"),
                     font=FONT_HEADER, text_color=c["text_title"]).pack(side="left", padx=12)
        self._lbl_count = ctk.CTkLabel(list_header, text=self._format_links_count(0),
                                        font=FONT_SMALL, text_color=c["text_dim"])
        self._lbl_count.pack(side="right", padx=12)

        # Área scrollável
        self._scroll = ctk.CTkScrollableFrame(
            right,
            fg_color=c["bg_card"],
            scrollbar_button_color=c["scrollbar"],
            scrollbar_button_hover_color=c["accent"],
        )
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Barra de progresso global
        prog_frame = ctk.CTkFrame(right, fg_color=c["bg_sidebar"], corner_radius=0, height=52)
        prog_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        prog_frame.pack_propagate(False)

        ctk.CTkLabel(prog_frame, text=t("global_progress"),
                     font=FONT_SMALL, text_color=c["text_dim"]).pack(side="left", padx=12)
        self._global_progress = ctk.CTkProgressBar(
            prog_frame,
            fg_color=c["progress_bg"],
            progress_color=c["accent"],
            corner_radius=6,
            height=14,
        )
        self._global_progress.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=18)
        self._global_progress.set(0)

        self._lbl_global_pct = ctk.CTkLabel(prog_frame, text="0%",
                                              font=FONT_SMALL, text_color=c["text"])
        self._lbl_global_pct.pack(side="right", padx=12)

    # ─────────────────────────────────────────────────────────────────────
    # Aba 2 — Histórico
    # ─────────────────────────────────────────────────────────────────────

    def _build_tab_history(self):
        tab = self._tabs.tab(t("tab_history"))
        tab.configure(fg_color=self.colors["bg"])
        c = self.colors

        # Estatísticas no topo
        stats_row = ctk.CTkFrame(tab, fg_color=c["bg_card"], corner_radius=CORNER_RADIUS, height=80)
        stats_row.pack(fill="x", padx=0, pady=(0, 8))
        stats_row.pack_propagate(False)

        stat_defs = [
            ("today",   f"📅 {t('today')}",     "0"),
            ("total",   f"📦 {t('total')}",     "0"),
            ("errors",  f"❌ {t('errors')}",    "0"),
            ("skipped", f"🔁 {t('skipped')}",   "0"),
        ]
        self._hist_stat_vars: dict[str, tk.StringVar] = {}
        for key, label, initial in stat_defs:
            col = ctk.CTkFrame(stats_row, fg_color=c["bg_sidebar"], corner_radius=8)
            col.pack(side="left", fill="y", expand=True, padx=6, pady=8)
            var = tk.StringVar(value=initial)
            self._hist_stat_vars[key] = var
            ctk.CTkLabel(col, text=label, font=FONT_SMALL, text_color=c["text_dim"]).pack(pady=(6, 0))
            ctk.CTkLabel(col, textvariable=var, font=("Segoe UI", 20, "bold"),
                         text_color=c["accent"]).pack(pady=(0, 6))

        # Botão limpar histórico
        ctk.CTkButton(
            tab, text=t("btn_clear_history"),
            font=FONT_BODY,
            fg_color=c["danger"],
            hover_color="#c0392b",
            corner_radius=CORNER_RADIUS,
            height=34,
            command=self._clear_history,
        ).pack(fill="x", padx=0, pady=(0, 8))

        # Botão atualizar
        ctk.CTkButton(
            tab, text=f"🔄  {t('btn_refresh_history')}",
            font=FONT_BODY,
            fg_color=c["bg_sidebar"],
            hover_color=c["border"],
            corner_radius=CORNER_RADIUS,
            height=32,
            command=self._refresh_history,
        ).pack(fill="x", padx=0, pady=(0, 6))

        # Tabela de histórico — usando CTkScrollableFrame + grid
        self._hist_scroll = ctk.CTkScrollableFrame(
            tab,
            fg_color=c["bg_card"],
            scrollbar_button_color=c["scrollbar"],
        )
        self._hist_scroll.pack(fill="both", expand=True)

        # Cabeçalhos
        headers = [
            t("history_col_artist"),
            t("history_col_title"),
            t("history_col_status"),
            t("history_col_quality"),
            t("history_col_date"),
        ]
        widths   = [160, 240, 90, 80, 150]
        for col_i, (h, w) in enumerate(zip(headers, widths)):
            lbl = ctk.CTkLabel(self._hist_scroll, text=h, font=FONT_HEADER,
                               text_color=c["accent"], width=w, anchor="w")
            lbl.grid(row=0, column=col_i, padx=4, pady=4, sticky="w")

        self._hist_rows_start = 1
        self._history_row_widgets: list[list] = []
        self._refresh_history()

    # ─────────────────────────────────────────────────────────────────────
    # Aba 3 — Configurações
    # ─────────────────────────────────────────────────────────────────────

    def _build_tab_settings(self):
        tab = self._tabs.tab(t("tab_settings"))
        tab.configure(fg_color=self.colors["bg"])
        c = self.colors

        scroll = ctk.CTkScrollableFrame(tab, fg_color=c["bg_card"], corner_radius=CORNER_RADIUS)
        scroll.pack(fill="both", expand=True)

        def section(title):
            ctk.CTkLabel(scroll, text=title, font=FONT_HEADER, text_color=c["accent"]).pack(
                anchor="w", padx=16, pady=(18, 4))
            ctk.CTkFrame(scroll, fg_color=c["border"], height=1).pack(fill="x", padx=16, pady=(0, 8))

        def row(label, widget_factory):
            f = ctk.CTkFrame(scroll, fg_color="transparent")
            f.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(f, text=label, font=FONT_BODY, text_color=c["text"],
                         width=200, anchor="w").pack(side="left")
            w = widget_factory(f)
            w.pack(side="right")
            return w

        # ── Geral ─────────────────────────────────────────────────────────
        section("📁  " + t("output_folder"))

        folder_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        folder_frame.pack(fill="x", padx=16, pady=(0, 8))
        self._var_folder = tk.StringVar(value=settings.output_folder)
        ctk.CTkEntry(folder_frame, textvariable=self._var_folder,
                     font=FONT_BODY, fg_color=c["bg_input"],
                     text_color=c["text"], border_color=c["border"]).pack(
                         side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(folder_frame, text="...", width=40,
                      fg_color=c["accent2"], hover_color="#6366f1",
                      command=self._browse_folder).pack(side="right")

        # ── Qualidade ─────────────────────────────────────────────────────
        section("🎵  " + t("quality"))
        self._var_quality_cfg = tk.StringVar(value=settings.quality)
        row(t("quality"), lambda p: ctk.CTkOptionMenu(
            p, values=["128", "192", "320"],
            variable=self._var_quality_cfg,
            fg_color=c["bg_input"], button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            dropdown_fg_color=c["bg_card"], text_color=c["text"],
            width=100,
        ))

        # ── Aparência ─────────────────────────────────────────────────────
        section(f"🎨  {t('appearance')}")
        self._var_theme = tk.StringVar(value=settings.theme)
        row(t("theme"), lambda p: ctk.CTkOptionMenu(
            p, values=["dark", "light"],
            variable=self._var_theme,
            fg_color=c["bg_input"], button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            dropdown_fg_color=c["bg_card"], text_color=c["text"],
            width=100,
        ))

        self._var_lang = tk.StringVar(value=settings.language)
        row(t("language"), lambda p: ctk.CTkOptionMenu(
            p, values=["pt", "es"],
            variable=self._var_lang,
            fg_color=c["bg_input"], button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            dropdown_fg_color=c["bg_card"], text_color=c["text"],
            width=100,
        ))

        # ── Download ──────────────────────────────────────────────────────
        section(f"⚙️  {t('download_section')}")

        self._var_thumb = tk.BooleanVar(value=settings.download_thumbnail)
        row(t("download_thumb"), lambda p: ctk.CTkCheckBox(
            p, text="", variable=self._var_thumb,
            fg_color=c["accent"], hover_color=c["accent_hover"],
        ))

        self._var_auto = tk.BooleanVar(value=settings.auto_start)
        row(t("auto_start"), lambda p: ctk.CTkCheckBox(
            p, text="", variable=self._var_auto,
            fg_color=c["accent"], hover_color=c["accent_hover"],
        ))

        self._var_hash = tk.BooleanVar(value=settings.use_hash_check)
        row(t("use_hash"), lambda p: ctk.CTkCheckBox(
            p, text="", variable=self._var_hash,
            fg_color=c["accent"], hover_color=c["accent_hover"],
        ))

        self._var_concurrent = tk.IntVar(value=settings.max_concurrent)
        row(t("max_concurrent"), lambda p: ctk.CTkSlider(
            p, from_=1, to=10, number_of_steps=9,
            variable=self._var_concurrent,
            button_color=c["accent"],
            button_hover_color=c["accent_hover"],
            progress_color=c["accent"],
            width=160,
        ))

        # ── Atualizações ────────────────────────────────────────────────
        section("⬆  " + t("updates"))

        self._var_manifest = tk.StringVar(value=settings.update_manifest_url)
        manifest_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        manifest_frame.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            manifest_frame,
            text=t("update_manifest"),
            font=FONT_BODY,
            text_color=c["text"],
            width=200,
            anchor="w",
        ).pack(side="left")
        ctk.CTkEntry(
            manifest_frame,
            textvariable=self._var_manifest,
            font=FONT_SMALL,
            fg_color=c["bg_input"],
            text_color=c["text"],
            border_color=c["border"],
        ).pack(side="right", fill="x", expand=True)

        self._var_auto_updates = tk.BooleanVar(value=settings.auto_check_updates)
        row(t("auto_check_updates"), lambda p: ctk.CTkCheckBox(
            p, text="", variable=self._var_auto_updates,
            fg_color=c["accent"], hover_color=c["accent_hover"],
        ))

        self._lbl_version = ctk.CTkLabel(
            scroll,
            text=t("current_version").format(version=APP_VERSION),
            font=FONT_SMALL,
            text_color=c["text_dim"],
        )
        self._lbl_version.pack(anchor="w", padx=16, pady=(2, 2))

        self._var_update_status = tk.StringVar(value="")
        self._lbl_update_status = ctk.CTkLabel(
            scroll,
            textvariable=self._var_update_status,
            font=FONT_SMALL,
            text_color=c["text_dim"],
            wraplength=760,
            justify="left",
        )
        self._lbl_update_status.pack(anchor="w", padx=16, pady=(0, 8))

        btns = ctk.CTkFrame(scroll, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 8))

        self._btn_check_update = ctk.CTkButton(
            btns,
            text=t("btn_check_updates"),
            font=FONT_BODY,
            fg_color=c["accent2"],
            hover_color="#6366f1",
            corner_radius=CORNER_RADIUS,
            height=36,
            command=lambda: self._check_updates(silent=False),
        )
        self._btn_check_update.pack(side="left")

        self._btn_apply_update = ctk.CTkButton(
            btns,
            text=t("btn_update_now"),
            font=FONT_BODY,
            fg_color=c["accent"],
            hover_color=c["accent_hover"],
            corner_radius=CORNER_RADIUS,
            height=36,
            state="disabled",
            command=self._apply_update,
        )
        self._btn_apply_update.pack(side="left", padx=(8, 0))

        # ── Salvar ────────────────────────────────────────────────────────
        ctk.CTkButton(
            scroll, text=t("btn_save_settings"),
            font=FONT_HEADER,
            fg_color=c["accent"],
            hover_color=c["accent_hover"],
            corner_radius=CORNER_RADIUS,
            height=44,
            command=self._save_settings,
        ).pack(fill="x", padx=16, pady=20)

    # ─────────────────────────────────────────────────────────────────────
    # Lógica dos botões
    # ─────────────────────────────────────────────────────────────────────

    def _clear_placeholder(self, event=None):
        current = self._txt_links.get("1.0", "end-1c").strip()
        if current == t("paste_links"):
            self._txt_links.delete("1.0", "end")

    def _auto_add_if_valid(self):
        """Após colar, adiciona automaticamente se todos os links forem válidos."""
        pass  # Apenas limpa — usuário clica em Adicionar

    def _add_links(self):
        raw = self._txt_links.get("1.0", "end-1c").strip()
        if not raw or raw == t("paste_links"):
            messagebox.showinfo(t("app_title"), t("no_links"))
            return

        urls = extract_urls_from_text(raw)
        if not urls:
            messagebox.showwarning(t("app_title"), t("invalid_youtube_urls"))
            return

        quality = self._quality_var.get()
        added = self.engine.add_items(urls, quality=quality)

        for item in added:
            self._add_item_row(item)

        self._txt_links.delete("1.0", "end")
        self._update_count()

        # Auto-start se configurado
        if settings.auto_start and not self.engine.is_running:
            self._start_downloads()

    def _start_downloads(self):
        items = self.engine.get_items()
        if not items:
            messagebox.showinfo(t("app_title"), t("no_links"))
            return
        if not self.engine.is_running:
            self.engine.start()
            self._btn_start.configure(state="disabled")
            self._btn_pause.configure(state="normal")

    def _toggle_pause(self):
        if self.engine.is_paused:
            self.engine.resume()
            self._btn_pause.configure(text=t("btn_pause"))
        else:
            self.engine.pause()
            self._btn_pause.configure(text=t("btn_resume"))

    def _clear_queue(self):
        if messagebox.askyesno(t("app_title"), t("clear_queue_confirm")):
            self.engine.clear_queue()
            for w in self._item_rows.values():
                w.destroy()
            self._item_rows.clear()
            self._update_count()
            self._global_progress.set(0)
            self._lbl_global_pct.configure(text="0%")
            self._btn_start.configure(state="normal")
            self._btn_pause.configure(text=t("btn_pause"))

    def _open_output_folder(self):
        folder = Path(settings.output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _browse_folder(self):
        path = filedialog.askdirectory(initialdir=settings.output_folder)
        if path:
            self._var_folder.set(path)

    def _save_settings(self):
        prev_lang = settings.language
        prev_theme = settings.theme

        settings.output_folder       = self._var_folder.get()
        settings.quality             = self._var_quality_cfg.get()
        settings.theme               = self._var_theme.get()
        settings.language            = self._var_lang.get()
        settings.download_thumbnail  = self._var_thumb.get()
        settings.auto_start          = self._var_auto.get()
        settings.use_hash_check      = self._var_hash.get()
        settings.max_concurrent      = self._var_concurrent.get()
        settings.update_manifest_url = self._var_manifest.get()
        settings.auto_check_updates  = self._var_auto_updates.get()
        settings.save()

        ctk.set_appearance_mode("dark" if settings.theme == "dark" else "light")
        if settings.language != prev_lang or settings.theme != prev_theme:
            self._reload_ui_runtime()
        messagebox.showinfo(t("app_title"), t("settings_saved"))

    def _reload_ui_runtime(self):
        """Reconstrói a interface para aplicar idioma/tema sem reiniciar o app."""
        # Preservar conteúdo digitado no campo de links (se existir)
        current_links_text = ""
        try:
            if hasattr(self, "_txt_links") and self._txt_links.winfo_exists():
                current_links_text = self._txt_links.get("1.0", "end-1c")
        except Exception:
            current_links_text = ""

        self.colors = settings.get_colors()
        self.configure(fg_color=self.colors["bg"])
        self.title(t("app_title"))

        # Remover widgets atuais (header/tabs/painéis)
        for child in self.winfo_children():
            child.destroy()

        # Limpar cache de linhas e reconstruir layout completo
        self._item_rows.clear()
        self._build_ui()

        # Restaurar texto digitado na caixa de links
        if current_links_text and current_links_text.strip() and current_links_text != t("paste_links"):
            self._txt_links.delete("1.0", "end")
            self._txt_links.insert("1.0", current_links_text)

        # Recriar linhas da fila atual sem perder estado dos downloads
        for item in self.engine.get_items():
            self._add_item_row(item)
            self._update_item_ui(item)

        self._update_count()
        self._update_global_progress()

        if self.engine.is_running:
            self._btn_start.configure(state="disabled")
            self._btn_pause.configure(state="normal")
            self._btn_pause.configure(text=t("btn_resume") if self.engine.is_paused else t("btn_pause"))
        else:
            self._btn_start.configure(state="normal")

    def _auto_check_updates(self):
        if settings.auto_check_updates:
            self._check_updates(silent=True)

    def _check_updates(self, silent: bool = False):
        if self._update_busy:
            return

        manifest = self._var_manifest.get().strip()
        if not manifest:
            if not silent:
                messagebox.showwarning(t("app_title"), t("configure_manifest"))
            return

        self._update_busy = True
        self._btn_check_update.configure(state="disabled")
        self._btn_apply_update.configure(state="disabled")
        self._var_update_status.set(t("checking_updates"))

        def worker():
            info, err = check_for_update(APP_VERSION, manifest)
            self.after(0, lambda: self._on_check_updates_done(info, err, silent))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_updates_done(self, info: Optional[dict], err: Optional[str], silent: bool):
        self._update_busy = False
        self._btn_check_update.configure(state="normal")

        if err:
            self._update_info = None
            self._var_update_status.set(f"{t('status_error')}: {err}")
            if not silent:
                messagebox.showerror(t("app_title"), err)
            return

        if not info or not info.get("available"):
            self._update_info = None
            self._btn_apply_update.configure(state="disabled")
            self._var_update_status.set(t("up_to_date"))
            if not silent:
                messagebox.showinfo(t("app_title"), t("up_to_date"))
            return

        self._update_info = info
        latest = info.get("latest_version", "?")
        notes = (info.get("notes") or "").strip()
        status = f"{t('update_available')}: {latest}"
        if notes:
            status += f" | {notes}"
        self._var_update_status.set(status)
        self._btn_apply_update.configure(state="normal")

        if not silent:
            messagebox.showinfo(t("app_title"), status)

    def _apply_update(self):
        if self._update_busy:
            return
        if not self._update_info:
            messagebox.showwarning(t("app_title"), t("no_update_available"))
            return

        download_url = (self._update_info.get("download_url") or "").strip()
        if not download_url:
            messagebox.showerror(t("app_title"), t("manifest_without_download"))
            return

        if not can_self_update_windows():
            # Em ambiente de desenvolvimento/macOS: abrir link para download manual.
            webbrowser.open(download_url)
            self._var_update_status.set(t("update_link_opened"))
            return

        self._update_busy = True
        self._btn_check_update.configure(state="disabled")
        self._btn_apply_update.configure(state="disabled")
        self._var_update_status.set(t("updating"))

        def worker():
            new_exe, err = download_update_exe(download_url)
            if err:
                self.after(0, lambda: self._on_apply_update_done(False, err))
                return

            ok, err2 = schedule_windows_exe_swap(new_exe)
            if not ok:
                self.after(0, lambda: self._on_apply_update_done(False, err2 or "Falha ao aplicar atualização."))
                return

            self.after(0, lambda: self._on_apply_update_done(True, None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_update_done(self, success: bool, error: Optional[str]):
        self._update_busy = False
        self._btn_check_update.configure(state="normal")

        if not success:
            self._btn_apply_update.configure(state="normal" if self._update_info else "disabled")
            self._var_update_status.set(t("update_failed").format(error=error or "?"))
            messagebox.showerror(t("app_title"), error or t("update_failed_generic"))
            return

        self._var_update_status.set(t("update_ready_restarting"))
        messagebox.showinfo(t("app_title"), t("update_downloaded_restart"))
        self.destroy()

    def _clear_history(self):
        if messagebox.askyesno(t("app_title"), t("clear_history_confirm")):
            self.db.clear_history()
            self._refresh_history()

    def _refresh_history(self):
        c = self.colors
        # Remover linhas antigas
        for row_widgets in self._history_row_widgets:
            for w in row_widgets:
                w.destroy()
        self._history_row_widgets.clear()

        records = self.db.get_history(limit=300)
        status_colors = {
            "success": c["accent"],
            "error":   c["danger"],
            "skipped": c["warning"],
            "pending": c["text_dim"],
        }

        for r_idx, rec in enumerate(records):
            row_widgets = []
            bg = c["bg_card"] if r_idx % 2 == 0 else c["bg_sidebar"]
            values = [
                rec.get("artist", "?") or "?",
                rec.get("title", "?")  or "?",
                rec.get("status", "?"),
                rec.get("quality", "?") or "?",
                (rec.get("downloaded_at") or rec.get("created_at") or "—")[:16],
            ]
            widths = [160, 240, 90, 80, 150]
            grid_row = self._hist_rows_start + r_idx

            for col_i, (val, w) in enumerate(zip(values, widths)):
                text_color = status_colors.get(val, c["text"]) if col_i == 2 else c["text"]
                lbl = ctk.CTkLabel(
                    self._hist_scroll,
                    text=str(val)[:40],
                    font=FONT_SMALL,
                    text_color=text_color,
                    width=w,
                    anchor="w",
                )
                lbl.grid(row=grid_row, column=col_i, padx=4, pady=2, sticky="w")
                row_widgets.append(lbl)
            self._history_row_widgets.append(row_widgets)

        # Atualizar stats
        stats = self.db.get_stats()
        self._hist_stat_vars["today"].set(str(stats["today"]))
        self._hist_stat_vars["total"].set(str(stats["total"]))
        self._hist_stat_vars["errors"].set(str(stats["errors"]))
        self._hist_stat_vars["skipped"].set(str(stats["skipped"]))

    # ─────────────────────────────────────────────────────────────────────
    # Linha de item individual na lista
    # ─────────────────────────────────────────────────────────────────────

    def _add_item_row(self, item: DownloadItem):
        if item.url in self._item_rows:
            return
        row = _ItemRow(self._scroll, item, self.colors, on_open_artist=self._open_artist_folder)
        row.pack(fill="x", padx=4, pady=3)
        self._item_rows[item.url] = row

    # ─────────────────────────────────────────────────────────────────────
    # Callbacks do motor (chamados em threads de worker)
    # ─────────────────────────────────────────────────────────────────────

    def _on_item_update(self, item: DownloadItem):
        """Atualiza a UI de forma thread-safe via after()."""
        self.after(0, self._update_item_ui, item)

    def _update_item_ui(self, item: DownloadItem):
        if item.url not in self._item_rows:
            self._add_item_row(item)
        row = self._item_rows.get(item.url)
        if row:
            row.update_item(item)
        self._update_global_progress()

    def _on_all_done(self):
        """Chamado quando todos os downloads terminam."""
        self.after(0, self._show_done_popup)

    def _show_done_popup(self):
        self._btn_start.configure(state="normal")
        self._btn_pause.configure(text=t("btn_pause"))
        self._refresh_history()
        messagebox.showinfo(t("all_done_title"), t("all_done_msg"))

    def _on_log(self, msg: str):
        logger.info(msg)

    # ─────────────────────────────────────────────────────────────────────
    # Progresso global e estatísticas
    # ─────────────────────────────────────────────────────────────────────

    def _update_global_progress(self):
        items = self.engine.get_items()
        if not items:
            self._global_progress.set(0)
            self._lbl_global_pct.configure(text="0%")
            return
        total_pct = sum(i.progress for i in items)
        avg = total_pct / len(items)
        self._global_progress.set(avg / 100)
        self._lbl_global_pct.configure(text=f"{avg:.0f}%")

    def _update_count(self):
        n = len(self.engine.get_items())
        self._lbl_count.configure(text=self._format_links_count(n))

    def _format_links_count(self, n: int) -> str:
        if settings.language == "es":
            suffix = "enlace" if n == 1 else "enlaces"
        else:
            suffix = "link" if n == 1 else "links"
        return f"{n} {suffix}"

    def _tick_stats(self):
        """Atualiza o painel de stats a cada segundo."""
        stats = self.engine.get_stats()
        self._stat_vars["completed"].set(str(stats["success"]))
        self._stat_vars["queue"].set(str(stats["queued"]))
        self._stat_vars["errors"].set(str(stats["error"]))
        self._stat_vars["speed"].set(format_speed(stats["speed"]))

        # Status global no header
        if self.engine.is_running:
            active = stats["downloading"]
            if self.engine.is_paused:
                self._lbl_global_status.configure(text=t("header_paused"))
            elif active:
                self._lbl_global_status.configure(text=t("header_downloading").format(n=active))
            else:
                self._lbl_global_status.configure(text=t("status_idle"))
        else:
            done = stats["success"]
            if done:
                self._lbl_global_status.configure(text=t("header_done").format(n=done))
            else:
                self._lbl_global_status.configure(text="")

        self.after(1000, self._tick_stats)

    # ─────────────────────────────────────────────────────────────────────
    # Abrir pasta do artista
    # ─────────────────────────────────────────────────────────────────────

    def _open_artist_folder(self, artist: str):
        folder = Path(settings.output_folder) / artist
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    # ─────────────────────────────────────────────────────────────────────
    # Drag and Drop
    # ─────────────────────────────────────────────────────────────────────

    def _setup_dnd(self):
        """Tenta configurar drag-and-drop via tkinterdnd2 (opcional)."""
        try:
            from tkinterdnd2 import DND_TEXT, DND_FILES
            self.drop_target_register(DND_TEXT)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # tkinterdnd2 não disponível — silenciar

    def _on_drop(self, event):
        data = event.data.strip()
        if data:
            self._txt_links.delete("1.0", "end")
            self._txt_links.insert("1.0", data)
            self.after(100, self._add_links)


# ─────────────────────────────────────────────────────────────────────────────
# Widget de linha individual de item
# ─────────────────────────────────────────────────────────────────────────────

class _ItemRow(ctk.CTkFrame):
    """
    Representa uma linha na lista de downloads com:
    thumbnail, título/artista, barra de progresso, status, botão de pasta.
    """

    _STATUS_COLORS = {
        DownloadStatus.QUEUED:      "#888888",
        DownloadStatus.DOWNLOADING: "#1db954",
        DownloadStatus.CONVERTING:  "#f39c12",
        DownloadStatus.SUCCESS:     "#1db954",
        DownloadStatus.ERROR:       "#e74c3c",
        DownloadStatus.SKIPPED:     "#f39c12",
        DownloadStatus.PAUSED:      "#535bf2",
        DownloadStatus.CANCELLED:   "#888888",
    }

    def __init__(self, parent, item: DownloadItem, colors: dict, on_open_artist=None):
        super().__init__(parent, fg_color=colors["bg_sidebar"], corner_radius=10)
        self._item = item
        self._colors = colors
        self._on_open_artist = on_open_artist
        self._thumb_image = None

        self._build()
        self.update_item(item)

    def _build(self):
        c = self._colors

        # Thumbnail placeholder
        self._thumb_lbl = ctk.CTkLabel(self, text="🎵", width=52, height=52,
                                        fg_color=c["bg_card"], corner_radius=8,
                                        font=("Segoe UI", 22))
        self._thumb_lbl.pack(side="left", padx=(8, 6), pady=6)

        # Info central
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, pady=4)

        # Linha 1: artista — título
        self._lbl_title = ctk.CTkLabel(info, text=t("loading"), font=FONT_BODY,
                                        text_color=c["text_title"], anchor="w")
        self._lbl_title.pack(fill="x", padx=0)

        # Linha 2: URL truncada
        self._lbl_url = ctk.CTkLabel(info, text="", font=FONT_SMALL,
                                      text_color=c["text_dim"], anchor="w")
        self._lbl_url.pack(fill="x", padx=0)

        # Linha 3: barra de progresso + info de velocidade
        prog_row = ctk.CTkFrame(info, fg_color="transparent")
        prog_row.pack(fill="x", pady=(4, 0))

        self._progress_bar = ctk.CTkProgressBar(
            prog_row,
            fg_color=c["progress_bg"],
            progress_color=c["accent"],
            corner_radius=4,
            height=8,
        )
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._progress_bar.set(0)

        self._lbl_pct = ctk.CTkLabel(prog_row, text="0%", font=FONT_SMALL,
                                      text_color=c["text_dim"], width=36)
        self._lbl_pct.pack(side="left")

        # Linha 4: speed / eta
        meta_row = ctk.CTkFrame(info, fg_color="transparent")
        meta_row.pack(fill="x")
        self._lbl_speed = ctk.CTkLabel(meta_row, text="", font=FONT_SMALL,
                                        text_color=c["text_dim"])
        self._lbl_speed.pack(side="left")
        self._lbl_eta = ctk.CTkLabel(meta_row, text="", font=FONT_SMALL,
                                      text_color=c["text_dim"])
        self._lbl_eta.pack(side="right")

        # Status badge
        self._lbl_status = ctk.CTkLabel(self, text=t("queue"), font=FONT_SMALL,
                                         text_color=c["text_dim"], width=90)
        self._lbl_status.pack(side="right", padx=(0, 4))

        # Botão abrir pasta artista
        self._btn_folder = ctk.CTkButton(
            self, text="📂", width=32, height=32,
            fg_color=c["bg_card"],
            hover_color=c["border"],
            corner_radius=8,
            font=("Segoe UI", 14),
            command=self._open_artist_folder,
        )
        self._btn_folder.pack(side="right", padx=(0, 6))

    def update_item(self, item: DownloadItem):
        self._item = item
        c = self._colors

        # Título
        if item.artist and item.title:
            self._lbl_title.configure(text=f"{item.artist} — {item.title}")
        elif item.title:
            self._lbl_title.configure(text=item.title)
        else:
            short_url = item.url[:60] + ("..." if len(item.url) > 60 else "")
            self._lbl_title.configure(text=short_url)

        # URL
        short = item.url[:70] + ("..." if len(item.url) > 70 else "")
        self._lbl_url.configure(text=short)

        # Progresso
        pct = item.progress / 100
        self._progress_bar.set(max(0, min(pct, 1)))
        self._lbl_pct.configure(text=f"{item.progress:.0f}%")

        # Cor da barra por status
        color = self._STATUS_COLORS.get(item.status, c["accent"])
        self._progress_bar.configure(progress_color=color)

        # Velocidade / ETA
        if item.status == DownloadStatus.DOWNLOADING and item.speed > 0:
            self._lbl_speed.configure(text=f"⚡ {format_speed(item.speed)}")
            self._lbl_eta.configure(text=f"⏱ {format_eta(item.eta)}")
        else:
            self._lbl_speed.configure(text="")
            self._lbl_eta.configure(text="")

        # Status label
        status_labels = {
            DownloadStatus.QUEUED: t("queue"),
            DownloadStatus.DOWNLOADING: t("status_downloading"),
            DownloadStatus.CONVERTING: t("status_converting"),
            DownloadStatus.SUCCESS: t("status_done") + " ✅",
            DownloadStatus.ERROR: t("status_error") + " ❌",
            DownloadStatus.SKIPPED: t("status_skipped") + " ⚠️",
            DownloadStatus.PAUSED: t("status_paused"),
            DownloadStatus.CANCELLED: t("status_cancelled"),
        }
        status_txt = status_labels.get(item.status, item.status.value)
        if item.status == DownloadStatus.ERROR and item.error_msg:
            status_txt = f"{t('status_error')}: {item.error_msg[:30]}"
        self._lbl_status.configure(text=status_txt, text_color=color)

        # Thumbnail assíncrono (apenas quando disponível e não carregado)
        if item.thumbnail_url and self._thumb_image is None:
            threading.Thread(
                target=self._load_thumbnail,
                args=(item.thumbnail_url,),
                daemon=True
            ).start()

    def _load_thumbnail(self, url: str):
        """Baixa e exibe thumbnail em thread separada."""
        try:
            with urlopen(url, timeout=8) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).resize((52, 52), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(52, 52))
            self._thumb_image = ctk_img
            # Atualizar na thread da UI
            self.after(0, lambda: self._thumb_lbl.configure(image=ctk_img, text=""))
        except Exception:
            pass  # Falha silenciosa — placeholder permanece

    def _open_artist_folder(self):
        if self._on_open_artist and self._item.artist:
            self._on_open_artist(self._item.artist)
