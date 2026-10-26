"""Пути к ресурсам и данным. Работает и из исходников, и в собранном exe (PyInstaller)."""
from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent            # папка пакета bloknot/


def resource_path(*parts: str) -> Path:
    """Вшитые ресурсы (шрифты, иконка). В exe лежат во временной папке PyInstaller."""
    base = Path(sys._MEIPASS) / "bloknot" if getattr(sys, "frozen", False) else PACKAGE_DIR
    return base.joinpath(*parts)


def data_dir() -> Path:
    """Папка данных (база). В exe — рядом с Bloknot.exe, чтобы данные не терялись."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return PACKAGE_DIR.parent / "data"
