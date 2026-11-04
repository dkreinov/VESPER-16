#!/usr/bin/env python3
"""Make docs/GUIDE-PROMPT.txt from helper-skill/vesper-guide/SKILL.md.

The skill is the one source. The prompt file is the same text for agents that cannot load a skill:
the learner pastes the whole file into a NEW chat (outside every run folder).

  python tools/make_guide_prompt.py            write docs/GUIDE-PROMPT.txt
  python tools/make_guide_prompt.py --check    exit 1 if the file is out of date
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "helper-skill", "vesper-guide", "SKILL.md")
OUT = os.path.join(ROOT, "docs", "GUIDE-PROMPT.txt")

HEAD = (
    "You are the guide for the VESPER-16 workshop. Follow the rules below for the whole chat.\n"
    "Start by asking me which agent I use and which stage I am in.\n"
    "Do not run any command for me. I type every command myself.\n"
    "\n"
    "--- THE RULES (the same text as the vesper-guide skill) ---\n"
    "\n"
)


def body(text):
    """The skill text without the YAML front matter."""
    text = text.replace("\r\n", "\n")
    if text.startswith("---\n"):
        text = text.split("\n---\n", 1)[1]
    return text.lstrip("\n")


def build():
    with open(SKILL, encoding="utf-8") as f:
        return HEAD + body(f.read())


def main(argv):
    want = build()
    if "--check" in argv:
        try:
            with open(OUT, encoding="utf-8", newline="") as f:
                have = f.read().replace("\r\n", "\n")
        except OSError:
            have = ""
        if have != want:
            print("docs/GUIDE-PROMPT.txt is out of date. Run: python tools/make_guide_prompt.py")
            return 1
        return 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(want)
    print("wrote", OUT, len(want), "characters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
