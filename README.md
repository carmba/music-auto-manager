# Music Auto Manager

Aplicativo desktop para Windows que baixa músicas do YouTube em MP3 automaticamente.

---

## Funcionalidades

- ✅ Download de vídeos, playlists, Shorts e links `youtu.be`
- ✅ Conversão automática para MP3 (128 / 192 / 320 kbps)
- ✅ Organização automática em `/Musicas/<Artista>/Música.mp3`
- ✅ Detecção de duplicatas por URL, caminho e hash
- ✅ Histórico completo em SQLite
- ✅ Interface moderna tema escuro (estilo Spotify)
- ✅ Downloads paralelos sem travar a interface
- ✅ Thumbnail embutida no MP3
- ✅ Drag & Drop de links
- ✅ Botão abrir pasta do artista
- ✅ Download automático do FFmpeg se não encontrado
- ✅ Log detalhado em `logs.txt`
- ✅ Configurações persistentes (pasta, qualidade, tema, idioma)
- ✅ Suporte PT / ES
- ✅ Geração de `.exe` via PyInstaller

---

## Instalação (desenvolvimento no Mac/Linux)

```bash
cd music_auto_manager
pip install -r requirements.txt
python main.py
```

---

## Build para Windows (.exe)

### Windows (via CMD):

```bat
build.bat
```

O `build.bat` agora baixa automaticamente `ffmpeg.exe` e `ffprobe.exe` para a pasta `ffmpeg_bin/` e embute tudo dentro do executável final.

### Ou manualmente via PyInstaller:

```bat
pip install -r requirements.txt
pyinstaller build_windows.spec
```

O executável será gerado em `dist/MusicAutoManager.exe`.

## Build de instalador profissional (Windows)

Para instalar em `C:\Program Files\Music Auto Manager` e criar atalho no desktop,
gere um instalador com Inno Setup.

### Pré-requisito

Instale o Inno Setup 6:

- https://jrsoftware.org/isdl.php

### Gerar instalador (recomendado)

```bat
build_installer.bat
```

Saída:

- `dist/MusicAutoManager-Setup.exe`

Esse instalador:

- instala em `C:\Program Files\Music Auto Manager`
- cria atalho no menu iniciar
- oferece opção de criar atalho na área de trabalho
- adiciona desinstalador

### Script do instalador

- `installer_windows.iss`

Se quiser trocar versão exibida no instalador, ajuste `MyAppVersion` nesse arquivo.

### Distribuição profissional

O `.exe` gerado no Windows já sai com:

- interface completa
- dependências Python empacotadas
- `ffmpeg.exe` embutido
- `ffprobe.exe` embutido

Assim, o usuário final não precisa instalar FFmpeg separadamente.

---

## Atualização sem reinstalar (Windows)

O app agora possui sistema de atualização por manifesto remoto.

### Como configurar

1. Publique um arquivo JSON baseado em `update_manifest.example.json`
2. Informe a URL desse JSON na aba **Configurações > Atualizações**
3. Publique o novo `MusicAutoManager.exe` na URL de download indicada no manifesto

### Exemplo de manifesto

```json
{
  "version": "1.0.1",
  "notes": "Correções e melhorias",
  "windows": {
    "url": "https://seu-dominio.com/downloads/MusicAutoManager.exe"
  }
}
```

### Fluxo de atualização

- O usuário clica em **VERIFICAR ATUALIZAÇÃO**
- Se houver nova versão, clica em **ATUALIZAR AGORA**
- No `.exe` do Windows, o app baixa o novo executável, fecha e reinicia já atualizado

> Observação: em ambiente de desenvolvimento (Python no macOS/Linux), o botão abre apenas o link de download no navegador.

---

## Estrutura do projeto

```
music_auto_manager/
├── main.py           # Ponto de entrada
├── ui.py             # Interface gráfica (CustomTkinter)
├── downloader.py     # Motor de download (yt-dlp + threads)
├── database.py       # SQLite — histórico e duplicatas
├── settings.py       # Configurações + tema + i18n
├── utils.py          # Sanitização, parsing, FFmpeg, helpers
├── assets/
│   └── icon.ico      # Ícone do app (colocar aqui)
├── requirements.txt
├── build_windows.spec
├── build.bat
├── build_installer.bat
├── installer_windows.iss
└── README.md
```

---

## Dependências principais

| Pacote          | Uso                     |
| --------------- | ----------------------- |
| `customtkinter` | Interface moderna       |
| `yt-dlp`        | Download do YouTube     |
| `Pillow`        | Thumbnails              |
| `tkinterdnd2`   | Drag & Drop             |
| `pyinstaller`   | Gerar .exe              |
| `sqlite3`       | Banco de dados (stdlib) |

---

## Configurações disponíveis

- **Pasta de destino** — onde salvar as músicas
- **Qualidade MP3** — 128 / 192 / 320 kbps
- **Tema** — Escuro / Claro
- **Idioma** — Português / Español
- **Downloads simultâneos** — 1 a 10
- **Baixar thumbnail** — embute capa no MP3
- **Verificar hash** — detecta duplicatas por conteúdo
- **Iniciar automático** — começa ao adicionar links

---

## Logs

Arquivo `logs.txt` criado automaticamente com:

- Data e hora
- Link baixado
- Status (sucesso / erro / duplicado)
- Mensagem de erro (quando aplicável)

---

## Ícone personalizado

Para usar um ícone personalizado:

1. Coloque o arquivo `icon.ico` em `assets/`
2. Execute o build normalmente

Sites para criar `.ico`: [favicon.io](https://favicon.io), [convertio.co](https://convertio.co)
