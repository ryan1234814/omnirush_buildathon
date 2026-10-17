.PHONY: test

test:
	cd backend && uv run --offline pytest && uv run --offline ruff check .
	cd frontend && npm run build
