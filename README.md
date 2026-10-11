# VESPER-16 development kit

Build the game described in [tasks/T3.md](tasks/T3.md).

## Requirements

- Linux x86-64 to run the supplied assembler and emulator.
- A browser to open the frame player.

The emulator is a self-contained Linux executable. Windows users need a Linux
environment such as WSL, a Linux VM or a remote Linux machine. It does not run
directly in PowerShell or on macOS.

## Start

```sh
git clone https://github.com/dkreinov/VESPER-16.git
cd VESPER-16
chmod +x bin/vesper
mkdir -p solutions
bin/vesper run examples/fill.vsa --frames 30 --out out/fill
```

Open `player.html` in a browser and drop the generated output folder into it.
Read `tasks/T3.md` for the complete game requirements and submission path.
You may search the web and test the console. This kit imposes no simulator-call
limit. Leave the supplied task and emulator unchanged.

## Files

```text
bin/vesper          assembler and emulator
examples/fill.vsa   small sample program
examples/pixel.vsa  small sample program
tasks/T3.md        game task
player.html        viewer for generated frames or GIFs
solutions/         save your game here
```
