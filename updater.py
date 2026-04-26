"""
updater.py — Sistema simples de atualização para o Music Auto Manager.

Fluxo:
1) Verifica manifesto JSON remoto (versão/download).
2) Compara com a versão atual.
3) Em Windows (.exe), baixa o novo executável e agenda substituição no reinício.
"""

import json
import os
import re
import sys
import tempfile
import subprocess
from pathlib import Path
from urllib.request import urlopen, urlretrieve
from urllib.error import URLError, HTTPError
from typing import Optional


def _version_to_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", value or "")
    if not nums:
        return (0,)
    return tuple(int(n) for n in nums)


def compare_versions(a: str, b: str) -> int:
    """
    Compara versões em formato semver simples.
    Retorna 1 se a>b, 0 se iguais, -1 se a<b.
    """
    va = list(_version_to_tuple(a))
    vb = list(_version_to_tuple(b))
    max_len = max(len(va), len(vb))
    va += [0] * (max_len - len(va))
    vb += [0] * (max_len - len(vb))

    if va > vb:
        return 1
    if va < vb:
        return -1
    return 0


def check_for_update(current_version: str, manifest_url: str, timeout: int = 12) -> tuple[Optional[dict], Optional[str]]:
    """
    Verifica atualização no manifesto remoto.

    Manifesto esperado (exemplo):
    {
      "version": "1.1.0",
      "notes": "Correcoes",
      "windows": {
        "url": "https://seuservidor/MusicAutoManager.exe"
      }
    }

    Retorna (info, error):
    - info: dict com available/latest_version/download_url/notes
    - error: mensagem de erro ou None
    """
    if not manifest_url:
        return None, "URL de manifesto não configurada."

    try:
        with urlopen(manifest_url, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
    except (HTTPError, URLError) as e:
        return None, f"Falha ao consultar servidor de atualização: {e}"
    except json.JSONDecodeError as e:
        return None, f"Manifesto inválido (JSON): {e}"
    except Exception as e:
        return None, f"Erro ao verificar atualização: {e}"

    latest = str(data.get("version", "")).strip()
    notes = str(data.get("notes", "")).strip()

    win = data.get("windows") or {}
    download_url = win.get("url") or data.get("download_url")
    if download_url:
        download_url = str(download_url).strip()

    if not latest:
        return None, "Manifesto sem campo 'version'."

    is_available = compare_versions(latest, current_version) > 0

    info = {
        "available": is_available,
        "latest_version": latest,
        "current_version": current_version,
        "download_url": download_url,
        "notes": notes,
    }
    return info, None


def download_update_exe(download_url: str, app_name: str = "MusicAutoManager") -> tuple[Optional[Path], Optional[str]]:
    """Baixa o novo .exe para pasta temporária e retorna seu caminho."""
    if not download_url:
        return None, "URL de download não informada no manifesto."

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="mam_update_"))
        dest = temp_dir / f"{app_name}_new.exe"
        urlretrieve(download_url, dest)
        if not dest.exists() or dest.stat().st_size <= 0:
            return None, "Arquivo de atualização vazio ou inválido."
        return dest, None
    except Exception as e:
        return None, f"Falha no download da atualização: {e}"


def can_self_update_windows() -> bool:
    """Retorna True se o app está rodando como .exe no Windows."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def schedule_windows_exe_swap(new_exe: Path, current_exe: Optional[Path] = None) -> tuple[bool, Optional[str]]:
    """
    Agenda troca do executável atual por novo .exe.
    Cria um .bat temporário que espera o app fechar, substitui e reinicia.
    """
    try:
        if not can_self_update_windows():
            return False, "Auto-update só está disponível no .exe do Windows."

        current = Path(current_exe) if current_exe else Path(sys.executable)
        if not current.exists():
            return False, "Executável atual não encontrado."
        if not new_exe.exists():
            return False, "Novo executável não encontrado."

        bat_path = Path(tempfile.mkdtemp(prefix="mam_swap_")) / "apply_update.bat"

        bat_content = f"""@echo off
setlocal
timeout /t 2 /nobreak >nul
:retry
move /Y \"{new_exe}\" \"{current}\" >nul 2>&1
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto retry
)
start \"\" \"{current}\"
del \"%~f0\"
"""
        bat_path.write_text(bat_content, encoding="utf-8")

        subprocess.Popen(["cmd", "/c", str(bat_path)],
                         creationflags=0x08000000)  # CREATE_NO_WINDOW
        return True, None
    except Exception as e:
        return False, f"Falha ao aplicar atualização: {e}"
