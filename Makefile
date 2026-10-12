.PHONY: install uninstall deps clean dev

# Install dependencies
deps:
	pip install -r requirements.txt

# Install project in development mode
dev: deps
	pip install -e .

# Install system service
install: dev
	shcron install

# Uninstall
uninstall:
	shcron uninstall --purge

# Start daemon (via service)
start:
	shcron start

# Stop daemon
stop:
	shcron stop

# Show status
status:
	shcron status

# Run diagnostics
doctor:
	shcron doctor

# List tasks
ls:
	shcron ls

# Run daemon in foreground (for debugging)
foreground:
	python -m shellcron.daemon

# Clean cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
