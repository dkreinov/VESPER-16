#!/usr/bin/env python3
"""T6 nameplate font - the ONE source of the 3x5 font (kit renderer and the part-4 grader).

  python t6font.py NAME                 print the 5 pixel rows ('#' / '.')
  python t6font.py NAME --task-md OUT   write tasks/T6.md filled in for NAME

Normalise: upper-case, keep A-Z, max 8 letters, empty -> VESPER. Letter i has its top-left pixel at
column 1 + 4*i, row 1 (rows 1-5); one blank column between letters. Standard library only.
Locked part 4 holds a byte-identical copy (grader/t6font.py), made by harness/build_part4.py (private repo).
"""
import os
import sys

MAX_LETTERS = 8
DEFAULT_NAME = "VESPER"
FONT = {
    "A": [".#.", "#.#", "###", "#.#", "#.#"],
    "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"],
    "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"],
    "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"],
    "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"],
    "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#.#", "###", "###", "#.#", "#.#"],
    "N": ["##.", "#.#", "#.#", "#.#", "#.#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."],
    "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "###", "..#"],
    "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."],
    "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"],
    "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#.#", "#.#", "###", "###", "#.#"],
    "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."],
    "Z": ["###", "..#", ".#.", "#..", "###"],
}


def normalise(name):
    s = "".join(c for c in str(name).upper() if "A" <= c <= "Z")[:MAX_LETTERS]
    return s or DEFAULT_NAME


def rows(name):
    """5 strings, 1:1 pixels; string index 0 is column 1."""
    s = normalise(name)
    return [" ".join(FONT[c][r] for c in s).replace(" ", ".") for r in range(5)]


def pixels(name):
    """(column, row) of every lit name pixel, in image coordinates."""
    return [(1 + x, 1 + r) for r, line in enumerate(rows(name)) for x, ch in enumerate(line) if ch == "#"]


def task_md(template, name):
    """Fill the T6 template text: {NAME} -> the normalised name, {NAME_ROWS} -> the 5 pixel rows."""
    n = normalise(name)
    return template.replace("{NAME_ROWS}", "\n".join(rows(n))).replace("{NAME}", n)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if "--task-md" in argv:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "tasks", "T6.md"), encoding="utf-8") as f:
            tpl = f.read()
        with open(argv[argv.index("--task-md") + 1], "w", encoding="utf-8", newline="\n") as f:
            f.write(task_md(tpl, argv[0]))
    else:
        print("\n".join(rows(argv[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
