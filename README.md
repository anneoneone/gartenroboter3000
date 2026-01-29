# 🌱 Gartenroboter3000

Raspberry Pi-based garden automation system with intelligent watering control.

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

### Prerequisites

- Raspberry Pi OS (64-bit recommended)
- Python 3.11+
- SPI enabled (`sudo raspi-config` → Interface Options → SPI)

### Quick Install

```bash
# Clone repository
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000

# Run install script
chmod +x scripts/install.sh
./scripts/install.sh

# Configure environment
cp .env.example .env
vim .env  # Edit with your settings

# Start the service
sudo systemctl start gartenroboter
sudo systemctl enable gartenroboter  # Auto-start on boot
```

### Manual Install (Development)

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,pi]"

# Run in mock mode (no hardware)
MOCK_MODE=true python -m gartenroboter
```

## Configuration

Configuration is managed via environment variables (`.env` file) and can be updated at runtime via Telegram bot.

### Required Settings

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated list of allowed user IDs |
| `OPENWEATHER_API_KEY` | API key from openweathermap.org |
| `LOCATION_LATITUDE` | Your garden's latitude |
| `LOCATION_LONGITUDE` | Your garden's longitude |

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

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=gartenroboter --cov-report=html

# Lint and format
ruff check src tests
ruff format src tests

# Type checking
mypy src

# Run in mock mode
MOCK_MODE=true LOG_LEVEL=DEBUG python -m gartenroboter
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
