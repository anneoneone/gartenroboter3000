"""Gartenroboter3000 - Raspberry Pi Garden Automation System.

A modern Python-based garden automation system featuring:
- 4x soil moisture sensors with per-zone monitoring
- Automated pump control with safety limits
- Rain barrel water level monitoring
- Weather station integration (OpenWeather API)
- Sunset-based watering schedule
- Telegram bot for notifications and configuration
- SQLite data logging with 90-day rotation
- Raspberry Pi temperature monitoring

Usage:
    # Run with real hardware
    gartenroboter -c config.json

    # Run in mock mode (development)
    gartenroboter -c config.json --mock

    # Run with debug logging
    gartenroboter -c config.json --debug
"""

__version__ = "0.1.0"
__author__ = "Anton"
__app_name__ = "Gartenroboter3000"
