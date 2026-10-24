"""Pulls the latest picker code from GitHub before each launch. Data files and .venv are
never touched. No internet, or GitHub down: starts on the code already here."""

import io
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "jaredtesche-arch/grocery-picker"
HERE = Path(__file__).parent
KEEP = {".venv", "settings.json", "history.json", "picks.json", "staples.json"}


def main(url=f"https://codeload.github.com/{REPO}/zip/refs/heads/main"):
    try:
        data = urllib.request.urlopen(url, timeout=15).read()
    except Exception as e:
        print(f"Couldn't check for updates ({e.__class__.__name__}). Starting anyway.")
        return
    changed = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            rel = info.filename.partition("/")[2]  # drop the grocery-picker-main/ folder
            if not rel or info.is_dir() or rel.split("/")[0] in KEEP:
                continue
            dest, new = HERE / rel, z.read(info)
            if not dest.exists() or dest.read_bytes() != new:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(new)
                changed.append(rel)
    if "requirements.txt" in changed:
        pip = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
        subprocess.run([*pip, "-r", str(HERE / "requirements.txt")], check=False)
    print(f"Updated: {', '.join(changed)}" if changed else "Up to date.")


if __name__ == "__main__":
    main(*sys.argv[1:])
