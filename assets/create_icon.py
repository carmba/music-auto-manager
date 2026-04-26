"""
assets/create_icon.py — Script auxiliar para gerar um icon.ico básico
Execute uma vez no Mac para criar o ícone antes do build no Windows.
Requer: pip install Pillow
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo circular verde (estilo Spotify)
    draw.ellipse([4, 4, size - 4, size - 4], fill="#1db954")

    # Nota musical ♪ no centro
    try:
        font = ImageFont.truetype("arial.ttf", 130)
    except Exception:
        font = ImageFont.load_default()

    text = "♪"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2 - 10
    draw.text((x, y), text, fill="white", font=font)

    # Salvar como ICO com múltiplos tamanhos
    output = os.path.join(os.path.dirname(__file__), "icon.ico")
    img.save(output, format="ICO", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print(f"Ícone criado: {output}")

if __name__ == "__main__":
    create_icon()
