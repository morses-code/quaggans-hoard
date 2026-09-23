"""Render the shared SVG into a multi-resolution Windows ICO.

Optional developer dependency: pip install resvg_py==0.5.0
The generated ICO is committed; normal app builds do not need this tool.
"""
from pathlib import Path
import struct
import resvg_py

public = Path(__file__).resolve().parent / 'public'
sizes = (16, 24, 32, 48, 64, 128, 256)
images = [resvg_py.svg_to_bytes(svg_path=str(public / 'quaggan.svg'), width=size, height=size)
          for size in sizes]
offset = 6 + 16 * len(sizes)
directory = []
for size, png in zip(sizes, images):
    directory.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
    offset += len(png)
(public / 'favicon.ico').write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(directory) + b''.join(images))
print('Generated favicon.ico at 16, 24, 32, 48, 64, 128 and 256 pixels.')
