import os, sys, subprocess
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
from bloknot.ui.main_window import MainWindow
from bloknot.core.node_types import all_specs

results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)

check("1 у каждого блока (кроме unknown) есть вход и выход",
      all(s.inputs and s.outputs for s in all_specs() if s.type != "unknown"))

flow = FlowService(); svc = ProjectService(ProjectRepository(db.connect_memory()), flow)
win = MainWindow(svc, flow); win.show(); app.processEvents()
svc.create_project("v")
n = svc.add_node("number", 0, 0); a = svc.add_node("act_use", 300, 0); m = svc.add_node("matrix", 0, 200)
r = svc.add_edge(n.id, 0, a.id, 0)
check("2 число → «Использовать у себя» соединяется визуально", r.edge is not None)
r2 = svc.add_edge(m.id, 0, a.id, 0)
check("2 вход занят — старая связь заменяется (как раньше)", r2.edge is not None and len(svc.current.schema.edges) == 1)
r3 = svc.add_edge(a.id, 0, n.id, 0)
check("3 выход «Использовать у себя» соединяется с числом", r3.edge is not None)
r4 = svc.add_edge(n.id, 0, a.id, 0)
check("3 замыкание цикла отклоняется", r4.edge is None and r4.error == "цикл в схеме")
flow.set_schema(svc.current.schema); flow.evaluate_now()
check("4 блоки без вычислений не падают", flow.get_state(a.id).error is None or "установи" not in str(flow.get_state(a).error))
check("4 число по-прежнему считается", flow.get_state(n.id).outputs["out"] == 2.0)

win.schema_tab.scene.load(svc.current); app.processEvents()
it = win.schema_tab.scene.node_items[n.id]
check("5 у узла число есть порт входа на канве", len(it.in_ports) == 1 and len(it.out_ports) == 1)

win.close(); app.processEvents()
r_ = subprocess.run([sys.executable, "tests/check_canvas.py"], capture_output=True, text=True, cwd=ROOT, timeout=300)
check("6 тесты канвы: " + r_.stdout.strip().splitlines()[-1], r_.returncode == 0)
r2_ = subprocess.run([sys.executable, "tests/check_features.py"], capture_output=True, text=True, cwd=ROOT, timeout=300)
check("6 тесты функций: " + r2_.stdout.strip().splitlines()[-1], r2_.returncode == 0)
r3_ = subprocess.run([sys.executable, "tests/check_agent.py"], capture_output=True, text=True, cwd=ROOT, timeout=400)
check("6 тесты экспорта: " + r3_.stdout.strip().splitlines()[-1], r3_.returncode == 0)
print(f"\n{sum(results)}/{len(results)} passed")
os._exit(0 if all(results) else 1)
