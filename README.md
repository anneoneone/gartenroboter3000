# 🌱 Gartenroboter3000

Raspberry Pi-based garden automation system with intelligent watering control.

**📖 Contents:** [Quick Start](#-quick-start) · [Features](#features) · [Hardware](#hardware-requirements) · [Installation](#installation) · [Configuration](#configuration) · [Telegram Bot](#telegram-bot-commands) · [Troubleshooting](#troubleshooting) · [Development](#development)

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000

# 2. Install uv (modern Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install dependencies
uv sync

# 4. Copy and configure environment
cp .env.example .env
# Edit .env with your Telegram bot token and OpenWeather API key

# 5. Run in mock mode (no hardware required)
uv run gartenroboter --mock --debug

# 6. Test your Telegram bot - send /status to your bot!
```

## Features

- **4x Soil Moisture Monitoring** — Capacitive sensors for each garden zone
- **Smart Watering** — Only waters after sunset when soil is dry
- **Rain Barrel Monitoring** — Ultrasonic water level sensing with low-level alerts
- **Telegram Bot Control** — Configure and monitor via Telegram
- **Weather Integration** — OpenWeather API for sunset times and conditions
- **Pi Health Monitoring** — Temperature warnings to prevent overheating
- **Data Logging** — SQLite database with 90-day retention

## Hardware Requirements

| Component | Model/Spec | Qty |
|-----------|------------|-----|
| Raspberry Pi | Pi 4 (2GB+) or Pi Zero 2 W | 1 |
| MicroSD Card | 32GB Class 10 | 1 |
| ADC Converter | MCP3008 (8-channel, 10-bit) | 1 |
| Soil Moisture Sensor | Capacitive (not resistive!) | 4 |
| Ultrasonic Sensor | HC-SR04 | 1 |
| Relay Module | 5V 1-channel with optocoupler | 1 |
| Water Pump | 12V DC submersible | 1 |
| Pump Power Supply | 12V 2A DC adapter | 1 |

## Wiring Diagram

```
Raspberry Pi GPIO Pinout:
┌─────────────────────────────────────┐
│  3V3 (1) (2) 5V                     │
│  SDA (3) (4) 5V ──────► HC-SR04 VCC │
│  SCL (5) (6) GND ─────► HC-SR04 GND │
│  GP4 (7) (8) TX                     │
│  GND (9) (10) RX                    │
│ GP17 (11) ─────────────► Pump Relay │
│ GP18 (12) (13) GP27                 │
│ GP22 (14) (15) GND                  │
│ GP23 (16) ─────────────► HC-SR04 Trigger
│ GP24 (18) ◄──[Voltage Divider]── HC-SR04 Echo
│  GND (20) (21) GP9                  │
│  CE0 (24) ─────────────► MCP3008 CS │
│ MOSI (19) ─────────────► MCP3008 DIN│
│ MISO (21) ◄────────────── MCP3008 DOUT
│ SCLK (23) ─────────────► MCP3008 CLK│
└─────────────────────────────────────┘

MCP3008 ADC Channels:
  CH0 ◄── Soil Sensor Zone 1
  CH1 ◄── Soil Sensor Zone 2
  CH2 ◄── Soil Sensor Zone 3
  CH3 ◄── Soil Sensor Zone 4
  CH4 ◄── Water Level (analog, optional)

Voltage Divider for HC-SR04 Echo (5V → 3.3V):
  Echo ──┬── 1kΩ ──► GPIO24
         └── 2kΩ ──► GND
```

## Installation

### On Raspberry Pi (Production)

```bash
# Clone repository
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000

# Run install script (installs uv, dependencies, enables SPI/I2C)
chmod +x scripts/install.sh
./scripts/install.sh

# Configure environment
cp .env.example .env
vim .env  # Edit with your API keys (see "Getting API Keys" below)

# Start the service
sudo systemctl start gartenroboter
sudo systemctl enable gartenroboter  # Auto-start on boot

# Check logs
journalctl -u gartenroboter -f
```

### On Laptop (Development)

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000
uv sync --extra dev

# Configure environment
cp .env.example .env
nano .env  # Add your Telegram token and OpenWeather API key

# Run in mock mode (simulates hardware)
uv run gartenroboter --mock --debug
```

## Getting API Keys

### 1. Telegram Bot Token

```bash
# 1. Open Telegram and search for @BotFather
# 2. Send: /newbot
# 3. Follow prompts to name your bot
# 4. Copy the token (looks like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)
# 5. Add to .env:
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 2. Your Telegram Chat ID

```bash
# 1. Search for @userinfobot on Telegram
# 2. Send any message
# 3. Copy your ID number (e.g., 123456789)
```

**Add to .env:**

```bash
# Users who can USE the bot (send /status, /water, etc.)
TELEGRAM_ALLOWED_CHAT_IDS=123456789

# Users who can ADMIN the bot (use /whitelist commands)
# For solo use: set both to your own ID
# For family: add everyone to ALLOWED, only yourself to ADMIN
TELEGRAM_ADMIN_CHAT_IDS=123456789

# Multiple users: comma-separated
# TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
```

### 3. OpenWeather API Key

```bash
# 1. Register at https://openweathermap.org/api
# 2. Go to API Keys in your account
# 3. Copy the key
# 4. Add to .env:
OPENWEATHER_API_KEY=your_api_key_here
```

### 4. Your Location

```bash
# Find your coordinates on Google Maps (right-click → "What's here?")
LOCATION_LATITUDE=52.5200
LOCATION_LONGITUDE=13.4050
LOCATION_TIMEZONE=Europe/Berlin
```

## Configuration

Configuration is managed via environment variables (`.env` file) and can be updated at runtime via Telegram bot.

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `123456:ABC...` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated list of allowed user IDs | `123456,789012` |
| `OPENWEATHER_API_KEY` | API key from openweathermap.org | `abc123...` |
| `LOCATION_LATITUDE` | Your garden's latitude | `52.5200` |
| `LOCATION_LONGITUDE` | Your garden's longitude | `13.4050` |

### Optional Settings (with defaults)

| Variable | Default | Description |
|----------|---------|-------------|
| `SENSOR_SOIL_THRESHOLD_DRY` | `30` | Soil moisture % below = dry |
| `SENSOR_WATER_LEVEL_MIN` | `15` | Water level % below = warning |
| `PUMP_MAX_RUNTIME` | `180` | Max pump runtime (seconds) |
| `PUMP_COOLDOWN` | `300` | Cooldown between cycles (seconds) |

See [.env.example](.env.example) for all configuration options.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/status` | Show all sensor values and system state |
| `/config` | View current configuration |
| `/set <key> <value>` | Update configuration value |
| `/water <zone>` | Manually trigger watering (1-4 or "all") |
| `/calibrate <sensor>` | Start sensor calibration wizard |
| `/history [hours]` | Show recent sensor readings |
| `/alerts on\|off` | Toggle notifications |
| `/help` | Show available commands |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/whitelist add <chat_id>` | Add user to whitelist |
| `/whitelist remove <chat_id>` | Remove user from whitelist |
| `/whitelist list` | Show all whitelisted users |

## Watering Logic

```
┌─────────────────────────────────────┐
│         Every 5 minutes             │
└─────────────┬───────────────────────┘
              ▼
┌─────────────────────────────────────┐
│    Is it after sunset?              │──No──► Wait
└─────────────┬───────────────────────┘
              ▼ Yes
┌─────────────────────────────────────┐
│    Is Pi temperature OK (<70°C)?    │──No──► Send warning, skip
└─────────────┬───────────────────────┘
              ▼ Yes
┌─────────────────────────────────────┐
│    Is water level OK (>15%)?        │──No──► Send alert, skip
└─────────────┬───────────────────────┘
              ▼ Yes
┌─────────────────────────────────────┐
│    For each zone:                   │
│    Is soil dry (<30%)?              │──No──► Skip zone
└─────────────┬───────────────────────┘
              ▼ Yes
┌─────────────────────────────────────┐
│    Is pump cooldown elapsed?        │──No──► Wait
└─────────────┬───────────────────────┘
              ▼ Yes
┌─────────────────────────────────────┐
│    Activate pump (max 180s)         │
│    Log event, send notification     │
└─────────────────────────────────────┘
```

## Troubleshooting

### "Bot not responding"

```bash
# Check if bot token is correct
uv run gartenroboter --mock --debug
# Look for "Telegram bot started" in output

# Verify your chat ID is whitelisted
grep TELEGRAM_ALLOWED_CHAT_IDS .env
```

### "No sensor readings"

```bash
# On Raspberry Pi: Check SPI is enabled
sudo raspi-config  # Interface Options → SPI → Enable

# Verify wiring: MCP3008 CLK=GPIO11, MOSI=GPIO10, MISO=GPIO9, CS=GPIO8
```

### "Permission denied on GPIO"

```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER
# Log out and back in
```

### "uv: command not found"

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# Reload shell
source ~/.bashrc  # or ~/.zshrc on macOS
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=gartenroboter --cov-report=html

# Lint and format
uv run ruff check src tests
uv run ruff format src tests

# Type checking
uv run mypy src

# Run in mock mode with debug output
uv run gartenroboter --mock --debug
```

### Making Changes

1. **Add a new sensor type**: Extend `src/gartenroboter/core/sensors.py`
2. **Add a new Telegram command**: Add handler in `src/gartenroboter/services/telegram/handlers.py`
3. **Change watering logic**: Modify `src/gartenroboter/core/watering.py`

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_pump.py

# Run with verbose output
uv run pytest -v

# Run and stop on first failure
uv run pytest -x
```

## Project Structure

```
gartenroboter3000/
├── src/gartenroboter/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── app.py               # Application factory
│   ├── config/
│   │   ├── settings.py      # Pydantic settings
│   │   └── validation.py    # Config validators
│   ├── core/
│   │   ├── sensors.py       # Sensor reading logic
│   │   ├── pump.py          # Pump control
│   │   └── watering.py      # Decision engine
│   ├── services/
│   │   ├── weather.py       # OpenWeather client
│   │   ├── sun.py           # Sunset calculation
│   │   └── telegram.py      # Telegram bot
│   └── infra/
│       ├── gpio.py          # GPIO abstraction
│       ├── database.py      # SQLite layer
│       └── scheduler.py     # Async task scheduler
├── tests/
├── scripts/
│   └── install.sh
├── systemd/
│   └── gartenroboter.service
├── pyproject.toml
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read the contributing guidelines first.

---

Made with 🌻 for garden automation
