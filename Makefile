.PHONY: build build-base build-master build-minion up down logs logs-master logs-minion test clean

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE_FILE := docker/docker-compose.yml
BASE_IMAGE := passwords-cracker-base:latest

help:
	@echo "Available targets:"
	@echo "  build          - Build all images (base, master, minion)"
	@echo "  build-base     - Build base image only"
	@echo "  build-master   - Build master image only"
	@echo "  build-minion   - Build minion image only"
	@echo "  up             - Start all services"
	@echo "  up-scale       - Start services with 5 minions (docker-compose up --scale minion=5)"
	@echo "  down           - Stop all services"
	@echo "  logs           - Show logs from all services"
	@echo "  logs-master    - Show logs from master only"
	@echo "  logs-minion    - Show logs from minion only"
	@echo "  test           - Run tests"
	@echo "  clean          - Remove all containers, networks, and images"
	@echo "  clean-all       - Clean everything including volumes"

build-base:
	@echo "Building base image..."
	docker build -f docker/Dockerfile.base -t $(BASE_IMAGE) ..

build-master: build-base
	@echo "Building master image..."
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE) -f docker/Dockerfile.master -t passwords-cracker-master:latest ..

build-minion: build-base
	@echo "Building minion image..."
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE) -f docker/Dockerfile.minion -t passwords-cracker-minion:latest ..

build: build-base build-master build-minion
	@echo "All images built successfully!"

up:
	@echo "Starting services..."
	cd docker && docker-compose up -d
	@echo "Services started. Use 'make logs' to view logs."

up-scale:
	@echo "Starting services with 5 minions..."
	cd docker && docker-compose up -d --scale minion=5
	@echo "Services started with 5 minions. Use 'make logs' to view logs."

down:
	@echo "Stopping services..."
	cd docker && docker-compose down
	@echo "Services stopped."

logs:
	cd docker && docker-compose logs -f

logs-master:
	cd docker && docker-compose logs -f master

logs-minion:
	cd docker && docker-compose logs -f minion

test:
	@echo "Running tests..."
	python -m pytest tests/ -v

clean:
	@echo "Cleaning up containers and networks..."
	cd docker && docker-compose down -v --remove-orphans
	@echo "Cleanup complete."

clean-all: clean
	@echo "Removing images..."
	docker rmi passwords-cracker-base:latest passwords-cracker-master:latest passwords-cracker-minion:latest 2>/dev/null || true
	@echo "All cleanup complete."

