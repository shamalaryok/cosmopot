COMPOSE ?= docker compose
ENV_FILE ?= .env.docker

.PHONY: help up down restart destroy logs ps tail connectivity seed status load-test

help:
    @echo "Available commands:"
    @echo "  make up            # Build and start the entire stack in the background"
    @echo "  make down          # Stop the stack"
    @echo "  make destroy       # Stop the stack and remove named volumes"
    @echo "  make logs          # Tail logs for every service"
    @echo "  make tail SERVICE=backend  # Tail logs for a specific service"
    @echo "  make ps            # Show container status"
    @echo "  make connectivity  # Run HTTP connectivity checks against nginx"
    @echo "  make load-test     # Run load tests against the API"

up:
    $(COMPOSE) --env-file $(ENV_FILE) up -d --build

down:
    $(COMPOSE) --env-file $(ENV_FILE) down

restart:
    $(MAKE) down
    $(MAKE) up

logs:
    $(COMPOSE) --env-file $(ENV_FILE) logs -f --tail=200

ps:
    $(COMPOSE) --env-file $(ENV_FILE) ps

TAIL_SERVICE ?= backend

tail:
    $(COMPOSE) --env-file $(ENV_FILE) logs -f --tail=200 $(TAIL_SERVICE)

destroy:
    $(COMPOSE) --env-file $(ENV_FILE) down -v

connectivity:
    ./scripts/connectivity_check.py

load-test:
    ./scripts/run_load_tests.sh
