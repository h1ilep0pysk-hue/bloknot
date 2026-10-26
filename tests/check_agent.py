import os, sys, json, re, subprocess
os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from bloknot.ui import theme
theme.init_fonts(); app.setStyleSheet(theme.build_qss())
from bloknot.storage import db
from bloknot.storage.project_repository import ProjectRepository
from bloknot.services.flow_service import FlowService
from bloknot.services.project_service import ProjectService
from bloknot.services.export_service import export_agent
from bloknot.ui.main_window import MainWindow
from bloknot.core.node_types import palette_groups, get_spec

flow = FlowService(); svc = ProjectService(ProjectRepository(db.connect_memory()), flow)
win = MainWindow(svc, flow); win.show(); app.processEvents()
svc.create_project("Бот-ассистент"); svc.update_text(idea="Локальный ассистент, который отвечает на вопросы по документам.")
results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)

check("1 группа Custom есть в палитре", any(c == "Custom" for c, _ in palette_groups()))
c1 = svc.add_node("custom", 0, 0); c2 = svc.add_node("custom", 300, 0); r = svc.add_node("result", 600, 0)
svc.update_text()  # no-op
svc.set_title(c1.id, "ЛОКАЛЬНАЯ ИИ МОДЕЛЬ"); svc.set_title(c2.id, "ИСТОЧНИК ДОКУМЕНТОВ")
svc.set_param(c1.id, "note", "Отвечает на вопросы пользователя")
ok1 = svc.add_edge(c2.id, 0, c1.id, 0); ok2 = svc.add_edge(c1.id, 0, r.id, 0)
check("2 свой блок соединяется с другими", ok1.edge is not None and ok2.edge is not None)
check("2 свой блок не считает значения (нет ошибки)", flow.get_state(c1.id).error is None)

md = export_agent(svc.current)
check("3 есть раздел Компоненты с названиями", "ЛОКАЛЬНАЯ ИИ МОДЕЛЬ" in md and "ИСТОЧНИК ДОКУМЕНТОВ" in md)
check("3 связи в явном виде", "- n1.out → n2.in" in md)
check("3 идея и описание попали в бриф", "Локальный ассистент" in md)
check("3 окончательный результат отмечен", "## Итоговые результаты" in md and "n3 — Result" in md)
check("3 описание блока попало в параметры", "Отвечает на вопросы пользователя" in md)
m = re.search(r"```json\n(.*?)\n```", md, re.S)
data = json.loads(m.group(1)) if m else {}
check("4 JSON валиден и содержит связи", data.get("edges") and len(data["edges"]) == 2)
check("4 JSON: финальный результат", data.get("final_results") == ["n3"])
check("4 JSON: вид блока «визуальный»", any("визуальный" in n["kind"] for n in data.get("nodes", [])))
check("5 Mermaid-диаграмма есть", "```mermaid" in md and "n1 --> n2" in md)

svc.flush(force=True)
r_ = subprocess.run([sys.executable, "tests/check_canvas.py"], capture_output=True, text=True, cwd=ROOT, timeout=300)
check("6 тесты канвы проходят: " + r_.stdout.strip().splitlines()[-1], r_.returncode == 0)
r2 = subprocess.run([sys.executable, "tests/check_features.py"], capture_output=True, text=True, cwd=ROOT, timeout=300)
check("6 тесты функций проходят: " + r2.stdout.strip().splitlines()[-1], r2.returncode == 0)

win.close(); app.processEvents()
print(f"\n{sum(results)}/{len(results)} passed")
open("/tmp/agent_sample.md","w",encoding="utf-8").write(md)
os._exit(0 if all(results) else 1)
