import os, sys, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
results = []
def check(name, cond):
    results.append(bool(cond)); print(("OK   " if cond else "FAIL ") + name)

def run_snippet(code, frozen=False):
    env = dict(os.environ)
    pre = ""
    if frozen:
        pre = (f"import sys; sys.frozen=True; sys._MEIPASS={ROOT!r}+'/_meipass'; "
               f"sys.executable={ROOT!r}+'/dist/Bloknot.exe'\n")
    r = subprocess.run([sys.executable, "-c", pre + "import sys; sys.path.insert(0,%r)\n" % ROOT + code],
                       capture_output=True, text=True, env=env, timeout=60)
    return r.stdout.strip(), r.returncode, r.stderr.strip()

out, rc, err = run_snippet("from bloknot.paths import data_dir; print(data_dir())")
check("1 в исходниках база лежит в data/ рядом с проектом", out == os.path.join(ROOT, "data") and rc == 0)

out, rc, err = run_snippet("from bloknot.paths import data_dir; print(data_dir())", frozen=True)
check("2 в exe база лежит рядом с Bloknot.exe", out == os.path.join(ROOT, "dist", "data") and rc == 0)

out, rc, err = run_snippet("from bloknot.paths import resource_path; print(resource_path('assets','icon','icon.ico'))", frozen=True)
check("3 в exe иконка ищется во временной папке PyInstaller", out.endswith(os.path.join("_meipass", "bloknot", "assets", "icon", "icon.ico")) and rc == 0)

out, rc, err = run_snippet("from bloknot.paths import resource_path; print(resource_path('assets','icon','icon.ico').exists())")
check("4 в исходниках иконка находится", out == "True" and rc == 0)

out, rc, err = run_snippet("from bloknot.storage import db; print(db.default_db_path())", frozen=True)
check("5 db.default_db_path в exe указывает на dist/data", out == os.path.join(ROOT, "dist", "data", "bloknot.sqlite3") and rc == 0)

print(f"\n{sum(results)}/{len(results)} passed")
os._exit(0 if all(results) else 1)
