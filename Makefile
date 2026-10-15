.PHONY: setup up down logs dev test clean
setup:
	cp -n .env.example .env || true
up:
	docker compose up --build -d
logs:
	docker compose logs -f voice-foundry
down:
	docker compose down
dev:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
test:
	python -m pytest -q
clean:
	docker compose down
