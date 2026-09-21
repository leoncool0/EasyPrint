"""
Generate EasyPrint icons.
Source: image_410469400848857.png (user approved design)
Outputs:
  - app.ico: Application icon (color)
  - tray_connected.ico: Tray icon - online (color)
  - tray_disconnected.ico: Tray icon - offline (grayscale)
"""
from PIL import Image
import struct
import os

ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_ICON = os.path.join(ASSETS_DIR, "image_410469400848857.png")


def to_grayscale(img: Image) -> Image:
    """Convert image to grayscale while preserving alpha channel."""
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        rgb = Image.merge("RGB", (r, g, b))
        gray = rgb.convert("L")
        gray_rgb = Image.merge("RGB", (gray, gray, gray))
        r2, g2, b2 = gray_rgb.split()
        return Image.merge("RGBA", (r2, g2, b2, a))
    elif img.mode == "RGB":
        gray = img.convert("L")
        gray_rgb = Image.merge("RGB", (gray, gray, gray))
        return gray_rgb.convert("RGBA")
    return img


def create_ico(src_img: Image, path: str, sizes: list):
    """Create .ico file with multiple sizes using manual ICO construction."""
    # Ensure source is at least 512x512 RGBA
    base = src_img.resize((512, 512), Image.LANCZOS)
    if base.mode != "RGBA":
        base = base.convert("RGBA")

    # Prepare PNG data for each size
    png_data_list = []
    for size in sizes:
        resized = base.resize((size, size), Image.LANCZOS)
        import io
        buf = io.BytesIO()
        # Save as PNG with alpha
        resized.save(buf, format="PNG")
        png_data = buf.getvalue()
        png_data_list.append((size, png_data))

    # Build ICO file manually
    # ICO file header: 6 bytes
    # ICO directory entry: 16 bytes per image
    num_images = len(png_data_list)
    header_size = 6
    dir_size = 16 * num_images
    data_offset = header_size + dir_size

    # ICO header
    ico = bytearray()
    ico += struct.pack('<HHH', 0, 1, num_images)  # reserved, type=1(icon), count

    # Directory entries
    current_offset = data_offset
    for size, png_data in png_data_list:
        width = size if size < 256 else 0
        height = size if size < 256 else 0
        ico += struct.pack('<BBBBHHII',
            width,          # width (0 = 256)
            height,         # height (0 = 256)
            0,              # color palette count (0 = no palette)
            0,              # reserved
            1,              # color planes
            32,             # bits per pixel
            len(png_data),  # image data size
            current_offset  # image data offset
        )
        current_offset += len(png_data)

    # Image data (PNG for each size)
    for size, png_data in png_data_list:
        ico += png_data

    # Write to file
    with open(path, 'wb') as f:
        f.write(ico)


def main():
    if not os.path.exists(BASE_ICON):
        print(f"ERROR: Base icon not found: {BASE_ICON}")
        return

    # Icon sizes (ICO format supports max 256x256, 512 not supported)
    sizes = [16, 32, 48, 64, 128, 256]

    # Load source image
    print(f"Loading: {BASE_ICON}")
    img = Image.open(BASE_ICON)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 1. app.ico - color
    print("Creating: app.ico (color)")
    create_ico(img.copy(), os.path.join(ASSETS_DIR, "app.ico"), sizes)
    print(f"  Done: app.ico ({os.path.getsize(os.path.join(ASSETS_DIR, 'app.ico'))} bytes)")

    # 2. tray_connected.ico - color (online)
    print("Creating: tray_connected.ico (color = online)")
    create_ico(img.copy(), os.path.join(ASSETS_DIR, "tray_connected.ico"), sizes)
    print(f"  Done: tray_connected.ico ({os.path.getsize(os.path.join(ASSETS_DIR, 'tray_connected.ico'))} bytes)")

    # 3. tray_disconnected.ico - grayscale (offline)
    print("Creating: tray_disconnected.ico (grayscale = offline)")
    gray = to_grayscale(img.copy())
    create_ico(gray, os.path.join(ASSETS_DIR, "tray_disconnected.ico"), sizes)
    print(f"  Done: tray_disconnected.ico ({os.path.getsize(os.path.join(ASSETS_DIR, 'tray_disconnected.ico'))} bytes)")

    # Verify
    print("\nVerification:")
    for name in ["app.ico", "tray_connected.ico", "tray_disconnected.ico"]:
        path = os.path.join(ASSETS_DIR, name)
        verify = Image.open(path)
        print(f"  {name}: size={verify.size}, file={os.path.getsize(path)} bytes")

    print("\nAll icons generated successfully!")
    print(f"  app.ico               -> 应用图标（彩色）")
    print(f"  tray_connected.ico    -> 托盘-在线（彩色）")
    print(f"  tray_disconnected.ico -> 托盘-离线（灰度）")


if __name__ == "__main__":
    main()
