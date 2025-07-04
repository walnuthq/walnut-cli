.PHONY: help install dev test publish clean

help:
	@echo "Walnut CLI - Build and Distribution"
	@echo ""
	@echo "Available commands:"
	@echo "  make install         Install package locally"
	@echo "  make dev            Install in development mode"
	@echo "  make test           Run tests"
	@echo "  make publish        Publish to PyPI"
	@echo "  make clean          Clean build artifacts"

install:
	pip install .

dev:
	pip install -e .
	pip install -r requirements.txt

test:
	python -m pytest tests/

publish:
	./scripts/publish-pypi.sh

clean:
	rm -rf build dist *.egg-info
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	find . -name "*.pyc" -delete
	find . -name ".DS_Store" -delete