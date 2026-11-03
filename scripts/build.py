"""Build a native onedir bundle on the current OS; does not publish it."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="현재 OS용 PGM 실행 파일 묶음을 만듭니다.")
    parser.add_argument("--dry-run", action="store_true", help="실행할 명령만 출력")
    parser.add_argument("--console", action="store_true", help="오류 확인용 콘솔 포함")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    entry = root / "run_pgm.py"
    if not entry.is_file():
        print(f"실행 진입 파일이 없습니다: {entry}", file=sys.stderr)
        return 1
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--console" if args.console else "--windowed", "--name", "PGM",
        "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root / "build"),
    ]
    assets = root / "pgm" / "assets"
    if assets.is_dir():
        command.extend(["--add-data", f"{assets}{os.pathsep}pgm/assets"])
    command.append(str(entry))
    print(subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command))
    if args.dry_run:
        return 0
    if importlib.util.find_spec("PyInstaller") is None:
        print("먼저 python -m pip install -r requirements-dev.txt 를 실행해 주세요.", file=sys.stderr)
        return 1
    environment = dict(os.environ)
    environment["PYINSTALLER_CONFIG_DIR"] = str(root / "build" / ".pyinstaller-cache")
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
