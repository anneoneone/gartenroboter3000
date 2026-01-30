#!/bin/bash
# Gartenroboter3000 Installation Script
# Run on Raspberry Pi to set up the garden automation system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/home/pi/gartenroboter3000"
SERVICE_NAME="gartenroboter"
PYTHON_VERSION="3.11"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Gartenroboter3000 Installation Script             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run as root. Run as the 'pi' user.${NC}"
    exit 1
fi

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "\n${GREEN}[1/7] Updating system packages...${NC}"
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
    python3-rpi.gpio

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
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed"
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

echo -e "\n${GREEN}[6/7] Installing Python dependencies...${NC}"
cd "$INSTALL_DIR"
uv sync

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
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              Installation Complete!                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "
${YELLOW}Next steps:${NC}

1. Edit the configuration file:
   ${GREEN}nano $INSTALL_DIR/.env${NC}

2. Start the service:
   ${GREEN}sudo systemctl start $SERVICE_NAME${NC}

3. Check the status:
   ${GREEN}sudo systemctl status $SERVICE_NAME${NC}

4. View logs:
   ${GREEN}journalctl -u $SERVICE_NAME -f${NC}

5. If you enabled SPI/I2C, reboot the Pi:
   ${GREEN}sudo reboot${NC}

${YELLOW}Hardware wiring:${NC}
- MCP3008 ADC: SPI0 (GPIO 10, 11, 9, 8)
- Soil Sensors: MCP3008 channels 0-3
- Water Level (HC-SR04):
  - Trigger: GPIO 23
  - Echo: GPIO 24 (use voltage divider!)
- Pump Relay: GPIO 17
"
