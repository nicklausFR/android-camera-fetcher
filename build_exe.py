"""Build the Windows executable and package the translation resources.

Run ``python build_exe.py``. A Windows folder picker asks where the final
AndroidCameraFetcher.exe must be created. The selected folder is remembered in
build_exe_config.json so the next build starts at the same location.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT / "build_exe_config.json"
APP_NAME = "AndroidCameraFetcher"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(output_dir: Path) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"output_directory": str(output_dir)}, indent=2) + "\n",
        encoding="utf-8",
    )


def choose_output_directory(initial: Path) -> Path | None:
    """Ask for the destination through the native Windows folder dialog."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Destination de AndroidCameraFetcher.exe",
            initialdir=str(initial if initial.is_dir() else PROJECT),
            parent=root,
        )
        root.destroy()
        return Path(selected) if selected else None
    except Exception:
        answer = input(f"Dossier de destination [{initial}]: ").strip().strip('"')
        return Path(answer) if answer else initial


def compile_translations() -> None:
    subprocess.run([sys.executable, str(PROJECT / "tools" / "compile_translations.py")], check=True)


def build(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    compile_translations()
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--distpath", str(output_dir),
        "--workpath", str(PROJECT / "build"),
        "--specpath", str(PROJECT),
        "--add-data", f"{PROJECT / 'locales'};locales",
        "--hidden-import", "pythoncom",
        "--hidden-import", "pywintypes",
        "--hidden-import", "win32com",
        str(PROJECT / "main.py"),
    ]
    subprocess.run(command, check=True, cwd=PROJECT)
    executable = output_dir / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise RuntimeError(f"Executable not produced: {executable}")
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Android Camera Fetcher for Windows")
    parser.add_argument("--output-dir", type=Path, help="Destination folder (skips the folder picker)")
    args = parser.parse_args()
    saved = Path(load_config().get("output_directory", PROJECT / "dist"))
    output_dir = args.output_dir or choose_output_directory(saved)
    if output_dir is None:
        print("Build cancelled.")
        return 0
    try:
        executable = build(output_dir)
    except subprocess.CalledProcessError as error:
        print(f"Build failed (exit code {error.returncode}).", file=sys.stderr)
        return error.returncode or 1
    save_config(output_dir)
    print(f"Build complete: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
