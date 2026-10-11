"""Pictures for the page: a Pillow picture as a `data:` link (the page needs no file of its own for it)."""
import base64
import io


def picture(img, size=None):
    """`img` (Pillow) as a data: link, shrunk to fit `size` (width, height) if given; None for no picture.
    WebP keeps it small (a portrait is ~25 KB instead of ~200 KB as PNG); PNG where Pillow cannot write WebP."""
    if img is None:
        return None
    img = img.convert('RGBA')
    if size and (img.width > size[0] or img.height > size[1]):
        img = img.copy()
        img.thumbnail(size)
    out = io.BytesIO()
    try:
        img.save(out, 'WEBP', quality=88, method=4)
        kind = 'webp'
    except (KeyError, OSError, ValueError):
        out = io.BytesIO()
        img.save(out, 'PNG', optimize=True)
        kind = 'png'
    return f"data:image/{kind};base64," + base64.b64encode(out.getvalue()).decode('ascii')
