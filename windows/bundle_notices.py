"""Include dependency notices and editable LGPL pyte source in distributions."""
from importlib import metadata
from pathlib import Path
import shutil
import pyte

root = Path('build/third-party')
root.mkdir(parents=True, exist_ok=True)
for name in ['pyte', 'pywinpty', 'psutil', 'Pillow', 'wcwidth', 'PySide6-Essentials', 'shiboken6']:
    distribution = metadata.distribution(name)
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    for file in distribution.files or []:
        if any(word in file.name.lower() for word in ['license', 'copying', 'notice']):
            source = Path(distribution.locate_file(file))
            if source.is_file(): shutil.copy2(source, target / file.name)
shutil.copytree(Path(pyte.__file__).parent, root / 'pyte/source/pyte', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
(root / 'README.txt').write_text('LocalDeck desktop dependencies\n\npyte is LGPL-3.0-or-later. The unmodified Python source and license are included.\nTo modify it, edit these source files, replace pyte in your Python environment,\nthen rebuild LocalDeck with windows/build.ps1 using the source in our GitHub repository.\nLocalDeck uses no binary signature or anti-modification mechanism.\nQt / PySide6 and Shiboken are unmodified dynamically linked libraries (LGPL-3.0).\nSource: https://download.qt.io/archive/qtforpython/ and https://code.qt.io/pyside/pyside-setup.git\nRebuild with replacement libraries using windows/requirements.txt and windows/build.ps1.\nLocalDeck source is included in our GitHub repository; no signature restricts modification.\nOther dependencies retain their original licenses; see their respective folders.\n', encoding='utf-8')
