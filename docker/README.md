# Docker Deployment Guide

This directory contains Docker configuration files for the distributed password cracker.

## Quick Start

```bash
# Build all images
make build

# Start services (default: 1 minion)
make up

# Start with 5 minions
make up-scale

# View logs
make logs

# Stop services
make down
```

## Manual Commands

### Build Images

```bash
# Build base image
docker build -f docker/Dockerfile.base -t passwords-cracker-base:latest ..

# Build master image
docker build --build-arg BASE_IMAGE=passwords-cracker-base:latest -f docker/Dockerfile.master -t passwords-cracker-master:latest ..

# Build minion image
docker build --build-arg BASE_IMAGE=passwords-cracker-base:latest -f docker/Dockerfile.minion -t passwords-cracker-minion:latest ..
```

### Run with Docker Compose

```bash
cd docker

# Start with default configuration
docker-compose up -d

# Scale to 5 minions
docker-compose up -d --scale minion=5

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Configuration

### Environment Variables

Key environment variables can be set in `docker-compose.yml`:

- `WORKER_THREADS`: Number of threads per minion (default: 2)
- `MINION_SUBRANGE_MIN_SIZE`: Minimum subrange size for parallel processing (default: 1000)
- `CHUNK_SIZE`: Chunk size for work distribution (default: 100000)
- `MINION_URLS`: Comma-separated list of minion URLs (auto-configured)

### Scaling Minions

When scaling minions, update `MINION_URLS` in the master service to include all minion instances:

```yaml
environment:
  - MINION_URLS=http://minion_1:8100,http://minion_2:8100,http://minion_3:8100
```

Or use docker-compose service discovery (minion service name resolves to all instances).

## Health Checks

Minions include a health check endpoint at `/health` that returns `{"status": "ok"}`.

The master waits for minions to be healthy before starting.

## Troubleshooting

### Check Service Status

```bash
docker-compose ps
```

### View Service Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f master
docker-compose logs -f minion
```

### Rebuild Images

```bash
make clean
make build
```

### Clean Everything

```bash
make clean-all
```

