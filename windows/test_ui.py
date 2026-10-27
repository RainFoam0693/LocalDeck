"""Render real Qt widgets at several scales and check navigation and selection."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from windows.app import App
from windows.fluent import setup_theme

qt = QApplication([]); setup_theme(qt); app = App(preview=True); app.show(); qt.processEvents()
assert app.live_list.count() == 5
app.search.setText('8000'); assert app.live_list.count() == 1 and app.detail_name.text() == 'python.exe'
app.search.setText('does-not-exist'); assert app.live_list.count() == 0 and not app.stop_button.isEnabled()
app.search.clear(); app.toggle_sort(); assert app.selected_listener()['name'] == 'node.exe'
output = Path(os.environ.get('LOCALDECK_UI_OUTPUT', 'dist/windows-preview')); output.mkdir(parents=True, exist_ok=True)
for width, height in [(1320, 860), (1050, 700)]:
    app.resize(width, height); qt.processEvents()
    for index, page in enumerate(['services', 'tasks', 'terminals']):
        app.select_page(index); qt.processEvents()
        assert app.tabs.currentIndex() == index
        assert app.centralWidget().width() >= 1000
        app.grab().save(str(output/f'{page}-{width}.png'))
app.select_page(0); app.search.setText('8000'); qt.processEvents(); app.grab().save(str(output/'services-detail.png'))
app.closed = True; app.executor.shutdown(); app.close()
print('Qt UI: search, selection, CPU sort, empty states, 3 pages and 2 sizes passed')
