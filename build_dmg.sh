#!/bin/bash
# Build ShellCron.dmg
set -e
APP_NAME="ShellCron"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DMG_PATH="$PROJECT_DIR/dist/$APP_NAME.dmg"
echo "=== Building $APP_NAME.app ==="
cd "$PROJECT_DIR"
rm -rf build dist/$APP_NAME.app dist/$APP_NAME

.venv/bin/pyinstaller --noconfirm --name "$APP_NAME" \
  --windowed --onedir \
  --icon img/ShellCron.icns \
  --add-data "daemon:daemon" \
  --add-data "gui:gui" \
  --hidden-import flask --hidden-import apscheduler --hidden-import requests \
  --hidden-import werkzeug --hidden-import jinja2 --hidden-import markupsafe \
  --hidden-import click --hidden-import itsdangerous --hidden-import blinker \
  --hidden-import tzlocal \
  --distpath dist \
  --osx-bundle-identifier com.shellcron.app \
  gui/__main__.py

echo "=== Creating DMG ==="
DMG_SRC="$PROJECT_DIR/dist/dmg_tmp"
rm -rf "$DMG_SRC"
mkdir -p "$DMG_SRC"
cp -R "dist/$APP_NAME.app" "$DMG_SRC/"
ln -s /Applications "$DMG_SRC/"
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" \
  -srcfolder "$DMG_SRC" -ov -format UDZO -fs HFS+ "$DMG_PATH"
rm -rf "$DMG_SRC"
echo "=== Done ==="
echo "DMG: $DMG_PATH"
echo "Size: $(du -h "$DMG_PATH" | cut -f1)"
