import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
from bloknot.ui import theme
theme.init_fonts(); app.setStyleSheet(theme.build_qss())
from bloknot.storage import db
from bloknot.storage.project_repository import ProjectRepository
from bloknot.services.flow_service import FlowService
from bloknot.services.project_service import ProjectService
from bloknot.ui.main_window import MainWindow
from bloknot.core.node_types import USAGE, all_specs

flow = FlowService(); svc = ProjectService(ProjectRepository(db.connect_memory()), flow)
win = MainWindow(svc, flow); win.show(); app.processEvents()
svc.create_project("t"); tab = win.schema_tab
results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)

# 1. подсказка есть для каждого блока
missing = [s.type for s in all_specs() if s.type not in USAGE]
check(f"1 подсказка есть для всех блоков (нет: {missing})", not missing)

# 2. панель справа показывает три секции
n = svc.add_node("parse_html", 0, 0); tab.scene.load(svc.current); app.processEvents()
tab.params.show_node(n.id); app.processEvents()
texts = [w.text() for w in tab.params._form_host.findChildren(QLabel)]
check("2 панель: «Как использовать» показан", any(t == "HOW TO USE" for t in texts))
check("2 панель: «Пример связи» показан", any(t == "LINK EXAMPLE" for t in texts))

# 3. цепочка через Результат: 3 -> Результат -> Оператор(+1) -> Результат2
svc.current.schema.nodes.clear(); svc.current.schema.edges.clear()
num = svc.add_node("number", 0, 0); res = svc.add_node("result", 200, 0)
op = svc.add_node("math", 400, 0); res2 = svc.add_node("result", 600, 0)
svc.set_param(num.id, "value", 3.0); svc.set_param(op.id, "op", "+")
flow.set_schema(svc.current.schema); flow.invalidate_all(); flow.evaluate_now()
svc.add_edge(num.id, 0, res.id, 0); svc.add_edge(res.id, 0, op.id, 0)
svc.add_edge(num.id, 0, op.id, 1)                  # второй вход: 3 + 3
svc.add_edge(op.id, 0, res2.id, 0)
flow.evaluate_now()
check("3 Результат пропускает значение дальше", flow.get_state(res.id).outputs["out"] == 3.0)
check("3 оператор получил 3 через Результат", flow.get_state(op.id).outputs["out"] is not None)
flow.evaluate_now()
check("3 итог в конце цепочки", flow.get_state(res2.id).outputs["out"] == 6.0)

# 4. окончательный ответ: выход не соединён — значение остаётся в узле
check("4 окончательный результат виден в узле", flow.get_state(res2.id).outputs["out"] == 6.0)

# 5. старые тесты канвы не сломаны
import subprocess
r = subprocess.run([sys.executable, "tests/check_canvas.py"], capture_output=True, text=True,
                   cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=240)
check("5 тесты канвы проходят: " + r.stdout.strip().splitlines()[-1], r.returncode == 0)

win.close(); app.processEvents()
print(f"\n{sum(results)}/{len(results)} passed")
os._exit(0 if all(results) else 1)
