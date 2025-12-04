# Quick Start Guide - Running Locally

## Prerequisites
- Python 3.8+
- pip installed

## Step-by-Step Instructions

### 1. Install Dependencies
```powershell
py -m pip install -r requirements.txt
```

**Note:** On Windows, use `py -m pip` instead of `pip`. If that doesn't work, try `python -m pip`.

### 2. Create Data Directory and Input File
```powershell
# Create data directory
mkdir data

# Create a sample input file (or use your own)
# The file should contain one MD5 hash per line
# Example: data/input.txt
```

**Example input file (`data/input.txt`):**
```
1d0b28c7e3ef0ba9d3c04a4183b576ac
a1b2c3d4e5f6789012345678901234ab
ffffffffffffffffffffffffffffffff
```

### 3. Start Minion Services

You need to start **at least 2 minions** (recommended: 3) in **separate terminal windows**.

**Terminal 1 - Minion 1 (Port 8000):**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8000
```

**Terminal 2 - Minion 2 (Port 8001):**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8001
```

**Terminal 3 - Minion 3 (Port 8002) [Optional]:**
```powershell
$env:WORKER_THREADS = "2"
py -m uvicorn minion.api.app:app --host 0.0.0.0 --port 8002
```

**Keep these terminals open!** You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4. Run the Master

Open a **new terminal** (4th terminal) and run:

```powershell
# Set minion URLs (adjust if you only have 2 minions)
$env:MINION_URLS = "http://localhost:8000,http://localhost:8001,http://localhost:8002"

# Set output file
$env:OUTPUT_FILE = "data/output.txt"

# Run the master
py main.py data/input.txt
```

**If you only have 2 minions:**
```powershell
$env:MINION_URLS = "http://localhost:8000,http://localhost:8001"
$env:OUTPUT_FILE = "data/output.txt"
py main.py data/input.txt
```

### 5. Check Results

Results are written to `data/output.txt`. Each line shows:
- `<hash> <password>` - Password found
- `<hash> NOT_FOUND` - Password not in search space
- `<hash> FAILED` - Job failed

### Stopping Services

- **Minions**: Press `CTRL+C` in each minion terminal
- **Master**: Press `CTRL+C` (or it exits automatically when done)

## Troubleshooting

### "Connection refused" errors
- Make sure all minions are running before starting the master
- Check that ports 8000, 8001, 8002 are not in use

### "No available minions" warnings
- Wait a few seconds - circuit breakers may be open
- Check minion logs for errors

### Output file not created
- Check that the `data/` directory exists
- Verify `OUTPUT_FILE` environment variable is set correctly

## Performance Tuning

**For faster processing:**
```powershell
$env:CHUNK_SIZE = "50000"              # Smaller chunks = more parallelism
$env:WORKER_THREADS = "3"               # More threads per minion (if you have 8+ cores)
$env:MAX_CONCURRENT_JOBS = "5"          # Process more hashes in parallel
```

**For lower CPU usage:**
```powershell
$env:WORKER_THREADS = "1"               # Sequential mode (1 thread per minion)
$env:CHUNK_SIZE = "100000"              # Larger chunks = less overhead
```

