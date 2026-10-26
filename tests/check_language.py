import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtWidgets import QTabBar
app = QApplication(sys.argv)
from bloknot import i18n
from bloknot.ui import theme
theme.init_fonts(); app.setStyleSheet(theme.build_qss())
from bloknot.storage import db
from bloknot.storage.project_repository import ProjectRepository
from bloknot.services.flow_service import FlowService
from bloknot.services.project_service import ProjectService
from bloknot.ui.main_window import MainWindow
results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)

def build(lang):
    i18n.set_language(lang)
    flow = FlowService(); svc = ProjectService(ProjectRepository(db.connect_memory()), flow)
    win = MainWindow(svc, flow); win.show(); app.processEvents()
    return win, svc

win, svc = build("en")
tabs = [win.tabs.tabText(i) for i in range(win.tabs.count())]
check("1 EN: вкладки Idea/Schema", tabs == ["Idea", "Schema"])
check("1 EN: палитра Data & code", any(c == "Data & code" for c, _ in __import__("bloknot.core.node_types", fromlist=["x"]).palette_groups()))
win.close(); app.processEvents()

win, svc = build("ru")
tabs = [win.tabs.tabText(i) for i in range(win.tabs.count())]
check("2 RU: вкладки Идея/Схема", tabs == ["Идея", "Схема"])
check("2 RU: строка в статусе", i18n.t("Saved") == "Сохранено")
check("2 RU: название блока", i18n.t("Number") == "Число")
check("2 RU: неизвестная строка возвращается как есть", i18n.t("Ветка уже русская") == "Ветка уже русская")
check("2 RU: формат с подстановкой", i18n.t('Delete project "{name}"?', name="A") == 'Удалить проект "A"?')
win.close(); app.processEvents()

i18n.set_language("en")
i18n.save_language("ru")
check("3 выбор языка сохраняется в settings.json", i18n.load_language() == "ru")
i18n.save_language("en")

r = __import__("subprocess").run([sys.executable, "tests/check_ports.py"], capture_output=True, text=True, cwd=ROOT, timeout=900)
check("4 остальные тесты проходят: " + r.stdout.strip().splitlines()[-1], r.returncode == 0)
print(f"\n{sum(results)}/{len(results)} passed")
os._exit(0 if all(results) else 1)
