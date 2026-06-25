.PHONY: test
.PHONY: seed
.PHONY: serve
.PHONY: smoke

test:
	python3 -m unittest discover -s tests

seed:
	python3 -m cargopilot.seed

serve:
	python3 -m cargopilot.web

smoke:
	python3 -m unittest discover -s tests
	python3 -m cargopilot.seed --db /tmp/cargopilot-smoke.sqlite3
