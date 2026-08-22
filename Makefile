.PHONY: install smoke test init-db run-date run-season replay reconcile case-study

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

run-season:
	python -m nba_warehouse.cli run-season

replay:
	python -m nba_warehouse.cli replay --start-date $(START) --end-date $(END)

reconcile:
	python -m nba_warehouse.cli reconcile --date $(DATE)

case-study:
	python scripts/build_case_study_notebook.py
