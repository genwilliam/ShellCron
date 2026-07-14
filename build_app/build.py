"""ShellCron macOS App Build Script.

Build a standalone .app bundle using PyInstaller.

Usage:
    python build_app/build.py          # build .app in dist/
    python build_app/build.py --dmg    # build .app + .dmg

This script is for users who want the desktop GUI or .app bundle.
The default way to use ShellCron is via the CLI (shcron).
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_APP_DIR = PROJECT_ROOT / "build_app"

APP_NAME = "ShellCron"
ICON_PATH = BUILD_APP_DIR / "icons" / "ShellCron.icns"
SPEC_PATH = BUILD_APP_DIR / "shellcron.spec"

# Path to Python within the project's venv
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def check_dependencies() -> bool:
    """Check if PyInstaller is installed."""
    try:
        subprocess.run(
            [str(VENV_PYTHON), "-m", "PyInstaller", "--version"],
            capture_output=True, timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def install_pyinstaller():
    """Install PyInstaller in the project venv."""
    print("Installing PyInstaller...")
    subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "pyinstaller"],
        check=True, timeout=120,
    )


def build_app():
    """Build the .app bundle using PyInstaller."""
    print(f"=== Building {APP_NAME}.app ===")

    # Clean previous builds
    for d in [PROJECT_ROOT / "build", DIST_DIR / APP_NAME, DIST_DIR / f"{APP_NAME}.app"]:
        if d.exists():
            shutil.rmtree(str(d))

    cmd = [
        str(VENV_PYTHON), "-m", "PyInstaller", "--noconfirm",
        "--name", APP_NAME,
        "--windowed", "--onedir",
        f"--icon={ICON_PATH}" if ICON_PATH.exists() else "",
        "--add-data", f"src/shellcron/daemon:daemon",
        "--add-data", f"src/shellcron/web:web",
        "--add-data", f"src/shellcron/cli:cli",
        "--hidden-import", "flask",
        "--hidden-import", "apscheduler",
        "--hidden-import", "requests",
        "--hidden-import", "werkzeug",
        "--hidden-import", "jinja2",
        "--hidden-import", "markupsafe",
        "--hidden-import", "click",
        "--hidden-import", "typer",
        "--hidden-import", "itsdangerous",
        "--hidden-import", "blinker",
        "--hidden-import", "tzlocal",
        "--distpath", str(DIST_DIR),
        "--osx-bundle-identifier", "com.shellcron.app",
        str(PROJECT_ROOT / "src" / "shellcron" / "cli" / "main.py"),
    ]
    # Remove empty strings
    cmd = [c for c in cmd if c]

    subprocess.run(cmd, check=True, timeout=300, cwd=str(PROJECT_ROOT))
    print(f"✓ {APP_NAME}.app built at {DIST_DIR / f'{APP_NAME}.app'}")


def build_dmg():
    """Build a .dmg disk image containing the .app."""
    from create_dmg import create_dmg

    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        print(f"Error: {app_path} not found. Run build first.")
        sys.exit(1)

    dmg_path = DIST_DIR / f"{APP_NAME}.dmg"
    print(f"=== Creating {dmg_path.name} ===")

    # Use create-dmg if available, otherwise hdiutil
    if shutil.which("create-dmg"):
        subprocess.run([
            "create-dmg",
            "--volname", APP_NAME,
            "--window-pos", "200", "120",
            "--window-size", "600", "400",
            "--icon-size", "100",
            "--app-drop-link", "400", "185",
            str(dmg_path),
            str(app_path),
        ], check=True, timeout=120)
    else:
        # Fallback: hdiutil
        dmg_src = DIST_DIR / "dmg_tmp"
        if dmg_src.exists():
            shutil.rmtree(str(dmg_src))
        dmg_src.mkdir(parents=True)
        shutil.copytree(str(app_path), str(dmg_src / f"{APP_NAME}.app"))
        # Symlink /Applications
        (dmg_src / "Applications").symlink_to("/Applications")

        if dmg_path.exists():
            dmg_path.unlink()
        subprocess.run([
            "hdiutil", "create", "-volname", APP_NAME,
            "-srcfolder", str(dmg_src), "-ov",
            "-format", "UDZO", "-fs", "HFS+",
            str(dmg_path),
        ], check=True, timeout=120)
        shutil.rmtree(str(dmg_src))

    print(f"✓ {dmg_path.name} created ({dmg_path.stat().st_size // 1024} KB)")


def install_app():
    """Copy the built .app to /Applications."""
    src = DIST_DIR / f"{APP_NAME}.app"
    dst = Path.home() / "Applications" / f"{APP_NAME}.app"
    if not src.exists():
        print(f"Error: {src} not found. Run build first.")
        sys.exit(1)
    if dst.exists():
        shutil.rmtree(str(dst))
    shutil.copytree(str(src), str(dst))
    print(f"✓ Installed to {dst}")


def main():
    parser = argparse.ArgumentParser(description="Build ShellCron .app bundle")
    parser.add_argument("--dmg", action="store_true", help="Build .dmg after .app")
    parser.add_argument("--install", action="store_true", help="Install .app to /Applications")
    parser.add_argument("--force-install", action="store_true",
                        help="Force install PyInstaller if missing")
    args = parser.parse_args()

    if not check_dependencies():
        if args.force_install:
            install_pyinstaller()
        else:
            print("PyInstaller not found. Install with:")
            print(f"  {VENV_PYTHON} -m pip install pyinstaller")
            print("Or rerun with --force-install")
            sys.exit(1)

    print(f"Building {APP_NAME} from {PROJECT_ROOT}")
    print(f"Python: {VENV_PYTHON}")

    build_app()
    if args.dmg:
        build_dmg()
    if args.install:
        install_app()

    print("\nDone!")


if __name__ == "__main__":
    main()
