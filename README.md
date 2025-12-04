# Distributed Password Cracker

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
│   │   └── worker.py      # Unified password cracking worker (sequential & parallel)
│   └── infrastructure/    # Infrastructure layer
│       └── cancellation.py
│
├── shared/                # Shared code
│   ├── domain/            # Domain models and constants
│   │   ├── models.py
│   │   ├── status.py
│   │   └── consts.py      # Constants (ResultStatus, PasswordSchemeName, etc.)
│   ├── interfaces/        # Abstract interfaces
│   │   └── password_scheme.py
│   ├── implementations/  # Concrete implementations
│   │   └── schemes/
│   ├── factories/         # Factory functions
│   │   └── scheme_factory.py
│   └── config/            # Configuration
│       └── config.py
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

-  Communication via REST only
-  Splitting workload even for a single hash
-  Resilient to failures (master/minions crash)
-  Real cancellation (minion-side early stop)
-  Circuit breaker per minion
-  Idempotent job completion
-  Caching of cracked passwords
-  Configurable via environment variables
-  Multi-threaded parallel processing within minions

## Configuration

All configuration is done via environment variables in `shared/config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | 100000 | How many indices per chunk |
| `CANCELLATION_CHECK_EVERY` | 5000 | Worker checks cancel every N iterations |
| `WORKER_THREADS` | 2 | Number of threads per minion (1 = sequential, 2 = balanced, >2 = high performance) |
| `MINION_SUBRANGE_MIN_SIZE` | 1000 | Minimum subrange size per thread in parallel mode (larger = less overhead, smaller = more parallelism) |
| `MAX_CONCURRENT_JOBS` | 3 | Maximum number of hash jobs to process in parallel (default: min(3, num_minions)) |
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

Output is written to a JSON file where each hash is a key with the following structure:

```json
{
  "hash_value": {
    "cracked_password": "password_if_found_or_null",
    "status": "FOUND|NOT_FOUND|FAILED",
    "job_id": "job_id_string"
  }
}
```

**Status values:**
- `FOUND` - Password was found
- `NOT_FOUND` - Password not in search space (valid hash, searched but not found)
- `INVALID_INPUT` - Invalid input (invalid hash format, unknown scheme, or range out of bounds)
- `FAILED` - Job failed (infrastructure issue, exceeded retries)

**Example:**
```json
{
  "1d0b28c7e3ef0ba9d3c04a4183b576ac": {
    "cracked_password": "050-0000000",
    "status": "FOUND",
    "job_id": "abc12345-..."
  },
  "a1b2c3d4e5f6789012345678901234ab": {
    "cracked_password": null,
    "status": "NOT_FOUND",
    "job_id": "def67890-..."
  },
  "invalid_hash_format_123": {
    "cracked_password": null,
    "status": "INVALID_INPUT",
    "job_id": "xyz99999-..."
  },
  "ffffffffffffffffffffffffffffffff": {
    "cracked_password": null,
    "status": "FAILED",
    "job_id": "ghi11111-..."
  }
}
```

**Note:** Console output still shows human-readable format: `<hash> <password> <job_id>` or `<hash> NOT_FOUND <job_id>` or `<hash> INVALID_INPUT <job_id>` or `<hash> FAILED <job_id>`

## How to Run

### Local Development

#### Step 1: Install Dependencies

```powershell
py -m pip install -r requirements.txt
```

**Note:** On Windows, use `py -m pip` instead of `pip`. If that doesn't work, try `python -m pip`.

#### Step 2: Create Input File

Create a file `data/input.txt` with MD5 hashes (one per line):

```powershell
# Create data directory if it doesn't exist
mkdir -p data

# Create input file with test hashes
# Example: echo "1d0b28c7e3ef0ba9d3c04a4183b576ac" > data/input.txt
```

**Input file format:**
- One MD5 hash per line (32 hex characters)
- Empty lines are ignored
- Invalid hashes are written to output with `INVALID_INPUT` status (not skipped)
- Example:
  ```
  1d0b28c7e3ef0ba9d3c04a4183b576ac
  a1b2c3d4e5f6789012345678901234ab
  ffffffffffffffffffffffffffffffff
  invalid_hash_format
  ```

#### Step 3: Start Minion Services

Open **3 separate terminal windows** and run one minion in each:

**Terminal 1 (Minion on port 8000):**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8000
```

**Terminal 2 (Minion on port 8001):**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8001
```

**Terminal 3 (Minion on port 8002):**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8002
```

**Note:** Keep these terminals open while running the master. You should see FastAPI startup messages like:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

#### Step 4: Configure and Run Master

Open a **4th terminal window** and run:

```powershell
# Set minion URLs (comma-separated)
$env:MINION_URLS = "http://localhost:8000,http://localhost:8001,http://localhost:8002"

# Set output file path
$env:OUTPUT_FILE = "data/output.txt"

# Optional: Tune performance settings
$env:CHUNK_SIZE = "50000"                    # Smaller chunks = more parallelism
$env:CANCELLATION_CHECK_EVERY = "10000"      # Check cancellation every N iterations
$env:MAX_CONCURRENT_JOBS = "3"               # Process 3 hashes in parallel

# Run the master
py main.py data/input.txt
```

**Output:**
- Results are written to `data/output.txt`
- Progress is logged to the console
- Each hash gets one line: `<hash> <password> <job_id>` (FOUND), `<hash> NOT_FOUND <job_id>`, `<hash> INVALID_INPUT <job_id>`, or `<hash> FAILED <job_id>`

#### Quick Start (Minimal Setup)

For a quick test with just 2 minions:

**Terminal 1:**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8000
```

**Terminal 2:**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8001
```

**Terminal 3 (Master):**
```powershell
$env:MINION_URLS = "http://localhost:8000,http://localhost:8001"
$env:OUTPUT_FILE = "data/output.txt"
py main.py data/input.txt
```

#### Stopping Services

- **Minions**: Press `CTRL+C` in each minion terminal
- **Master**: Press `CTRL+C` in the master terminal (or it will exit when done)

### Docker

```powershell
cd docker
docker-compose up --build
```

**Note:** For local development, use `py -m pip` instead of `pip` on Windows.

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
- FOUND / NOT_FOUND / INVALID_INPUT / FAILED / CANCELLED
- Output lines

## Status Codes

### ResultStatus Enum
- `FOUND` - Password successfully cracked
- `NOT_FOUND` - Valid hash searched but password not found in search space
- `INVALID_INPUT` - Invalid input (hash format, scheme, or range validation failed)
- `ERROR` - Internal error during processing
- `CANCELLED` - Job was cancelled (typically after password found)

### OutputStatus
- `FOUND` - Password found (same as ResultStatus.FOUND)
- `NOT_FOUND` - Password not found (same as ResultStatus.NOT_FOUND)
- `INVALID_INPUT` - Invalid input detected (same as ResultStatus.INVALID_INPUT)
- `FAILED` - Job failed after exhausting retries
