#!/usr/bin/env python3
"""Unlock a workshop part when the presenter gives you its password.

    python unlock.py <part-number> <password>      e.g.  python unlock.py 2 some-pass-word-12

Extracts locked/part-<n>.zip into unlocked/part-<n>/. Works on Windows, Linux and macOS (Python 3, no extras).
"""
import io, os, sys, zipfile

def main():
    if len(sys.argv) != 3:
        print(__doc__.strip()); sys.exit(1)
    part, pwd = sys.argv[1], sys.argv[2].encode()
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "locked", "part-%s.zip" % part)
    if not os.path.exists(path):
        print("No such part: %s" % path); sys.exit(1)
    try:
        with zipfile.ZipFile(path) as outer:
            inner = outer.read("payload.zip", pwd=pwd)
    except RuntimeError:
        print("Wrong password."); sys.exit(2)
    dest = os.path.join(here, "unlocked", "part-%s" % part)
    with zipfile.ZipFile(io.BytesIO(inner)) as z:
        names = z.namelist()
        z.extractall(dest)
    tops = sorted({n.split("/")[0] for n in names if n.strip("/")})
    print("Unlocked part %s: %d files -> %s" % (part, len(names), ", ".join(os.path.join("unlocked", "part-" + part, t) + "/" for t in tops)))

if __name__ == "__main__":
    main()
