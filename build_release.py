"""Build the Blender add-on ZIP. Run from any directory with Python 3."""
import ast
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
module = ast.parse((ROOT / '__init__.py').read_text())
info = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'bl_info' for t in n.targets))
version = '.'.join(map(str, info['version']))
files = ['__init__.py', 'README.md', 'LICENSE', 'native/GamepadBridge.swift', 'native/gamepad_bridge']
for name in files:
    if not (ROOT / name).is_file():
        raise SystemExit(f'Missing {name}. Build the native helper first; see README.')
out = ROOT / 'dist' / f'roomwalker-{version}-macos-arm64.zip'
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(ROOT / name, 'roomwalker/' + name)
print(out)
