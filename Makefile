PYTHON ?= python3
PY_PATH=$(PWD)/src
RUN_PY = PYTHONPATH=$(PY_PATH) $(PYTHON) -m
BLACK_CMD = $(RUN_PY) black --line-length 100 .
# NOTE: exclude any virtual environment subdirectories here
PY_FIND_COMMAND = find -name '*.py' ! -path './venv/*'
MYPY_CONFIG=$(PY_PATH)/mypy_config.ini

init:
	$(PYTHON) -m venv venv

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
	$(RUN_PY) unittest discover -s test -p *_test.py -v

run_worker_dev:
	$(RUN_PY) executables.tgtg_worker --mode dev --time-between-loop 15 --verbose --use-proxies

run_worker_prod:
	$(RUN_PY) executables.tgtg_worker --mode prod --time-between-loop 20 --use-proxies

create_account:
	$(RUN_PY) executables.tgtg_api_setup --email $(email) --number-of-credentials $(emails)

reset_monitor:
	$(RUN_PY) executables.reset_monitor $(ARGS)

test_run:
	$(RUN_PY) executables.test_uploads $(ARGS)

run_search:
	$(RUN_PY) search_context.executables.run_searcher $(ARGS)

clean:
	rm -rf *.pickle
	rm -rf ./venv
	rm -rf ./logs
	rm -rf .mypy_cache

.PHONY: init
.PHONY: install
.PHONY: format
.PHONY: check_format
.PHONY: mypy
.PHONY: pylint
.PHONY: autopep8
.PHONY: isort
.PHONY: lint
.PHONY: test
.PHONY: run_worker_dev
.PHONY: run_worker_prod
.PHONY: create_account
.PHONY: reset_monitor
.PHONY: test_run
.PHONY: clean
