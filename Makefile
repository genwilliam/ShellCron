.PHONY: install uninstall run deps clean

# Install dependencies
deps:
	pip install -r requirements.txt

# Install ShellCron service
install: deps
	python3 -m daemon --install

# Uninstall ShellCron (removes service + data)
uninstall:
	python3 -m daemon --uninstall

# Start the GUI
run:
	python3 -m gui

# Start the daemon (foreground)
daemon:
	python3 -m daemon

# Clean cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
