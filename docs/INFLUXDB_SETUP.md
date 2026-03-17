# InfluxDB Setup Guide for Gartenroboter3000

This guide explains how to set up InfluxDB on your Raspberry Pi 4 to store sensor metrics and watering events in a time-series database.

**Table of Contents:**
- [What is InfluxDB?](#what-is-influxdb)
- [System Requirements](#system-requirements)
- [Installation Steps](#installation-steps)
- [Initial Configuration](#initial-configuration)
- [Gartenroboter3000 Integration](#gartenroboter3000-integration)
- [Querying Data](#querying-data)
- [Grafana Visualization (Optional)](#grafana-visualization-optional)
- [Troubleshooting](#troubleshooting)

---

## What is InfluxDB?

InfluxDB is an open-source time-series database optimized for storing and querying metrics with timestamps. It's perfect for:
- **High-frequency sensor data** (soil moisture, temperature, pressure readings)
- **Event tracking** (when pump started/stopped, watering cycles)
- **Historical trend analysis** (seasonal patterns, long-term monitoring)
- **Real-time analytics** with Grafana dashboards

**Why use InfluxDB with Gartenroboter3000?**

| Storage Solution | Pros | Cons |
|---|---|---|
| **SQLite** (current) | Simple, single-file database | Time-series optimization limited |
| **InfluxDB** (optional addon) | Optimized for metrics, efficient storage, better queries | Extra disk space, separate process |
| **Both together** | Flexibility + performance optimization | Slightly higher resource usage |

---

## System Requirements

**Raspberry Pi 4 Specifications:**
- 2GB RAM minimum (4GB+ recommended for InfluxDB + Gartenroboter)
- 32GB microSD card or larger
- Storage requirement: ~100-200MB for InfluxDB binary + data (~50MB for 30 days of sensor data)

**Network:**
- Local network access (InfluxDB listens on port 8086 by default)
- No internet required (InfluxDB is self-contained)

---

## Installation Steps

### Step 1: Update System Package Manager

```bash
sudo apt update
sudo apt upgrade -y
```

### Step 2: Install InfluxDB 2.x (Recommended Latest)

Raspberry Pi 4 with 32-bit OS:

```bash
# Download InfluxDB 2.x for ARM (32-bit)
wget https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.4_linux_armv7.tar.gz

# Extract to /tmp
cd /tmp
tar xzf influxdb2-2.7.4_linux_armv7.tar.gz

# Copy binary to system path
sudo cp influxdb2-2.7.4/influxd /usr/local/bin/
sudo chmod +x /usr/local/bin/influxd

# Verify installation
influxd version
```

**For 64-bit OS:**

```bash
# Download for ARM64
wget https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.4_linux_arm64.tar.gz

cd /tmp
tar xzf influxdb2-2.7.4_linux_arm64.tar.gz
sudo cp influxdb2-2.7.4/influxd /usr/local/bin/
sudo chmod +x /usr/local/bin/influxd
```

### Step 3: Create InfluxDB User and Directory

```bash
# Create influxdb user (non-root for security)
sudo useradd -m -s /bin/false influxdb

# Create data directory
sudo mkdir -p /var/lib/influxdb
sudo chown -R influxdb:influxdb /var/lib/influxdb
sudo chmod 700 /var/lib/influxdb

# Create config directory
sudo mkdir -p /etc/influxdb
sudo chown -R influxdb:influxdb /etc/influxdb
```

### Step 4: Create Systemd Service File

Create `/etc/systemd/system/influxdb.service`:

```bash
sudo nano /etc/systemd/system/influxdb.service
```

Add this content:

```ini
[Unit]
Description=InfluxDB Time Series Database
Requires=network-online.target
After=network-online.target
StartLimitIntervalSec=3000
StartLimitBurst=10

[Service]
Type=simple
User=influxdb
Group=influxdb

ExecStart=/usr/local/bin/influxd --http-bind-address :8086 \
  --engine-path /var/lib/influxdb \
  --log-level info

WorkingDirectory=/var/lib/influxdb
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/influxdb/influxdb.log
StandardError=append:/var/log/influxdb/influxdb.log

# Limits for Raspberry Pi (prevent resource exhaustion)
MemoryLimit=500M
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Create log directory:

```bash
sudo mkdir -p /var/log/influxdb
sudo chown -R influxdb:influxdb /var/log/influxdb
sudo chmod 755 /var/log/influxdb
```

### Step 5: Enable and Start InfluxDB Service

```bash
# Enable service to start on boot
sudo systemctl enable influxdb

# Start the service
sudo systemctl start influxdb

# Check status
sudo systemctl status influxdb

# View logs
sudo journalctl -u influxdb -n 20
```

### Step 6: Verify InfluxDB is Running

```bash
# Check port 8086
ss -tlnp | grep 8086

# Or make a test request
curl http://localhost:8086/api/v2/setup
# Should return: {"allowed":true} if not initialized, or setup status
```

---

## Initial Configuration

### Step 1: Access InfluxDB Web UI

Open a browser on your computer and navigate to:

```
http://<raspberry-pi-ip>:8086
```

Replace `<raspberry-pi-ip>` with your Pi's IP address (e.g., `192.168.1.100`).

### Step 2: Run InfluxDB Setup Wizard

The first time you access the UI, you'll see a setup page. Follow these steps:

1. **Organization Name:** `gartenroboter`
2. **Bucket Name:** `garden_metrics`
3. **Username:** Create an account (e.g., `admin`)
4. **Password:** Create a strong password
5. **Click Finish Setup**

### Step 3: Generate API Token

After setup, create a token for Gartenroboter3000:

1. Click **Data** (left sidebar)
2. Click **API Tokens** tab
3. Click **Generate Token** → **Read/Write Bucket**
4. Select bucket: `garden_metrics`
5. Token name: `gartenroboter-app`
6. Copy the token

**Example token (DO NOT USE - for reference only):**
```
xYz_12345abcDEF67890_qWerTyUiOpAsdfGHjklZxCvBnM==
```

---

## Gartenroboter3000 Integration

### Step 1: Update Environment Configuration

Edit your `.env` file:

```bash
nano .env
```

Add or uncomment the InfluxDB section:

```dotenv
# ============================================================
# INFLUXDB CONFIGURATION
# ============================================================
# Enable InfluxDB
INFLUXDB_ENABLED=true

# InfluxDB server URL (local Raspberry Pi)
INFLUXDB_URL=http://localhost:8086

# API token (from Step 3 above)
INFLUXDB_TOKEN=xYz_12345abcDEF67890_qWerTyUiOpAsdfGHjklZxCvBnM==

# Organization name (from Step 2)
INFLUXDB_ORG=gartenroboter

# Bucket name (from Step 2)
INFLUXDB_BUCKET=garden_metrics

# Write timeout (default: 10 seconds)
INFLUXDB_TIMEOUT_SECONDS=10
```

### Step 2: Install Python InfluxDB Client

Gartenroboter3000 already includes the `influxdb-client` dependency in `pyproject.toml`. Just ensure your environment is updated:

```bash
cd ~/gartenroboter3000

# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

### Step 3: Restart Gartenroboter Service

```bash
# If using systemd
sudo systemctl restart gartenroboter

# Or if running manually
# Stop the current process (Ctrl+C) and restart
python -m gartenroboter
```

### Step 4: Verify Data is Being Recorded

After a few minutes of operation, check if data is arriving:

1. Open InfluxDB UI: `http://<pi-ip>:8086`
2. Click **Data** (left sidebar)
3. Click **Explore** tab
4. Select:
   - **FROM:** `garden_metrics` bucket
   - **MEASUREMENT:** `soil_humidity`, `watertank_level`, `pi_temperature`, etc.
5. Click **SUBMIT**

You should see time-series data points appearing!

---

## Querying Data

### Flux Query Language

InfluxDB uses **Flux** for querying (similar to SQL but for time-series):

**Example 1: Last 24 hours of soil humidity**

```flux
from(bucket: "garden_metrics")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "soil_humidity")
  |> sort(columns: ["_time"], desc: true)
```

**Example 2: Average air temperature per zone**

```flux
from(bucket: "garden_metrics")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "air_temperature")
  |> aggregateWindow(every: 1h, fn: mean)
```

**Example 3: Pump runtime statistics**

```flux
from(bucket: "garden_metrics")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "pump_runtime")
  |> stats(mode: "mean")
```

### Via InfluxDB CLI

```bash
# Connect to InfluxDB (requires token)
influx --host http://localhost:8086 \
       --token xYz_12345abcDEF... \
       --org gartenroboter

# List buckets
bucket list

# List measurements
bucket get garden_metrics

# Query example
query '
from(bucket: "garden_metrics") 
  |> range(start: -1h) 
  |> filter(fn: (r) => r._measurement == "soil_humidity")
'
```

---

## Grafana Visualization (Optional)

Grafana creates beautiful dashboards from InfluxDB data.

### Step 1: Install Grafana

```bash
sudo apt install -y grafana-server

# OR from Docker (if Docker installed)
docker run -d \
  -p 3000:3000 \
  --name grafana \
  -e "GF_SECURITY_ADMIN_PASSWORD=your-password" \
  grafana/grafana
```

### Step 2: Access Grafana

```
http://<raspberry-pi-ip>:3000
```

Default login: `admin` / `admin`

### Step 3: Add InfluxDB Data Source

1. Click **Configuration** (gear icon)
2. Click **Data Sources**
3. Click **Add data source**
4. Select **InfluxDB**
5. Configure:
   - **URL:** `http://localhost:8086`
   - **Organization:** `gartenroboter`
   - **Token:** (paste your API token)
   - **Bucket:** `garden_metrics`
6. Click **Save & Test**

### Step 4: Create Example Dashboard

1. Click **Create** → **Dashboard**
2. Click **Add a new panel**
3. Set data source to InfluxDB
4. Write a Flux query (see above)
5. Choose visualization (Line Graph, Gauge, Stat, etc.)
6. Save dashboard

**Example visualization queries:**
- Soil moisture trend (line chart)
- Water tank level gauge
- Pi temperature (with warning threshold)
- Pump runtime statistics (bar chart)

---

## Troubleshooting

### InfluxDB Won't Start

```bash
# Check service status
sudo systemctl status influxdb

# View detailed logs
sudo journalctl -u influxdb -n 50

# Check port is free
sudo ss -tlnp | grep 8086

# Try manual start for debugging
sudo -u influxdb /usr/local/bin/influxd --http-bind-address :8086 --engine-path /var/lib/influxdb
```

### Data Not Appearing in InfluxDB

1. **Check Gartenroboter logs:**
   ```bash
   sudo journalctl -u gartenroboter -n 50
   # Look for "Wrote X metrics to InfluxDB" messages
   ```

2. **Verify environment variables:**
   ```bash
   grep INFLUXDB /etc/default/gartenroboter  # If using systemd env file
   # Or from gartenroboter directory:
   cat .env | grep INFLUXDB
   ```

3. **Check network connectivity:**
   ```bash
   curl http://localhost:8086/api/v2/setup
   ```

4. **Verify token is valid:**
   - Delete token and generate new one in InfluxDB UI
   - Update `.env` and restart Gartenroboter

### InfluxDB Using Too Much Disk Space

Check database size:

```bash
du -sh /var/lib/influxdb

# If > 500MB, consider deleting old data
# In InfluxDB UI: Data → Buckets → Edit → Set retention policy
```

### High Memory Usage on Pi

InfluxDB can use 200-500MB RAM. If Pi is tight on memory:

1. **Reduce sensor polling frequency:**
   ```bash
   # In .env
   SCHEDULER_SENSOR_INTERVAL=30  # Instead of 15
   ```

2. **Limit InfluxDB memory in systemd service:**
   ```ini
   # Edit /etc/systemd/system/influxdb.service
   MemoryLimit=300M
   ```

3. **Set aggressive data retention:**
   ```
   InfluxDB UI → Buckets → Edit → Set retention to 7 days
   ```

### Connection to InfluxDB Fails

**Error:** `Failed to write metrics to InfluxDB`

1. **Check token:** Tokens expire after 90 days by default
   - Generate new token in InfluxDB UI
   - Update `.env`
   - Restart Gartenroboter

2. **Check URL:** Must be resolvable
   ```bash
   curl http://localhost:8086/health
   # Should return 200 OK
   ```

3. **Check firewall** (if accessing from another computer):
   ```bash
   sudo ufw allow 8086
   ```

---

## Performance Tips

**For Raspberry Pi 4 with limited resources:**

1. **Adjust retention policy:**
   ```
   InfluxDB UI → Buckets → garden_metrics → Edit
   Set retention to 14-30 days instead of unlimited
   ```

2. **Downsampling old data** (advanced):
   Create a task to aggregate data older than 30 days:
   ```flux
   option task = {
     name: "downsample_old_data",
     every: 24h,
   }
   
   from(bucket: "garden_metrics")
     |> range(start: -60d, stop: -30d)
     |> aggregateWindow(every: 1h, fn: mean)
     |> to(bucket: "garden_metrics_archive")
   ```

3. **Monitor Pi system resources:**
   ```bash
   free -h          # Memory usage
   df -h            # Disk usage
   top -u influxdb  # InfluxDB process details
   ```

---

## Next Steps

- **Monitor your garden** with Grafana dashboards
- **Set up alerts** in Grafana for abnormal values
- **Export data** for external analysis (Excel, Python, etc.)
- **Archive data** to cloud storage (AWS S3, Google Cloud, etc.)

---

## References

- [InfluxDB Official Docs](https://docs.influxdata.com/influxdb/v2/)
- [Flux Query Language](https://docs.influxdata.com/flux/)
- [Grafana + InfluxDB Integration](https://grafana.com/docs/grafana/latest/datasources/influxdb/)
- [InfluxDB on Raspberry Pi Guide](https://medium.com/@tcharl/install-influxdb-on-raspberry-pi-a-complete-guide-15e4e8e6f097)
