# Installation

## Development Mode

  cd ShellCron
  uv venv --python 3.11
  uv pip install -r requirements.txt
  python -m gui

## Build macOS App

  bash build_dmg.sh

Output: dist/ShellCron.dmg

1. Open dist/ShellCron.dmg
2. Drag ShellCron.app to ~/Applications
3. Open ~/Applications/ShellCron.app

The daemon starts automatically with the app. No separate installation needed.

## Email Notification Setup (Gmail)

1. Enable 2-Step Verification on your Google account
2. Generate an App Password at https://myaccount.google.com/apppasswords
3. Open ShellCron -> Settings -> Notifications
4. Fill in:
   - SMTP Server: smtp.gmail.com
   - Port: 465
   - Username: your full Gmail address
   - Password: the 16-character App Password (no spaces)
   - Recipient: destination email address
5. Check "Send email notification"
6. Click "Send Test Email" to verify

## Uninstall

  rm -rf ~/.local/share/shellcrond
  rm -rf ~/.local/state/shellcrond
  rm -f ~/Library/LaunchAgents/com.shellcrond.plist
  rm -rf ~/Desktop/ShellCron  # project directory
