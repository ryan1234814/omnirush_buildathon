.PHONY: test phase8-check

test:
	cd backend && uv run --offline pytest && uv run --offline ruff check .
	cd frontend && npm run build

phase8-check:
	cd backend && uv run --offline python -m scripts.phase8_check
