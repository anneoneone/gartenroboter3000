#!/bin/bash
# Gartenroboter3000 Installation Script (Pi Zero 2 W Optimized)
# Run on Raspberry Pi Zero 2 W to set up the garden automation system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/home/pi/gartenroboter3000"
SERVICE_NAME="gartenroboter"
PYTHON_VERSION="3.11"
PI_MODEL=""

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Gartenroboter3000 Installation Script (Pi Zero 2 W)          ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}❌ Please do not run as root. Run as the 'pi' user.${NC}"
    exit 1
fi

# Check if running on Raspberry Pi and detect model
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model | sed 's/[^a-zA-Z0-9 ]//g')
    echo -e "${BLUE}ℹ️  Detected: $PI_MODEL${NC}"
else
    echo -e "${YELLOW}⚠️  Warning: This doesn't appear to be a Raspberry Pi.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Pi Zero 2 W specific optimizations
if [[ "$PI_MODEL" == *"Pi Zero 2"* ]] || [[ "$PI_MODEL" == *"Zero W"* ]]; then
    echo -e "${BLUE}ℹ️  Pi Zero 2 W detected - using optimized settings${NC}"
    SENSOR_INTERVAL=60
    WATERING_INTERVAL=600
    DATA_RETENTION=45
else
    SENSOR_INTERVAL=30
    WATERING_INTERVAL=300
    DATA_RETENTION=90
fi

echo -e "\n${GREEN}[1/7] Updating system packages...${NC}"
echo -e "${YELLOW}⚠️  Note: This may take 3-5 minutes on Pi Zero 2 W${NC}"
sudo apt update && sudo apt upgrade -y

echo -e "\n${GREEN}[2/7] Installing system dependencies...${NC}"
sudo apt install -y \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    git \
    libgpiod2 \
    i2c-tools \
    python3-smbus \
    python3-rpi.gpio \
    wireless-tools

echo -e "${YELLOW}"
echo "⚠️  CRITICAL FOR PI ZERO 2 W:"
echo "═══════════════════════════════════════════════════════════"
echo "Your power supply MUST provide at least 5V @ 3A (15W)"
echo "Common problems with weak power supplies:"
echo "  • Random \"brown out\" reboots"
echo "  • WiFi disconnects"
echo "  • GPIO/I2C unreliable behavior"
echo "  • USB device detection fails"
echo ""
echo "RECOMMENDED: Anker 5V/3A or official Raspberry Pi 27W PSU"
echo "═══════════════════════════════════════════════════════════"
echo -e "${NC}"

echo -e "\n${GREEN}[3/7] Enabling hardware interfaces...${NC}"
# Enable SPI
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
    echo -e "${YELLOW}SPI enabled - reboot required${NC}"
fi

# Enable I2C
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
    echo -e "${YELLOW}I2C enabled - reboot required${NC}"
fi

# Add user to required groups
sudo usermod -aG gpio,spi,i2c pi

echo -e "\n${GREEN}[4/7] Installing uv (Python package manager)...${NC}"
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing uv - may take 1-2 minutes on Pi Zero 2 W${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "✅ uv already installed"
fi

echo -e "\n${GREEN}[5/7] Setting up project directory...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Project directory exists, updating..."
    cd "$INSTALL_DIR"
    git pull || echo "Not a git repo or no remote configured"
else
    echo "Creating project directory..."
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create required directories
mkdir -p data logs

echo -e "${YELLOW}ℹ️  Disk space check:${NC}"
AVAILABLE=$(df "$INSTALL_DIR" | tail -1 | awk '{print $4}')
AVAILABLE_GB=$((AVAILABLE / 1024 / 1024))
if [ "$AVAILABLE_GB" -lt 2 ]; then
    echo -e "${RED}⚠️  WARNING: Only ${AVAILABLE_GB}GB free! Database retention may be limited.${NC}"
fi

echo -e "\n${GREEN}[6/7] Installing Python dependencies...${NC}"
echo -e "${YELLOW}This will take 2-4 minutes on Pi Zero 2 W - be patient!${NC}"
cd "$INSTALL_DIR"
uv sync --python 3.11

echo -e "\n${GREEN}[7/7] Setting up systemd service...${NC}"

# Copy service file
sudo cp "$INSTALL_DIR/systemd/gartenroboter.service" /etc/systemd/system/

# Create environment file if it doesn't exist
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    if [ -f "$INSTALL_DIR/.env.example" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        echo -e "${YELLOW}Please edit $INSTALL_DIR/.env with your configuration!${NC}"
    else
        cat > "$INSTALL_DIR/.env" << 'EOF'
# Gartenroboter3000 Configuration
# Copy this file to .env and fill in your values

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_ADMIN_CHAT_IDS=123456789

# OpenWeather API
OPENWEATHER_API_KEY=your_api_key_here

# Location (for sunset calculation)
LOCATION_LATITUDE=52.52
LOCATION_LONGITUDE=13.405

# Database
DATABASE_PATH=data/gartenroboter.db
EOF
        echo -e "${YELLOW}Please edit $INSTALL_DIR/.env with your configuration!${NC}"
    fi
fi

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable $SERVICE_NAME

echo -e "\n${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║      🎉 Gartenroboter3000 Setup Complete! (Pi Zero 2 W)      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "
${YELLOW}⚡ NEXT STEPS:${NC}

1. ${GREEN}nano $INSTALL_DIR/.env${NC}
   Add your Telegram bot token and OpenWeather API key

2. ${GREEN}sudo systemctl start $SERVICE_NAME${NC}
   Start the service

3. ${GREEN}journalctl -u $SERVICE_NAME -f${NC}
   Watch logs for errors (wait 10-15sec for bot to connect)

4. ${GREEN}sudo reboot${NC}
   Reboot if SPI/I2C were just enabled

${BLUE}🔧 PI ZERO 2 W OPTIMIZATION:${NC}

This installation is optimized for Pi Zero 2 W:
  ✓ Sensor polling: 60s (not 30s) to reduce CPU load
  ✓ Watering checks: 10m (not 5m) to reduce interrupt frequency
  ✓ Data retention: 45 days (not 90) to save ~5GB disk space
  ✓ Python 3.11: Async I/O for resource efficiency

Edit these in .env if needed:
  ${GREEN}SCHEDULER_SENSOR_INTERVAL=60${NC}
  ${GREEN}SCHEDULER_WATERING_INTERVAL=600${NC}
  ${GREEN}DATABASE_RETENTION_DAYS=45${NC}

${YELLOW}⚠️  IMPORTANT - Pin Configuration:${NC}

MCP3008 ADC (SPI):
  CLK  → GPIO 11 (SCLK)
  MOSI → GPIO 10 (MOSI)
  MISO → GPIO 9  (MISO)
  CS   → GPIO 8  (CE0)
  GND  → GND
  VDD  → 3.3V

HC-SR04 Ultrasonic:
  VCC → 5V
  GND → GND
  Trigger → GPIO 23
  Echo → GPIO 24 (via 1k/2k voltage divider to make 3.3V safe!)

Pump Relay:
  INPUT → GPIO 17
  GND → GND

Soil Sensors:
  Zone 1-4 → MCP3008 channels 0-3 (analog input)

${YELLOW}🌐 Verify WiFi:${NC}
  ${GREEN}iwconfig${NC}  (check connection strength)
  ${GREEN}ping 8.8.8.8${NC}  (test internet)

${YELLOW}Hardware check:${NC}
  ${GREEN}gpio readall${NC}  (verify GPIO setup)
  ${GREEN}i2cdetect -y 1${NC}  (list I2C devices)
  ${GREEN}cat /proc/device-tree/model${NC}  (verify Pi model)
"
