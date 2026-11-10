.PHONY: check start stop restart status logs build backup

check:
	./deploy/check-environment.sh

build:
	docker compose build

start:
	./deploy/start.sh

stop:
	./deploy/stop.sh

restart:
	./deploy/restart.sh

status:
	./deploy/status.sh

logs:
	./deploy/logs.sh

backup:
	./deploy/backup.sh
