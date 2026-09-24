"""Render the shared SVG into Windows and cross-platform application icons.

Optional developer dependencies: pip install resvg_py==0.5.0 Pillow
The generated ICO is committed; normal app builds do not need this tool.
"""
from pathlib import Path
import struct
import resvg_py
from PIL import Image
from io import BytesIO

public = Path(__file__).resolve().parent / 'public'
sizes = (16, 24, 32, 48, 64, 128, 256)
images = [resvg_py.svg_to_bytes(svg_path=str(public / 'quaggan.svg'), width=size, height=size)
          for size in sizes]
large_png = resvg_py.svg_to_bytes(svg_path=str(public / 'quaggan.svg'), width=512, height=512)
(public / 'quaggan-512.png').write_bytes(large_png)
Image.open(BytesIO(large_png)).convert('RGBA').save(
    public / 'quaggan.icns', sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
offset = 6 + 16 * len(sizes)
directory = []
for size, png in zip(sizes, images):
    directory.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
    offset += len(png)
(public / 'favicon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(directory) + b''.join(images))
print('Generated favicon.ico, quaggan-512.png and quaggan.icns.')
