# 🟣 Pentera Distributed Password Cracker

A fully distributed **Master → Minions** password-cracking system over **REST** only.

## Overview

This system reads a file of MD5 hashes, brute-forces each hash using multiple minions in parallel, splits the password space into inclusive chunks, performs retries, handles minion failure, supports cancellation, caching, circuit breaker, idempotency, and produces clean output.

## Project Structure

```
passwords-cracker/
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
├── README.md              # This file
│
├── master/                # Master service
│   ├── services/          # Business logic
│   │   ├── job_manager.py
│   │   ├── chunk_manager.py
│   │   └── scheduler.py
│   └── infrastructure/    # Infrastructure layer
│       ├── cache.py
│       ├── circuit_breaker.py
│       ├── minion_client.py
│       └── minion_registry.py
│
├── minion/                # Minion service
│   ├── api/               # API layer
│   │   └── app.py         # FastAPI application
│   ├── services/          # Business logic
│   │   ├── worker.py      # Password cracking worker
│   │   └── worker_parallel.py  # Parallel processing worker
│   └── infrastructure/    # Infrastructure layer
│       └── cancellation.py
│
├── shared/                # Shared code
│   ├── domain/            # Domain models
│   │   ├── models.py
│   │   └── status.py
│   ├── interfaces/        # Abstract interfaces
│   │   └── password_scheme.py
│   ├── implementations/  # Concrete implementations
│   │   └── schemes/
│   ├── factories/         # Factory functions
│   │   └── scheme_factory.py
│   ├── config/            # Configuration
│   │   └── config.py
│   └── consts.py          # Constants
│
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   ├── e2e/              # End-to-end tests
│   └── pytest.ini
│
├── docker/                # Docker files
└── data/                  # Data files
```

## Architecture

### Components

- **Master**: Coordinates work distribution, manages jobs and chunks, handles failures and retries
- **Minions**: FastAPI services that perform the actual password cracking work
- **Shared Layer**: Common domain models, configuration, password schemes, and status enums

### Key Features

- ✅ Communication via REST only
- ✅ Splitting workload even for a single hash
- ✅ Resilient to failures (master/minions crash)
- ✅ Clean architecture & clean code
- ✅ Real cancellation (minion-side early stop)
- ✅ Circuit breaker per minion
- ✅ Idempotent job completion
- ✅ Caching of cracked passwords
- ✅ Configurable via environment variables
- ✅ Multi-threaded parallel processing within minions

## Configuration

All configuration is done via environment variables in `shared/config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | 100000 | How many indices per chunk |
| `CANCELLATION_CHECK_EVERY` | 5000 | Worker checks cancel every N iterations |
| `WORKER_THREADS` | 2 | Number of threads per minion (1 = sequential, 2 = balanced, >2 = high performance) |
| `MAX_ATTEMPTS` | 3 | Retries per chunk |
| `MINION_REQUEST_TIMEOUT` | 5.0 | Request timeout in seconds |
| `NO_MINION_WAIT_TIME` | 0.5 | Wait time if no minion available (seconds) |
| `OUTPUT_FILE` | output.txt | Output file path |
| `MINION_URLS` | (see default) | Comma-separated list of minion URLs |
| `MINION_FAILURE_THRESHOLD` | 3 | Circuit breaker failure threshold |
| `MINION_BREAKER_OPEN_SECONDS` | 10.0 | Circuit breaker open window (seconds) |

## Input/Output

### Input Format

- Text file with **one MD5 hash per line**
- Empty lines allowed (ignored)
- Invalid hashes skipped with warning
- Hashes normalized to lowercase automatically

### Output Format

For each hash, exactly one line:
- `<hash> <password>` - Password found
- `<hash> NOT_FOUND` - Password not in search space
- `<hash> FAILED` - Job failed (infrastructure issue)

Example:
```
1d0b28c7e3ef0ba9d3c04a4183b576ac 050-0000000
a1b2c3d4e5f6789012345678901234ab NOT_FOUND
ffffffffffffffffffffffffffffffff FAILED
```

## How to Run

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare input file:**
   ```bash
   # Copy example input file
   cp data/input.txt.example data/input.txt
   # Or create your own with MD5 hashes (one per line)
   ```

3. **Start minions** (in separate terminals):
   ```powershell
   # Terminal 1
   $env:WORKER_THREADS = "2"  # Balanced (default)
   py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8000
   
   # Terminal 2
   $env:WORKER_THREADS = "2"
   py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8001
   
   # Terminal 3
   $env:WORKER_THREADS = "2"
   py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8002
   ```

4. **Set environment variables** (in a new terminal):
   ```powershell
   $env:MINION_URLS = "http://localhost:8000,http://localhost:8001,http://localhost:8002"
   $env:OUTPUT_FILE = "data/output.txt"
   
   # Optional: Optimize settings
   $env:CHUNK_SIZE = "50000"
   $env:CANCELLATION_CHECK_EVERY = "10000"
   ```

5. **Run master:**
   ```powershell
   py main.py data/input.txt
   ```

### Docker

```powershell
cd docker
docker-compose up --build
```

Output will be written to `data/output.txt`.

**Note**: Docker Compose automatically sets `WORKER_THREADS=2` for all minions (balanced configuration).

## Testing

### Running Tests

```powershell
# Run all tests
py -m pytest tests/ -v

# Run specific test categories
py -m pytest tests/unit/ -v          # Unit tests only
py -m pytest tests/integration/ -v    # Integration tests only
py -m pytest tests/e2e/ -v            # End-to-end tests only
```

### Test Structure

- **Unit Tests**: Individual components (password scheme, cache, circuit breaker, etc.)
- **Integration Tests**: API endpoints, minion-client communication
- **End-to-End Tests**: Full system flow with mocked components

## Key Behaviors

### Chunk Splitting

- Search space split into **inclusive, gap-free chunks**
- Each chunk covers `CHUNK_SIZE` indices (except last)
- Chunks processed in parallel across minions

### Retry Logic

- Chunks retry up to `MAX_ATTEMPTS` on ERROR
- CANCELLED chunks do NOT count towards retries
- Failed chunks mark job as FAILED

### Circuit Breaker

Each minion has its own circuit breaker:
- After `MINION_FAILURE_THRESHOLD` consecutive failures → Unavailable
- Remains unavailable for `MINION_BREAKER_OPEN_SECONDS` seconds
- Registry skips unavailable minions
- After window expires → breaker resets

### No Available Minions

If all minions are unavailable:
- Scheduler **waits** `NO_MINION_WAIT_TIME` seconds
- **Does NOT fail the job**
- Retries when minions become available
- Implements graceful degradation

### Idempotency

- Duplicate FOUND results after job DONE are ignored
- Late NOT_FOUND results after job DONE are ignored
- CANCELLED chunks do NOT count towards MAX_ATTEMPTS

### Cancellation

- When password is FOUND, master broadcasts cancellation to all minions
- Minions check cancellation every `CANCELLATION_CHECK_EVERY` iterations
- CANCELLED chunks are not retried

### Caching

- Cracked passwords cached in memory
- Cache checked before creating job
- Cache hit → job immediately DONE

## Performance

### Multi-Threading Support

Each minion can process chunks in parallel using multiple threads:
- **Default**: `WORKER_THREADS = 2` (balanced performance)
- With 3 minions (default): 3 × 2 = 6 total threads (~75% CPU on 8-core systems)
- **Speedup**: 2-3x on multi-core systems with balanced config

**Balanced Configuration (Recommended)**:
```powershell
$env:WORKER_THREADS = "2"  # Default: balanced (good for most systems)
```

**High Performance** (for 8+ core systems):
```powershell
$env:WORKER_THREADS = "3"  # 3 threads per minion
```

**Low Resource** (for 4 cores or less):
```powershell
$env:WORKER_THREADS = "1"  # Sequential mode
# Use 2 minions instead of 3
$env:MINION_URLS = "http://localhost:8000,http://localhost:8001"
```

### Performance Characteristics

- **Sequential Mode** (`WORKER_THREADS=1`): ~50,000-100,000 hashes/second per minion
- **Balanced Mode** (`WORKER_THREADS=2`): ~150,000-200,000 hashes/second per minion
- **High Performance** (`WORKER_THREADS=3`): ~200,000-250,000 hashes/second per minion

## Limitations

- No persistence for job state (in-memory only)
- No TLS/authentication
- No queue (HTTP only)
- Static minion list (no dynamic discovery)

## Logging

Logging uses Python's `logging` module:
- **Level**: INFO (default)
- **Format**: `%(asctime)s %(levelname)s %(name)s - %(message)s`

Important events logged:
- Job creation/completion
- Chunk creation/assignment/completion
- Retries
- Circuit breaker unavailable/available
- FOUND / NOT_FOUND / FAILED / CANCELLED
- Output lines
