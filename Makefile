.PHONY: test
.PHONY: serve

test:
	python3 -m unittest discover -s tests

serve:
	python3 -m cargopilot.web
