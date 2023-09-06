PYTHON ?= python3
PY_PATH=$(PWD)/src
RUN_PY = PYTHONPATH=$(PY_PATH) $(PYTHON) -m
BLACK_CMD = $(RUN_PY) black --line-length 100 .
# NOTE: exclude any virtual environment subdirectories here
PY_FIND_COMMAND = find -name '*.py' ! -path './venv/*'
MYPY_CONFIG=$(PY_PATH)/mypy_config.ini

init:
	$(PYTHON) -m venv venv
	source ./venv/bin/activate

install:
	pip3 install -r requirements.txt

format: isort
	$(BLACK_CMD)

check_format:
	$(BLACK_CMD) --check --diff

mypy:
	$(RUN_PY) mypy $(shell $(PY_FIND_COMMAND)) --config-file $(MYPY_CONFIG) --no-namespace-packages

pylint:
	$(RUN_PY) pylint $(shell $(PY_FIND_COMMAND))

autopep8:
	autopep8 --in-place --aggressive --aggressive $(shell $(PY_FIND_COMMAND))

isort:
	isort $(shell $(PY_FIND_COMMAND))

lint: check_format mypy pylint

test:
# $(RUN_PY) unittest discover -s test -p *_test.py -v
# Uncomment and tab over to run individual tests
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_uuid
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_finding_interval
	$(RUN_PY) unittest test.tgtg_test.TgtgTest.test_conversion_timezone
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_get_intervals_from_start_time
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_timezone_changes
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_time_within_divisors_of_24
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_time_all_starts_within_interval
# $(RUN_PY) unittest test.tgtg_test.TgtgTest.test_time_all_starts_outside_interval


run_worker_dev:
	$(RUN_PY) executables.tgtg_worker --mode dev --time-between-loop 60 --verbose

run_worker_prod:
	$(RUN_PY) executables.tgtg_worker --mode prod

create_account:
	$(RUN_PY) executables.tgtg_api_setup --email $(email)

reset_monitor:
	$(RUN_PY) executables.reset_monitor

clean:
	rm -rf *.pickle

.PHONY: init install format check_format mypy pylint autopep8 isort lint test run_worker create_account clean
