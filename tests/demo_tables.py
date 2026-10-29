"""Manual demo of the result tables with fake data (no real agent, no state files).
Run in a terminal (PowerShell):  python tests/demo_tables.py"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault("VESPER_HOME", tempfile.mkdtemp(prefix="demo_tables_"))
import workshop as w  # noqa: E402
from test_tables import ORGANISER_ROWS, pair  # noqa: E402


def main():
    print("== show: one row per run, 'what' says what the row is ==")
    w.show_rows(ORGANISER_ROWS)
    print("\n== WITH vs WITHOUT: both attempts pass (change column filled) ==")
    rw, rc = pair("100", "100")
    w.compare_control(None, rw, rc, "T3")
    print("\n== WITH vs WITHOUT: one attempt failed (no change column) ==")
    rw, rc = pair("100", "5")
    w.compare_control(None, rw, rc, "T3")


if __name__ == "__main__":
    main()
