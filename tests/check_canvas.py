import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
app = QApplication(sys.argv)
from bloknot.ui import theme
theme.init_fonts(); app.setStyleSheet(theme.build_qss())
from bloknot.storage import db
from bloknot.storage.project_repository import ProjectRepository
from bloknot.services.flow_service import FlowService
from bloknot.services.project_service import ProjectService
from bloknot.ui.main_window import MainWindow

flow = FlowService()
svc = ProjectService(ProjectRepository(db.connect_memory()), flow)
win = MainWindow(svc, flow); win.show(); app.processEvents()
svc.create_project("t")
tab = win.schema_tab; scene, view = tab.scene, tab.view

def fresh(nodes):
    """nodes: list of (type,x,y); returns ids"""
    svc.current.schema.nodes.clear(); svc.current.schema.edges.clear()
    ids = [svc.add_node(t, x, y).id for t, x, y in nodes]
    svc.current.schema.edges.clear()
    scene.load(svc.current); app.processEvents()
    return ids

def vp(p): return view.mapFromScene(p)
def drag(a, b, mid=None):
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(a))
    if mid is not None: QTest.mouseMove(view.viewport(), vp(mid))
    QTest.mouseMove(view.viewport(), vp(b))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(b))
    app.processEvents()

def item(i): return scene.node_items[i]
results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("OK   " if cond else "FAIL ") + name)

# 1. точный выход -> вход
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
drag(item(a).out_ports[0].scene_center(), item(b).in_ports[0].scene_center())
check("1 точное попадание выход->вход", len(svc.current.schema.edges) == 1)

# 2. отпустили в 15 px от точки входа (раньше не цеплялось)
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
c = item(b).in_ports[0].scene_center()
drag(item(a).out_ports[0].scene_center(), QPointF(c.x() - 15, c.y() + 10))
check("2 цепляется в радиусе ~18 px", len(svc.current.schema.edges) == 1)

# 3. отпустили на тело узла-приёмника (не на точку)
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
c = item(b).sceneBoundingRect().center()
drag(item(a).out_ports[0].scene_center(), c)
check("3 отпускание на тело узла", len(svc.current.schema.edges) == 1)

# 4. обратная тяга: от входа к выходу
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
before = (item(b).x(), item(b).y())
drag(item(b).in_ports[0].scene_center(), item(a).out_ports[0].scene_center())
check("4 обратная тяга создаёт связь", len(svc.current.schema.edges) == 1)
check("4 узел при обратной тяге не двигается", (item(b).x(), item(b).y()) == before)
e = svc.current.schema.edges[0] if svc.current.schema.edges else None
check("4 направление связи выход->вход", e and e.from_node == a and e.to_node == b)

# 5. обратная тяга, отпустили на тело узла-источника
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
drag(item(b).in_ports[0].scene_center(), item(a).sceneBoundingRect().center())
check("5 обратная тяга на тело узла", len(svc.current.schema.edges) == 1)

# 6. масштаб 0.5: точка относительно мала, но прилипание работает
view.set_zoom(0.5)
a, b = fresh([("site_url", 0, 0), ("parse_html", 300, 0)])
drag(item(a).out_ports[0].scene_center(), item(b).in_ports[0].scene_center())
check("6 при зуме 50% связь создаётся", len(svc.current.schema.edges) == 1)
view.set_zoom(1.0)

# 7. самосвязь запрещена (не падает, связи нет)
a, = fresh([("math", 0, 0)])[:1] and [svc.current.schema.nodes[0].id]
drag(item(a).out_ports[0].scene_center(), item(a).in_ports[0].scene_center())
check("7 самосвязь запрещена", len(svc.current.schema.edges) == 0)

# 8. цепочка едет вместе: A->B->C, D отдельно
a, b, c, d = fresh([("site_url", 0, 0), ("parse_html", 300, 0),
                    ("extract", 600, 0), ("site_url", 0, 300)])
svc.add_edge(a, 0, b, 0); svc.add_edge(b, 0, c, 0); scene.load(svc.current); app.processEvents()
pos0 = {n: (item(n).x(), item(n).y()) for n in (a, b, c, d)}
QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton,
                 pos=vp(item(a).sceneBoundingRect().center()))
QTest.mouseMove(view.viewport(), vp(item(a).sceneBoundingRect().center() + QPointF(60, 40)))
QTest.mouseMove(view.viewport(), vp(item(a).sceneBoundingRect().center() + QPointF(120, 80)))
QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton,
                   pos=vp(item(a).sceneBoundingRect().center() + QPointF(120, 80)))
app.processEvents()
dA = (item(a).x() - pos0[a][0], item(a).y() - pos0[a][1])
check("8 перетащили A", dA != (0, 0))
check("8 B остался на месте (двигается только A)", (item(b).x(), item(b).y()) == pos0[b])
check("8 C остался на месте", (item(c).x(), item(c).y()) == pos0[c])
check("8 D остался на месте", (item(d).x(), item(d).y()) == pos0[d])
check("8 связи A->B и B->C сохранились", len(svc.current.schema.edges) == 2)
e = item(b).in_ports[0].scene_center(); ea = scene.edge_into(b, 0)
check("8 связь A->B тянется за A (конец на входе B)", ea is not None and ea._p1 == e)
check("8 позиции сохранены в модель",
      all((svc.node(n).x, svc.node(n).y) == (item(n).x(), item(n).y()) for n in (a, b, c, d)))

print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed")
os._exit(0 if all(ok for _, ok in results) else 1)
