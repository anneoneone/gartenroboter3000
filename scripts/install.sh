#!/bin/bash
# Gartenroboter3000 Installation Script (Raspberry Pi 4 Model B Optimized)
# Run on Raspberry Pi 4 Model B to set up the garden automation system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CURRENT_USER="$(whoami)"
INSTALL_DIR="$HOME/gartenroboter3000"
SERVICE_NAME="gartenroboter"
PYTHON_VERSION="3.11"
PI_MODEL=""

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Gartenroboter3000 Installation Script (Raspberry Pi 4)       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "${BLUE}ℹ️  Installing for user: $CURRENT_USER${NC}"
echo -e "${BLUE}ℹ️  Installation directory: $INSTALL_DIR${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}❌ Please do not run as root. Run as a regular user (not root).${NC}"
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

# Raspberry Pi 4 specific optimizations
if [[ "$PI_MODEL" == *"Raspberry Pi 4"* ]]; then
    echo -e "${BLUE}ℹ️  Raspberry Pi 4 detected - using optimized settings${NC}"
    SENSOR_INTERVAL=15
    WATERING_INTERVAL=300
    DATA_RETENTION=180
elif [[ "$PI_MODEL" == *"Pi Zero 2"* ]] || [[ "$PI_MODEL" == *"Zero W"* ]]; then
    echo -e "${BLUE}ℹ️  Pi Zero 2 W detected - using conservative settings${NC}"
    SENSOR_INTERVAL=60
    WATERING_INTERVAL=600
    DATA_RETENTION=45
else
    echo -e "${YELLOW}⚠️  Unknown Pi model detected - using default settings${NC}"
    SENSOR_INTERVAL=30
    WATERING_INTERVAL=300
    DATA_RETENTION=90
fi

echo -e "\n${GREEN}[1/7] Updating system packages...${NC}"
echo -e "${YELLOW}ℹ️  This typically takes 1-2 minutes on Raspberry Pi 4${NC}"
sudo apt update && sudo apt upgrade -y

echo -e "\n${GREEN}[2/7] Installing system dependencies...${NC}"
sudo apt install -y \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    git \
    gpiod \
    i2c-tools \
    python3-smbus \
    python3-rpi.gpio \
    wireless-tools

echo -e "${YELLOW}"
echo "⚠️  POWER SUPPLY REQUIREMENTS FOR RASPBERRY PI 4:"
echo "═══════════════════════════════════════════════════════════"
echo "Minimum: USB-C 5V @ 3A (15W)"
echo "Recommended: USB-C 5V @ 5A (27W) - especially with USB devices"
echo ""
echo "RECOMMENDED POWER SUPPLIES:"
echo "  • Official Raspberry Pi 27W USB-C PSU (best option)"
echo "  • Anker USB-C Power Delivery 65W"
echo "  • Any certified USB-C PD supply rated for 27W+"
echo ""
echo "WARNING: Using micro-USB supplies or low-quality adapters"
echo "can cause GPIO/I2C instability and mysterious failures!"
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
echo -e "${BLUE}ℹ️  Adding $CURRENT_USER to GPIO/SPI/I2C groups...${NC}"
sudo usermod -aG gpio,spi,i2c "$CURRENT_USER"
echo -e "${YELLOW}⚠️  You may need to log out and back in for group changes to take effect${NC}"

echo -e "\n${GREEN}[4/7] Installing uv (Python package manager)...${NC}"
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing uv - typically 30 seconds on Raspberry Pi 4${NC}"
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
echo -e "${YELLOW}This will take 1-2 minutes on Raspberry Pi 4 - be patient!${NC}"
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
echo "║     🎉 Gartenroboter3000 Setup Complete! (Raspberry Pi 4)   ║"
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

${BLUE}🔧 RASPBERRY PI 4 OPTIMIZATION:${NC}

This installation is optimized for Raspberry Pi 4 Model B:
  ✓ Sensor polling: 15s (aggressive monitoring) for real-time responsiveness
  ✓ Watering checks: 5m (standard interval) with fast processing
  ✓ Data retention: 180 days (extended history) with ample storage
  ✓ Python 3.11: Full async I/O with parallel operations

Edit these in .env if needed or for Pi Zero 2 W fallback:
  ${GREEN}SCHEDULER_SENSOR_INTERVAL=15${NC}     (RPi 4) or 60 (Pi Zero 2W)
  ${GREEN}SCHEDULER_WATERING_INTERVAL=300${NC}  (RPi 4) or 600 (Pi Zero 2W)
  ${GREEN}DATABASE_RETENTION_DAYS=180${NC}      (RPi 4) or 45 (Pi Zero 2W)

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
