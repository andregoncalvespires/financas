import io

from fastapi import HTTPException
from PIL import Image, ImageOps

MAX_LADO = 1600


def preparar(dados: bytes) -> tuple[bytes, str, str]:
    """Normaliza o arquivo enviado: PDF passa direto; imagens são giradas conforme o EXIF, reduzidas e regravadas em JPEG
    (o que também remove metadados como GPS). Retorna (bytes, mime, extensão)."""
    if dados[:5] == b"%PDF-":
        return dados, "application/pdf", "pdf"
    try:
        img = Image.open(io.BytesIO(dados))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise HTTPException(415, "arquivo não reconhecido: envie uma foto (JPG/PNG/WebP) ou PDF")
    img.thumbnail((MAX_LADO, MAX_LADO))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue(), "image/jpeg", "jpg"
