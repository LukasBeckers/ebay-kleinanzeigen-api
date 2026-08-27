.PHONY: test test-live install-dev

install-dev:
	pip install -r requirements-dev.txt

test:
	python -m pytest tests/ -q

test-live:
	python -m pytest tests/ -m live -q
