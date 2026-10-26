import os, sys, json, tempfile, subprocess
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Проверка: язык, сохранённый в settings.json, применяется при следующем запуске (отдельный процесс)
from bloknot import paths
settings = paths.data_dir() / "settings.json"
settings.parent.mkdir(parents=True, exist_ok=True)
settings.write_text(json.dumps({"language": "ru"}, ensure_ascii=False), encoding="utf-8")
code = r'''
import os, sys
os.environ["QT_QPA_PLATFORM"]="offscreen"; sys.path.insert(0, %r)
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from bloknot import i18n
i18n.init_from_settings()
from bloknot.ui import theme
theme.init_fonts(); app.setStyleSheet(theme.build_qss())
from bloknot.storage import db
from bloknot.storage.project_repository import ProjectRepository
from bloknot.services.flow_service import FlowService
from bloknot.services.project_service import ProjectService
from bloknot.ui.main_window import MainWindow
flow=FlowService(); svc=ProjectService(ProjectRepository(db.connect_memory()), flow)
win=MainWindow(svc, flow); win.show(); app.processEvents()
svc.create_project()
win.refresh_projects(); app.processEvents()
print("TABS", [win.tabs.tabText(i) for i in range(win.tabs.count())])
print("LANG", i18n.get_language())
print("TITLE", win.windowTitle())
win.close(); app.processEvents(); os._exit(0)
''' % ROOT
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
out = r.stdout
results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)
check("1 после запуска язык ru из settings.json", "LANG ru" in out)
check("2 вкладки на русском", "TABS ['Идея', 'Схема']" in out)
check("3 заголовок окна содержит «Без названия»", "Без названия" in out and "TITLE Bloknot — Без названия" in out)
settings.write_text(json.dumps({"language": "en"}), encoding="utf-8")
r2 = subprocess.run([sys.executable, "-c", code.replace('"ru"','"en"')], capture_output=True, text=True, timeout=120)
check("4 при en остаётся английский", "TABS ['Idea', 'Schema']" in r2.stdout)
if r.returncode != 0: print(r.stderr[-800:])
print(f"\n{sum(results)}/{len(results)} passed")
os._exit(0 if all(results) else 1)
