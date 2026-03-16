# 🌱 Gartenroboter3000

**Optimized for Raspberry Pi 4 Model B** — Garden automation system with intelligent watering control, soil monitoring, and Telegram integration.

**📖 Contents:** [Quick Start](#-quick-start) · [Features](#features) · [Hardware](#hardware-requirements) · [Installation](#installation-raspberry-pi-4) · [Configuration](#configuration) · [Telegram Bot](#telegram-bot-commands) · [RPi 4 Optimization](#-raspberry-pi-4-model-b-optimization) · [Troubleshooting](#troubleshooting) · [Development](#development)

## ⚡ Quick Start (Raspberry Pi 4)

### Prerequisites
- Raspberry Pi 4 Model B (2GB RAM minimum, 4GB+ recommended) with 32GB microSD card
- Power supply (**5V @ 3A minimum, 5V @ 5A recommended** for USB peripherals)
- 30 minutes of setup time

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000

# 2. Run the automated install (includes uv, dependencies, GPIO setup)
chmod +x scripts/install.sh
./scripts/install.sh

# 3. Configure environment
cp .env.example .env
nano .env  # Add your Telegram token and OpenWeather API key

# 4. (If script enabled SPI/I2C) Reboot
sudo reboot

# 5. Start the service
sudo systemctl start gartenroboter
sudo systemctl enable gartenroboter  # Auto-start on boot

# 6. Verify it's running
journalctl -u gartenroboter -n 20 -f
```

## Features

- **4x Soil Moisture Monitoring** — Capacitive sensors for each garden zone
- **Smart Watering** — Only waters after sunset when soil is dry
- **Rain Barrel Monitoring** — Ultrasonic water level sensing with low-level alerts
- **Telegram Bot Control** — Configure and monitor via Telegram
- **Weather Integration** — OpenWeather API for sunset times and conditions
- **Pi Health Monitoring** — Temperature warnings to prevent overheating
- **Data Logging** — SQLite database with 90-day retention

## 🎯 Raspberry Pi 4 Model B Optimization

RPi 4 offers significant advantages over Pi Zero 2 W:

| Feature | RPi 4 (2GB) | Pi Zero 2 W |
|---------|------------|------------|
| CPU | BCM2711 (4x 1.5GHz ARM Cortex-A72) | BCM2710A1 (4x 1GHz ARM Cortex-A53) |
| RAM | 2GB LPDDR4 | 512MB/1GB |
| Storage I/O | Gigabit Ethernet | USB 2.0 (slower) |
| Temperature | Runs cooler (~50°C idle) | Gets hot under load (~65°C) |
| **Monitoring Intervals** | **15-30 seconds** (aggressive) | **60 seconds** (conservative) |
| **Data Retention** | **180 days** (large storage capacity) | **45 days** (limited storage) |

**Optimizations applied for RPi 4:**
- Shorter sensor polling intervals (15 seconds vs 60+)
- More aggressive weather API checks for real-time conditions
- Extended data retention for historical analysis
- No frequency scaling concerns (better sustained performance)
- Can safely run additional monitoring tasks in parallel

## Hardware Requirements

| Component | Model/Spec | Qty | Notes |
|-----------|------------|-----|-------|
| **Raspberry Pi** | **Raspberry Pi 4 Model B** | 1 | ✅ Officially supported (1.5GHz ARM Cortex-A72 quad-core) |
| MicroSD Card | 32GB Class 10+ (SanDisk recommended) | 1 | ~23GB usable; avoid cheap brands |
| Power Supply | **5V 3A USB-C** | 1 | ⚠️ **Critical for stability!** Low power causes random crashes |
| ADC Converter | MCP3008 (8-channel, 10-bit SPI) | 1 | Required for soil moisture sensors |
| Soil Moisture Sensor | Capacitive (not resistive!) | 4 | Resistive sensors corrode quickly |
| Water Level Sensor | HC-SR04 (ultrasonic) | 1 | Requires voltage divider (5V → 3.3V) on echo pin |
| Relay Module | 5V 1-channel with optocoupler | 1-2 | 1 for single pump, 2 for parallel dual-pump setup |
| Water Pump | 12V DC submersible | 1-2 | 2-5W typical; 2 pumps allow simultaneous watering |
| Pump Power Supply | 12V ≥2A DC adapter | 1 | Separate from Pi power (no shared ground until relay) |

### Single Pump vs Dual Pump Comparison

| Feature | Single Pump | Dual Pump Setup |
|---------|------------|-----------------|
| **Relay GPIO pins** | GPIO 17 | GPIO 17 + GPIO 27 |
| **Configuration** | `GPIO_PUMP_RELAY_PIN_2=0` | `GPIO_PUMP_RELAY_PIN_2=27` |
| **Watering time** | Serial (zones 1→2→3→4) | Parallel (1+2 simultaneous, 3+4 simultaneous) |
| **Cost** | $ | $$ (1 extra relay + 1 extra pump) |
| **Typical runtime** | 10-15 minutes per cycle | 5-8 minutes per cycle |
| **Recommended for** | Small garden (1-2 zones) | Larger garden (4 zones) |

## Wiring Diagram

### Single Pump Setup (Default)

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

### Soil Humidity Sensor Wiring (Capacitive 4-Channel)

**Soil Sensor Pin Connections:**

Each of the 4 soil sensors has 4 pins:
```
Soil Sensor Pinout:
  1. GND  ← Connect to Raspberry Pi ground (any GND pin)
  2. VCC  ← Connect to 3.3V power from Raspberry Pi (pin 1 or 17)
  3. NC   ← Leave disconnected (stands for "No Connection")
  4. SIG  ← Connect to MCP3008 analog input channel
```


```
1. GND (Pin 1 - Brown wire)
   └─ Connect to: Raspberry Pi GND (e.g., pin 6, 9, 14, 20, 25, 30, 34, or 39)

2. VCC (Pin 2 - Red wire)  
   └─ Connect to: Raspberry Pi 3.3V power (pin 1 - upper left, labeled "3V3")

3. NC (Pin 3 - Yellow/White wire)
   └─ Leave unconnected (NC = "No Connection", it's not used)

4. SIG (Pin 4 - Black wire)
   └─ Connect to ONE MCP3008 channel:
      • Zone 1 Sensor SIG → MCP3008 CH0
      • Zone 2 Sensor SIG → MCP3008 CH1
      • Zone 3 Sensor SIG → MCP3008 CH2
      • Zone 4 Sensor SIG → MCP3008 CH3
```

**MCP3008 Power Supply:**

```
MCP3008 VDD (pin 16) ──► Raspberry Pi 3.3V (pin 1)
MCP3008 VSS (pin 15 or any other GND pin) ──► Raspberry Pi GND
```

**Pin Reference Chart:**

| Soil Sensor | Purpose | Pin Type | Raspberry Pi Connection | Cable Color |
|------------|---------|----------|------------------------|-------------|
| GND | Ground return | Digital | GND (pins 6, 9, 14, 20, 25, 30, 34, 39) | Brown |
| VCC | 3.3V power | Power | 3.3V (pins 1, 17) | Red |
| NC | Not connected | — | Leave empty | (no cable) |
| SIG | Analog signal | Analog | MCP3008 CH0-CH3 | Black |

**MCP3008 SPI Communication (automatically configured):**

| MCP3008 Pin | Raspberry Pi GPIO | Purpose |
|-------------|-------------------|---------|
| CS (CE0) | GPIO 8 (pin 24) | Chip Select |
| DIN | GPIO 10 (pin 19) | Serial Data In (MOSI) |
| DOUT | GPIO 9 (pin 21) | Serial Data Out (MISO) |
| CLK | GPIO 11 (pin 23) | Serial Clock |
| VDD | 3.3V (pin 1) | Positive Supply |
| VSS | GND (pins 6, 9, 14, etc.) | Ground |

Voltage Divider for HC-SR04 Echo (5V → 3.3V):
  Echo ──┬── 1kΩ ──► GPIO24
         └── 2kΩ ──► GND
```

### Dual Pump Setup (Parallel Watering)

```
Raspberry Pi GPIO Pinout (with 2nd pump):
┌──────────────────────────────────────┐
│  3V3 (1) (2) 5V                      │
│  SDA (3) (4) 5V ──────► HC-SR04 VCC  │
│  SCL (5) (6) GND ─────► HC-SR04 GND  │
│  GP4 (7) (8) TX                      │
│  GND (9) (10) RX                     │
│ GP17 (11) ────────────► Pump 1 Relay │
│ GP18 (12) (13) GP27 ──► Pump 2 Relay │
│ GP22 (14) (15) GND                   │
│ GP23 (16) ────────────► HC-SR04 Trigger
│ GP24 (18) ◄─[Divider]─── HC-SR04 Echo
│  GND (20) (21) GP9                   │
│  CE0 (24) ────────────► MCP3008 CS   │
│ MOSI (19) ────────────► MCP3008 DIN  │
│ MISO (21) ◄───────────── MCP3008 DOUT
│ SCLK (23) ────────────► MCP3008 CLK  │
└──────────────────────────────────────┘

Zone-to-Pump Mapping (with dual pumps):
  Zone 1 (odd)   → Pump 1 (GPIO 17)
  Zone 2 (even)  → Pump 2 (GPIO 27)  ← Can water Zone 1 & 2 simultaneously!
  Zone 3 (odd)   → Pump 1 (GPIO 17)
  Zone 4 (even)  → Pump 2 (GPIO 27)  ← Can water Zone 3 & 4 simultaneously!

MCP3008 ADC Channels: (same as single pump)
  CH0 ◄── Soil Sensor Zone 1
  CH1 ◄── Soil Sensor Zone 2
  CH2 ◄── Soil Sensor Zone 3
  CH3 ◄── Soil Sensor Zone 4
```

### 2-Channel Relay Module Wiring (10A 1U Relay Board)

**Relay Module Pinout:**
```
┌────────────────────────────────────────────────┐
│       2-CHANNEL RELAY MODULE (1U / 10A)        │
├────────────────────────────────────────────────┤
│                                                │
│  Power Section:        Control Section:       │
│  ┌─────────────────┐   ┌─────────────────┐   │
│  │ JD-VCC ├─────┐ │   │ GND  │VCC  │IN1 │   │
│  │  12V ──┤ ┌┐  │ │   │ GND ─┼─── ┼─── │   │
│  │ GND ───┤ └┘  │ │   │ GND  │    │IN2 │   │
│  │        └─────┘ │   └─────────────────┘   │
│  │  (Jumper: keep on to use Pi 5V for coil) │
│  └─────────────────┘                         │
│                                                │
│  Relay 1 Contacts:    Relay 2 Contacts:      │
│  ┌─────────────────┐  ┌─────────────────┐   │
│  │ 1-1 │ 1-2 │ 1-3 │  │ 2-1 │ 2-2 │ 2-3 │   │
│  │ NC  │ COM │ NO  │  │ NC  │ COM │ NO  │   │
│  └─────────────────┘  └─────────────────┘   │
│                                                │
└────────────────────────────────────────────────┘
```

**Complete Relay Wiring Diagram:**

```
RASPBERRY PI                          2CH RELAY MODULE                    12V POWER SUPPLY
─────────────────────────────────────────────────────────────────────────────────────

Pump 1 Circuit:
─────────────
GPIO 17 ──────────────────────────────► IN1                          
                                                                      
                                   ┌─ JD-VCC (12V) ◄──────────── +12V (from DC supply)
                                   │                              
             ┌────────────────────►│─ GND         ◄───┐          
             │                     │                   │
             │                     │  [Relay Ch1]    ±12V, 2A DC Adapter
             │                     │                   │
             │  ┌─────────────────►│─ VCC (5V) ◄──── GND (return)
             │  │                  │                   │
             │  │  ┌─ 1-3 (NO) ────┼──────────────────┤
         GND ┴──┴─ 1-2 (COM)────────┼─┐                └─ GND (relay board)
                                      │                
                                      └──► Pump 1 Power Circuit
                                          (+12V to pump, -12V return)

Pump 2 Circuit:
─────────────
GPIO 27 ──────────────────────────────► IN2
                                   
             ┌────────────────────►│─ GND
             │  ┌─────────────────►│─ VCC (5V)
             │  │  ┌─ 2-3 (NO) ────┼──────────────────┐
        GND ┴──┴─ 2-2 (COM)────────┼─┐                │
                                     │        (12V pump circuit)
                                     └──► Pump 2 Power Circuit
                                         (+12V to pump, -12V return)
```

**Step-by-Step Wiring Instructions:**

**1. Control Power (5V from Pi to Relay Logic)**
```
Pi GPIO GND    → Relay GND (control section)
Pi +5V* (pin 2 or 4) → Relay VCC (control section)
```
*If Pi 5V available; otherwise use separate USB power for relay logic VCC

**2. GPIO Inputs to Relay**
```
Pi GPIO 17 (pump 1)  → Relay IN1
Pi GPIO 27 (pump 2)  → Relay IN2
```

**3. Relay Coil Power (12V Supply)**
```
+12V (from DC adapter) → Relay JD-VCC (DO NOT JUMPER to VCC!)
GND (from DC adapter)  → Relay GND (shared with control)
```

**4. Pump 1 Connected to Relay Ch1**
```
Pump 1 +12V → Relay 1-3 (NO - normally open)
Pump 1 -12V → Relay 1-2 (COM - common)
```
When GPIO 17 = HIGH: Relay closes, pump runs
When GPIO 17 = LOW:  Relay opens, pump stops

**5. Pump 2 Connected to Relay Ch2**
```
Pump 2 +12V → Relay 2-3 (NO - normally open)
Pump 2 -12V → Relay 2-2 (COM - common)
```
When GPIO 27 = HIGH: Relay closes, pump runs
When GPIO 27 = LOW:  Relay opens, pump stops

**Ground Connections (Critical!) — BEGINNER GUIDE:**

Think of ground (GND) like the "return path" for electricity. All devices must share the same reference point, or they won't communicate.

**Simple Analogy:**
Imagine 3 people talking on phones:
- Pi (Raspberry Pi)
- Relay (2-Channel Relay Module)  
- Power Supply (12V DC Adapter)

For them to "hear" each other (communicate), they all need to be on the **SAME PHONE LINE** — that phone line is **GND (Ground)**.

**Visual Wiring (The Easy Way):**

```
Step 1: Find all the GND pins
▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼

Raspberry Pi          12V Power Supply      2CH Relay Module
    │                      │                      │
   GND ◄──────┐            │                      │
              │            │                      │
         (any 1 black wire) │                      │
              │            │                      │
              ├────────────GND ◄──────────────────GND
              │
         This ONE black wire connects all 3 GNDs together!


Step 2: Connect with ONE black wire (Negative wire from power supply)

1. Black wire FROM 12V power supply GND
2. Goes TO Relay module GND
3. Then continues TO Raspberry Pi GND
   
   OR
   
   Use a "solder blob" / wire nut to join all 3 together


Before Wiring:           After Correct Wiring:
─────────────                ─────────────────

Pi GND: alone            Pi GND: ──────[black wire]──────
Relay GND: alone    →    Relay GND: ────[connected]────
PSU GND: alone           PSU GND: ─────[shares wire]────

                         All 3 are now connected by 1 black wire!
```

**MOST IMPORTANT: Why Ground Matters**

Without proper ground connection:
- ❌ GPIO signal from Pi won't reach relay (relay doesn't "hear" the signal)
- ❌ Relay won't turn on when GPIO 17 or 27 goes HIGH
- ❌ Pumps won't start even though code says they should
- ❌ You'll waste hours debugging and think your relay is broken!

**WITH proper ground connection:**
- ✅ GPIO 17 HIGH → Relay hears it → Relay turns on → Pump 1 runs
- ✅ GPIO 27 HIGH → Relay hears it → Relay turns on → Pump 2 runs
- ✅ Everything works!

**Checklist Before Plugging In:**

```
Do you have a BLACK WIRE connecting:
  [ ] Raspberry Pi GND
  [ ] Relay module GND  
  [ ] 12V Power Supply GND (negative)

All 3 connected by ONE black wire?
  [ ] YES → You're good! ✅
  [ ] NO  → DO NOT PLUG IN! Go fix it first.

All 3 are the same electrical reference point? 
  [ ] YES → Safe to test!
  [ ] NO  → Ground loops possible, fix it!
```

**Real Example Wiring:**

```
You'll have 3 main wires from 12V power supply:

1. RED wire   → Relay JD-VCC (12V input)
2. BLACK wire → THREE places:
               • Relay GND (control section, left side)
               • Raspberry Pi GND (pin 9 or 14 or any GND pin)
               • 12V Power Supply GND (negative)
3. RED wire from relay VCC → Raspberry Pi 5V (optional, if not using separate USB)

Visual Connection:
                    [12V Power Supply]
                           │
                   ┌───RED wire──────────┐
                   │                     │
                   ▼                     ▼
              [Relay JD-VCC]     [Relay VCC in]
              
                   ┌───BLACK wire────────┬──────────┐
                   │                     │          │
                   ▼                     ▼          ▼
              [Relay GND]         [Pi GND pin 9] [PSU GND]
              (left bottom)         (or pin 14)  (negative)
```

**If Still Confused:**

Contact your relay module supplier for a diagram, then:
1. Find the 2-3 GND pins (usually labeled "GND" or "G")
2. Connect them ALL with ONE black wire
3. Test with: `gpio readall` (should show GPIO 17 and 27)
4. Then test: `gpio write 17 1` (relay should click)


**❌ DO NOT:**
- Connect Pi 5V directly to JD-VCC (relay coil only takes 12V)
- Share pump 12V supply with Pi power
- Leave GND connections floating

**✅ Safe Wiring Checklist:**
- [ ] JD-VCC has jumper (or connected to 12V supply, NOT Pi 5V)
- [ ] All GND connections are common (Pi, relay, 12V supply)
- [ ] GPIO pins 17 and 27 connected to IN1 and IN2
- [ ] Pump wiring uses NO (1-3, 2-3) and COM (1-2, 2-2) contacts
- [ ] 12V supply is isolated from Pi power
- [ ] Relay cooling slots are not blocked
- [ ] TEST with `gpio readall` before attaching pumps

```

## Installation (Raspberry Pi 4)

### Step-by-Step Setup

**1. Initial Pi Setup (via Raspberry Pi Imager)**
```bash
# Flash 32GB microSD with:
# - OS: Raspberry Pi OS Lite (64-bit recommended)
# - Hostname: gartenroboter
# - Enable SSH, set password
# - Set WiFi SSID and password
```

**2. Boot Raspberry Pi 4 and SSH in**
```bash
ssh pi@gartenroboter.local
# Default password: raspberry
# CHANGE IT: passwd
```
M@rT1n_B3LaU!

**3. Run Automated Installation**
```bash
# Clone repository
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000

# Run install script (uv, Python deps, GPIO setup, systemd service)
chmod +x scripts/install.sh
./scripts/install.sh

#⚠️ Script will prompt to reboot if SPI/I2C were disabled
```

**4. Configure Secrets**
```bash
cp .env.example .env
nano .env  # Fill in your Telegram token and OpenWeather API key
```

**5. Start Service**
```bash
sudo systemctl start gartenroboter
sudo systemctl enable gartenroboter

# Verify it started
journalctl -u gartenroboter -n 30 -f

# To see real-time logs:
sudo journalctl -u gartenroboter -f
```

### Laptop/Development Setup

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/anneoneone/gartenroboter3000.git
cd gartenroboter3000
uv sync --all-extras

# Copy config
cp .env.example .env

# Run in mock mode (no hardware needed)
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
TELEGRAM_BOT_TOKEN=8699595089:AAF5P8Fb1fTC75fzRDcTcjXmJeHqnt_b27M
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

## ⚙️ Configuration

Configuration is managed via environment variables in `.env` file (encrypted at rest by systemd) and can be updated at runtime via Telegram bot.

### Raspberry Pi 4 Specific Tuning

```dotenv
# ✅ RECOMMENDED for Raspberry Pi 4 (from .env.example):

# Aggressive sensor polling for real-time monitoring
SCHEDULER_SENSOR_INTERVAL=15        # Default: 30s → RPi 4: 15s

# Shorter watering interval for responsive control  
SCHEDULER_WATERING_INTERVAL=300     # Default: 300s → RPi 4: maintain default

# Standard thresholds (Pi 4 handles more aggressive settings)
SENSOR_SOIL_THRESHOLD_DRY=30        # Default: 30% → RPi 4: maintain default

# Extended database retention with plenty of storage
DATABASE_RETENTION_DAYS=180         # Default: 90 → RPi 4: 180 days
```

See `.env.example` for all options and defaults.

### Dual Pump Configuration

To enable parallel watering with two pumps, add the second pump relay GPIO pin to your `.env` file:

```dotenv
# Single pump (default)
GPIO_PUMP_RELAY_PIN=17
GPIO_PUMP_RELAY_PIN_2=0          # Disabled

# Dual pump setup (parallel watering)
GPIO_PUMP_RELAY_PIN=17           # Pump 1 (zones 1, 3)
GPIO_PUMP_RELAY_PIN_2=27         # Pump 2 (zones 2, 4) - can run simultaneously!
```

**Zone Distribution (with dual pumps):**
- Zone 1 (odd) → Pump 1 (GPIO 17)
- Zone 2 (even) → Pump 2 (GPIO 27) — **Can water simultaneously with Zone 1!**
- Zone 3 (odd) → Pump 1 (GPIO 17)
- Zone 4 (even) → Pump 2 (GPIO 27) — **Can water simultaneously with Zone 3!**

**Benefits of dual pump:**
- ✅ Reduces watering cycle time by ~50% (5-8m vs 10-15m)
- ✅ Allows simultaneous watering of two zones
- ✅ Better for larger gardens
- ❌ Requires second pump, second relay module, additional GPIO pin
- ❌ Uses more water pumping capacity (both pumps can run in parallel)

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

## 🚀 Raspberry Pi 4 Model B Optimization

Raspberry Pi 4 is powerful enough to handle aggressive monitoring without constraints:

### Resource Management

| Resource | RPi 4 (2GB+) | Strategy |
|----------|-------------|----------|
| **RAM** | 2-8 GB | Full caching, parallel operations, no memory constraints |
| **CPU** | 1.5 GHz quad-core | Sensor polling every 15s (aggressive monitoring), fast processing |
| **Disk** | 32+ GB available | 180-day data retention, full SQLite capabilities |
| **I/O** | Gigabit Ethernet | Responsive API calls, real-time weather updates |

### Recommended Hardware Setup

```
┌─────────────────────────────────────────┐
│  Raspberry Pi 4 Model B                 │
│  ├─ 5V @ 3A minimum, 5A recommended    │
│  ├─ Optional: Aluminum heatsink         │
│  └─ ~0.6W idle, 1.5-2.5W running       │
├─────────────────────────────────────────┤
│  Recommended Additions:                 │
│  ├─ MCP3008 ADC (SPI, efficient)       │
│  ├─ HC-SR04 ultrasonic (GPIO, GPIO)    │
│  ├─ 4x soil sensors (passive, analog)  │
│  ├─ 2× relay modules (supports dual)   │
│  └─ External storage (USB 3.0 backup) │
└─────────────────────────────────────────┘
```

### Performance Notes

- **Cold boot**: ~20-30 seconds
- **Service startup**: ~3-5 seconds
- **Telegram response time**: <1 second (WiFi dependent)
- **Sensor reading**: 50-100ms per zone
- **Database query**: <20ms (fast with extended retention)

### Storage Life Expectancy

With recommended settings:
- **SanDisk 32GB microSD**: ~5-8 years (moderate write load, ideal for RPi 4)
- **Samsung EVO Plus 32GB**: ~7-10 years (excellent endurance)
- **Kingston Canvas Go Plus**: ~6-9 years (reliable performance)

**Pro tip**: Raspberry Pi 4 can safely run with standard journal logging:
```bash
# Optional: Enable persistent journaling for better debugging
sudo systemctl enable systemd-journald
journalctl --vacuum=60d  # Keep 60 days of logs
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
