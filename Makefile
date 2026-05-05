.PHONY: start stop restart logs errors test health dev

start:
	launchctl load ~/Library/LaunchAgents/com.rickarmbrust.things-agent.plist

stop:
	launchctl unload ~/Library/LaunchAgents/com.rickarmbrust.things-agent.plist

restart: stop start

logs:
	tail -f ~/Dev/alfred/logs/stdout.log

errors:
	tail -f ~/Dev/alfred/logs/stderr.log

test:
	cd ~/Dev/alfred && uv run pytest -v

health:
	curl -s http://127.0.0.1:8200/api/v1/health | python3 -m json.tool

dev:
	cd ~/Dev/alfred && uv run uvicorn src.main:app --host 127.0.0.1 --port 8200 --reload
