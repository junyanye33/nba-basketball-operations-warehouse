.PHONY: install smoke test init-db run-date replay reconcile

install:
	pip install -r requirements.txt
	pip install -e .

smoke:
	python -m nba_warehouse.cli smoke

test:
	pytest -q

init-db:
	python -m nba_warehouse.cli init-db

run-date:
	python -m nba_warehouse.cli run-date --date $(DATE)

replay:
	python -m nba_warehouse.cli replay --start-date $(START) --end-date $(END)

reconcile:
	python -m nba_warehouse.cli reconcile --date $(DATE)
