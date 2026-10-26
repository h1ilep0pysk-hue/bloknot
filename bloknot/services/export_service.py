"""Экспорт проекта в Markdown + Mermaid (SPEC_UI п. 6, ARCHITECTURE С5). Без Qt."""
from __future__ import annotations

import json as _json

from ..core.models import Project
from ..core.node_types import block_syntax, block_usage, default_params, get_spec
from ..core.validation import topo_sort


def _mermaid_label(text: str) -> str:
    return " ".join(text.replace('"', "'").split()) or "—"


def _params_text(node, spec) -> str:
    parts = []
    for key, ps in spec.params.items():
        val = node.params.get(key, ps.default)
        if val not in (None, ""):
            parts.append(f"{ps.label}: `{' '.join(str(val).split())}`")
    return "; ".join(parts)


def export_markdown(project: Project) -> str:
    schema = project.schema
    nodes = {n.id: n for n in schema.nodes}
    order, cyclic = topo_sort([n.id for n in schema.nodes], schema.edges)
    order = order + cyclic            # узлы цикла (битый файл) — в конец, ничего не теряем
    index = {nid: i + 1 for i, nid in enumerate(order)}

    lines: list[str] = [f"# {project.name}", ""]
    if project.idea_summary.strip():
        lines += [f"> {' '.join(project.idea_summary.split())}", ""]
    if project.description.strip():
        lines += ["## Описание", "", project.description.strip(), ""]

    lines += ["## Шаги схемы", ""]
    if not order:
        lines += ["Схема пока пуста.", ""]
    for nid in order:
        node = nodes[nid]
        spec = get_spec(node.type)
        incoming = sorted((e for e in schema.edges if e.to_node == nid), key=lambda e: e.to_port)
        src = ", ".join(f"шаг {index[e.from_node]}" for e in incoming if e.from_node in index)
        kind = "исполняемый" if spec.runnable else "проектный"
        line = f"{index[nid]}. **{node.title}** ({spec.title}, {kind})"
        details = _params_text(node, spec)
        if details:
            line += f" — {details}"
        if src:
            line += f". Получает данные от: {src}"
        lines.append(line)
    lines.append("")

    lines += ["## Диаграмма", "", "```mermaid", "flowchart LR"]
    for nid in order:
        lines.append(f'    n{index[nid]}["{_mermaid_label(nodes[nid].title)}"]')
    for e in schema.edges:
        if e.from_node not in index or e.to_node not in index:
            continue
        src_spec = get_spec(nodes[e.from_node].type)
        label = ""
        if len(src_spec.outputs) > 1 and 0 <= e.from_port < len(src_spec.outputs):
            label = f"|{_mermaid_label(src_spec.outputs[e.from_port].caption)}|"
        lines.append(f"    n{index[e.from_node]} -->{label} n{index[e.to_node]}")
    lines += ["```", ""]
    return "\n".join(lines)


# ───────────── экспорт для ИИ-агента ─────────────
_KIND = {"custom": "визуальный (свой блок, значения не считает)"}


def _kind(spec) -> str:
    if spec.type in _KIND:
        return _KIND[spec.type]
    return "исполняемый (вычисляется приложением)" if spec.runnable else \
        "проектный (описывает шаг, не выполняется)"


def _changed_params(node, spec) -> dict:
    defaults = default_params(spec)
    return {k: v for k, v in node.params.items() if v not in (None, "") and v != defaults.get(k)}


def export_agent(project: Project) -> str:
    """Самодостаточная бриф-схема для ИИ-агента: что за система, из каких блоков, как связаны."""
    schema = project.schema
    nodes = {n.id: n for n in schema.nodes}
    order, cyclic = topo_sort([n.id for n in schema.nodes], schema.edges)
    order = order + cyclic
    ref = {nid: f"n{i + 1}" for i, nid in enumerate(order)}
    out_edges = {(e.from_node, e.from_port) for e in schema.edges}

    def port_name(nid: str, port: int, side: str) -> str:
        spec = get_spec(nodes[nid].type)
        ports = spec.outputs if side == "out" else spec.inputs
        return ports[port].name if 0 <= port < len(ports) else str(port)

    lines: list[str] = [
        f"# Архитектура: {project.name}", "",
        "Это схема системы из приложения Bloknot. Прочитай её как план архитектуры, а не как готовый код.",
        "- Каждый блок — компонент системы; `ID` (n1, n2…) используй в ответах.",
        "- Связь `A.out → B.in` — поток данных от выхода A ко входу B.",
        "- Блоки «исполняемые» вычисляются приложением; «проектные» и «свои» описывают шаги и компоненты.",
        "- Результат, у которого выход не подключён, — окончательный ответ системы.", "",
    ]
    if project.idea_summary.strip():
        lines += ["## Идея", "", f"> {' '.join(project.idea_summary.split())}", ""]
    if project.description.strip():
        lines += ["## Описание", "", project.description.strip(), ""]

    lines += [f"## Компоненты ({len(order)})", ""]
    if not order:
        lines += ["Схема пуста.", ""]
    for nid in order:
        node, spec = nodes[nid], get_spec(nodes[nid].type)
        lines.append(f"### {ref[nid]} — {node.title}")
        if node.type == "custom":                       # свой блок: назначение — его собственное описание
            note = ' '.join(str(node.params.get("note") or "").split())
            lines.append(f"- Тип: свой блок · визуальный компонент")
            lines.append(f"- Назначение: {note or 'описание не задано'}")
        else:
            syntax, _ = block_syntax(node.type)
            usage, _ = block_usage(node.type)
            lines.append(f"- Тип: {spec.title} · {_kind(spec)}")
            if usage:
                lines.append(f"- Назначение: {usage}")
            if syntax:
                lines.append(f"- Синтаксис: `{syntax}`")
        changed = {k: v for k, v in _changed_params(node, spec).items()
                   if not (node.type == "custom" and k == "note")}
        if changed:
            lines.append("- Параметры: " + "; ".join(
                f"{spec.params[k].label if k in spec.params else k} = `{' '.join(str(v).split())}`"
                for k, v in changed.items()))
        lines.append("")

    lines += ["## Связи (поток данных)", ""]
    if not schema.edges:
        lines += ["Связей нет: блоки пока не соединены.", ""]
    for e in sorted(schema.edges, key=lambda e: (ref.get(e.from_node, ""), ref.get(e.to_node, ""))):
        if e.from_node not in ref or e.to_node not in ref:
            continue
        lines.append(f"- {ref[e.from_node]}.{port_name(e.from_node, e.from_port, 'out')} → "
                     f"{ref[e.to_node]}.{port_name(e.to_node, e.to_port, 'in')}"
                     f"  ({nodes[e.from_node].title} → {nodes[e.to_node].title})")
    lines.append("")

    finals = [nid for nid in order if nodes[nid].type == "result" and (nid, 0) not in out_edges]
    lines += ["## Итоговые результаты", ""]
    lines += [f"- {ref[nid]} — {nodes[nid].title}" for nid in finals] or ["Нет окончательных результатов."]
    lines.append("")

    lines += ["## Диаграмма", "", "```mermaid", "flowchart LR"]
    for nid in order:
        lines.append(f'    {ref[nid]}["{_mermaid_label(nodes[nid].title)}"]')
    for e in schema.edges:
        if e.from_node in ref and e.to_node in ref:
            lines.append(f"    {ref[e.from_node]} --> {ref[e.to_node]}")
    lines += ["```", ""]

    machine = {
        "project": project.name,
        "nodes": [{"id": ref[nid], "type": nodes[nid].type, "title": nodes[nid].title,
                   "kind": _kind(get_spec(nodes[nid].type)),
                   "params": _changed_params(nodes[nid], get_spec(nodes[nid].type))} for nid in order],
        "edges": [{"from": f"{ref[e.from_node]}.{port_name(e.from_node, e.from_port, 'out')}",
                   "to": f"{ref[e.to_node]}.{port_name(e.to_node, e.to_port, 'in')}"}
                  for e in schema.edges if e.from_node in ref and e.to_node in ref],
        "final_results": [ref[n] for n in finals],
    }
    lines += ["## Машиночитаемо (JSON)", "", "```json",
              _json.dumps(machine, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)
