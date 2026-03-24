#!/usr/bin/env python3
"""
Build the Vite frontend before a Vercel FastAPI deployment.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
API_WEB_DIR = ROOT_DIR / "api" / "web_dist"


def main() -> None:
    subprocess.run(["npm", "install"], cwd=WEB_DIR, check=True)
    subprocess.run(["npm", "run", "build"], cwd=WEB_DIR, check=True)
    shutil.rmtree(API_WEB_DIR, ignore_errors=True)
    shutil.copytree(WEB_DIR / "dist", API_WEB_DIR)


if __name__ == "__main__":
    main()
