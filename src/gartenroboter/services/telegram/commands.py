"""Telegram bot command handlers."""

import logging
from datetime import datetime, timedelta
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from gartenroboter.config.settings import Settings
from gartenroboter.config.validation import ConfigValidator, ValidationError
from gartenroboter.services.telegram.security import admin_only, authorized

logger = logging.getLogger(__name__)


def get_container(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    """Get the dependency container from context."""
    return {
        "settings": context.bot_data.get("settings"),
        "database": context.bot_data.get("database"),
        "sensors": context.bot_data.get("sensors"),
        "pump": context.bot_data.get("pump"),
        "weather": context.bot_data.get("weather"),
        "sun": context.bot_data.get("sun"),
        "watering": context.bot_data.get("watering"),
        "notifier": context.bot_data.get("notifier"),
        "config_manager": context.bot_data.get("config_manager"),
    }


@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not update.message:
        return

    await update.message.reply_text(
        "🌱 *Welcome to Gartenroboter3000!*\n\n"
        "I'm your garden automation assistant.\n\n"
        "*Available commands:*\n"
        "/status - Show current sensor readings\n"
        "/config - View current configuration\n"
        "/set <key> <value> - Update a setting\n"
        "/water <zone> - Manually water a zone\n"
        "/history [hours] - Show recent readings\n"
        "/alerts on|off - Toggle notifications\n"
        "/calibrate <sensor> - Calibrate a sensor\n"
        "/help - Show this help message\n\n"
        "*Admin commands:*\n"
        "/whitelist - Manage authorized users\n"
        "/reboot - Restart the system",
        parse_mode="Markdown",
    )


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await cmd_start(update, context)


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - show all sensor readings."""
    if not update.message:
        return

    container = get_container(context)
    sensors = container.get("sensors")
    pump = container.get("pump")
    weather = container.get("weather")
    sun = container.get("sun")
    settings: Settings = container.get("settings")

    # Build status message
    lines = ["📊 *Current Status*\n"]

    # Soil moisture sensors
    lines.append("*Soil Moisture:*")
    if sensors:
        try:
            readings = await sensors.read_all_soil_moisture()
            threshold = settings.sensor.soil_threshold_dry
            for i, reading in enumerate(readings):
                status = "🟢" if reading.moisture_percent > threshold else "🔴"
                lines.append(
                    f"  Zone {i + 1}: {reading.moisture_percent:.1f}% {status}"
                )
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Sensors not available")

    # Water level
    lines.append("\n*Water Level:*")
    if sensors:
        try:
            water_reading = await sensors.read_water_level()
            min_level = settings.sensor.water_level_min
            status = "🟢" if water_reading.level_percent > min_level else "🔴"
            lines.append(f"  {water_reading.level_percent:.1f}% {status}")
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Sensor not available")

    # Pi temperature
    lines.append("\n*Pi Temperature:*")
    if sensors:
        try:
            temp = await sensors.read_pi_temperature()
            warning = settings.system.pi_temp_warning
            status = "🟢" if temp.temperature_celsius < warning else "🟡"
            if temp.temperature_celsius > settings.system.pi_temp_critical:
                status = "🔴"
            lines.append(f"  {temp.temperature_celsius:.1f}°C {status}")
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Not available")

    # Pump status
    lines.append("\n*Pump:*")
    if pump:
        state = pump.state.value
        lines.append(f"  State: {state}")
        if pump.is_in_cooldown:
            remaining = pump.cooldown_remaining
            lines.append(f"  Cooldown: {remaining:.0f}s remaining")
    else:
        lines.append("  ⚠️ Not available")

    # Weather
    lines.append("\n*Weather:*")
    if weather:
        try:
            weather_data = await weather.get_current()
            if weather_data:
                lines.append(f"  {weather_data.description}")
                lines.append(f"  Temp: {weather_data.temperature_celsius:.1f}°C")
                if weather_data.rain_mm_1h:
                    lines.append(f"  Rain: {weather_data.rain_mm_1h:.1f}mm/h")
            else:
                lines.append("  ⚠️ No data available")
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Not available")

    # 3-Day Forecast
    lines.append("\n*Forecast:*")
    if weather:
        try:
            forecast = await weather.get_daily_forecast(days=3)
            if forecast:
                for day in forecast:
                    day_name = day["date"].strftime("%a")
                    rain_icon = "🌧" if day["rain_chance"] >= 0.5 else ""
                    lines.append(
                        f"  {day_name}: {day['temp_min']:.0f}°/{day['temp_max']:.0f}° "
                        f"{day['description']} {rain_icon}"
                    )
            else:
                lines.append("  ⚠️ No forecast available")
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Not available")

    # Sun
    lines.append("\n*Sun:*")
    if sun:
        try:
            is_night = await sun.is_night()
            event_name, event_time = await sun.get_next_sun_event()
            status = "🌙 Night" if is_night else "☀️ Day"
            emoji = "🌅" if event_name == "sunrise" else "🌇"
            lines.append(f"  Status: {status}")
            lines.append(
                f"  Next: {emoji} {event_name.capitalize()} at {event_time.strftime('%H:%M')}"
            )
        except Exception as e:
            lines.append(f"  ❌ Error: {e}")
    else:
        lines.append("  ⚠️ Not available")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@authorized
async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /config command - show current configuration."""
    if not update.message:
        return

    container = get_container(context)
    settings: Settings = container.get("settings")

    if not settings:
        await update.message.reply_text("❌ Configuration not available")
        return

    lines = ["⚙️ *Current Configuration*\n"]

    # Pump settings
    lines.append("*Pump:*")
    lines.append(f"  Max runtime: {settings.pump.max_runtime}s")
    lines.append(f"  Cooldown: {settings.pump.cooldown}s")

    # Sensor thresholds
    lines.append("\n*Soil Sensors:*")
    lines.append(f"  Dry threshold: {settings.sensor.soil_threshold_dry}%")

    # Water level
    lines.append("\n*Water Level:*")
    lines.append(f"  Minimum: {settings.sensor.water_level_min}%")

    # System
    lines.append("\n*System:*")
    lines.append(f"  Pi temp warning: {settings.system.pi_temp_warning}°C")
    lines.append(f"  Pi temp critical: {settings.system.pi_temp_critical}°C")
    lines.append(f"  Data retention: {settings.database.retention_days} days")

    # Location
    lines.append("\n*Location:*")
    lines.append(f"  Lat: {settings.location.latitude}")
    lines.append(f"  Lon: {settings.location.longitude}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@authorized
async def cmd_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /set command - update a configuration value."""
    if not update.message or not context.args:
        await update.message.reply_text(
            "Usage: `/set <key> <value>`\n\n"
            "*Available keys:*\n"
            "• `pump_max_runtime` (10-300 seconds)\n"
            "• `pump_cooldown` (60-600 seconds)\n"
            "• `soil_threshold_1` to `soil_threshold_4` (0-100%)\n"
            "• `water_level_min` (0-100%)\n"
            "• `pi_temp_warning` (50-85°C)\n"
            "• `pi_temp_critical` (60-90°C)",
            parse_mode="Markdown",
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Please provide both key and value")
        return

    key = context.args[0].lower()
    value = context.args[1]

    container = get_container(context)
    config_manager = container.get("config_manager")
    notifier = container.get("notifier")

    if not config_manager:
        await update.message.reply_text("❌ Configuration manager not available")
        return

    # Validate the new value
    try:
        validated_value = ConfigValidator.validate_setting(key, value)
    except ValidationError as e:
        await update.message.reply_text(f"❌ Invalid value: {e.message}")
        return

    # Get old value for notification
    old_value = config_manager.get_value(key)

    # Update the configuration
    try:
        await config_manager.set_value(key, validated_value)

        # Get user info for notification
        user = update.effective_user
        user_info = f"{user.full_name}" if user else "Unknown"

        # Notify about change
        if notifier:
            await notifier.notify_config_changed(
                key=key,
                old_value=str(old_value),
                new_value=str(validated_value),
                changed_by=user_info,
            )

        await update.message.reply_text(
            f"✅ Configuration updated\n\n"
            f"Key: `{key}`\n"
            f"Old: `{old_value}`\n"
            f"New: `{validated_value}`",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        await update.message.reply_text(f"❌ Failed to update: {e}")


@authorized
async def cmd_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /water command - manually trigger watering."""
    if not update.message:
        return

    container = get_container(context)
    watering = container.get("watering")
    pump = container.get("pump")

    if not watering or not pump:
        await update.message.reply_text("❌ Watering system not available")
        return

    # Parse zone argument
    zone = None
    if context.args:
        try:
            zone = int(context.args[0])
            if zone < 1 or zone > 4:
                await update.message.reply_text("❌ Zone must be between 1 and 4")
                return
        except ValueError:
            await update.message.reply_text(
                "Usage: `/water [zone]`\n"
                "Zone is optional (1-4). Without zone, waters all dry zones.",
                parse_mode="Markdown",
            )
            return

    # Check pump state
    if pump.is_active:
        await update.message.reply_text("⚠️ Pump is already running")
        return

    if pump.is_in_cooldown:
        remaining = pump.cooldown_remaining
        await update.message.reply_text(
            f"⚠️ Pump is in cooldown. {remaining:.0f}s remaining"
        )
        return

    # Trigger watering
    try:
        if zone:
            await update.message.reply_text(f"💧 Starting watering for zone {zone}...")
            await watering.water_zone(zone - 1)  # 0-indexed internally
        else:
            await update.message.reply_text("💧 Starting automatic watering check...")
            result = await watering.check_and_water()
            if not result.watered:
                await update.message.reply_text(
                    f"ℹ️ No watering needed: {result.reason}"
                )
                return

        await update.message.reply_text("✅ Watering completed")

    except Exception as e:
        logger.error(f"Manual watering failed: {e}")
        await update.message.reply_text(f"❌ Watering failed: {e}")


@authorized
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history command - show recent sensor readings."""
    if not update.message:
        return

    container = get_container(context)
    database = container.get("database")

    if not database:
        await update.message.reply_text("❌ Database not available")
        return

    # Parse hours argument (default 24)
    hours = 24
    if context.args:
        try:
            hours = int(context.args[0])
            hours = max(1, min(hours, 168))  # 1 hour to 1 week
        except ValueError:
            pass

    try:
        since = datetime.now() - timedelta(hours=hours)
        readings = await database.get_sensor_readings(since=since, limit=20)

        if not readings:
            await update.message.reply_text(
                f"No readings found in the last {hours} hours"
            )
            return

        lines = [f"📈 *Sensor History* (last {hours}h)\n"]

        for reading in readings[:10]:  # Show last 10
            timestamp = reading.timestamp.strftime("%H:%M")
            lines.append(f"`{timestamp}` - Zones: {reading.moisture_values}")

        if len(readings) > 10:
            lines.append(f"\n_...and {len(readings) - 10} more readings_")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        await update.message.reply_text(f"❌ Failed to fetch history: {e}")


@authorized
async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /alerts command - toggle notifications."""
    if not update.message:
        return

    container = get_container(context)
    notifier = container.get("notifier")

    if not notifier:
        await update.message.reply_text("❌ Notifier not available")
        return

    if not context.args:
        status = "enabled" if notifier.alerts_enabled else "disabled"
        await update.message.reply_text(
            f"🔔 Alerts are currently *{status}*\n\n"
            "Usage: `/alerts on` or `/alerts off`",
            parse_mode="Markdown",
        )
        return

    action = context.args[0].lower()

    if action == "on":
        notifier.alerts_enabled = True
        await update.message.reply_text("✅ Alerts enabled")
    elif action == "off":
        notifier.alerts_enabled = False
        await update.message.reply_text("✅ Alerts disabled")
    else:
        await update.message.reply_text("Usage: `/alerts on` or `/alerts off`")


@authorized
async def cmd_calibrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /calibrate command - start sensor calibration wizard."""
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "🔧 *Sensor Calibration*\n\n"
            "Usage: `/calibrate <sensor>`\n\n"
            "*Available sensors:*\n"
            "• `soil1` to `soil4` - Soil moisture sensors\n"
            "• `water` - Water level sensor\n\n"
            "The calibration wizard will guide you through the process.",
            parse_mode="Markdown",
        )
        return

    sensor = context.args[0].lower()

    # Start calibration conversation
    # For now, just provide instructions
    if sensor.startswith("soil"):
        try:
            zone = int(sensor[-1])
            if zone < 1 or zone > 4:
                raise ValueError()
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Invalid sensor. Use soil1-soil4")
            return

        await update.message.reply_text(
            f"🔧 *Calibrating Soil Sensor {zone}*\n\n"
            "*Step 1: Dry calibration*\n"
            "1. Ensure the sensor is completely dry\n"
            "2. Reply with `/cal_dry {zone}`\n\n"
            "*Step 2: Wet calibration*\n"
            "1. Submerge sensor in water\n"
            "2. Reply with `/cal_wet {zone}`\n\n"
            "_Calibration values will be saved automatically._",
            parse_mode="Markdown",
        )
    elif sensor == "water":
        await update.message.reply_text(
            "🔧 *Calibrating Water Level Sensor*\n\n"
            "*Step 1: Empty calibration*\n"
            "1. Ensure barrel is empty (or at minimum level)\n"
            "2. Reply with `/cal_empty`\n\n"
            "*Step 2: Full calibration*\n"
            "1. Fill barrel to maximum level\n"
            "2. Reply with `/cal_full`\n\n"
            "_Calibration values will be saved automatically._",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "❌ Unknown sensor. Available: soil1-soil4, water"
        )


@admin_only
async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /whitelist command - manage authorized users (admin only)."""
    if not update.message:
        return

    container = get_container(context)
    settings: Settings = container.get("settings")
    config_manager = container.get("config_manager")

    if not context.args:
        # Show current whitelist
        allowed = settings.telegram.allowed_chat_ids
        admins = settings.telegram.admin_chat_ids

        lines = ["👥 *Authorized Users*\n"]
        lines.append("*Allowed:*")
        for chat_id in allowed:
            is_admin = "👑" if chat_id in admins else ""
            lines.append(f"  `{chat_id}` {is_admin}")

        lines.append("\n*Usage:*")
        lines.append("`/whitelist add <chat_id>`")
        lines.append("`/whitelist remove <chat_id>`")
        lines.append("`/whitelist admin <chat_id>`")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    action = context.args[0].lower()

    if len(context.args) < 2:
        await update.message.reply_text("❌ Please provide a chat_id")
        return

    try:
        chat_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat_id")
        return

    if action == "add":
        if chat_id in settings.telegram.allowed_chat_ids:
            await update.message.reply_text("ℹ️ User already authorized")
            return

        settings.telegram.allowed_chat_ids.add(chat_id)
        await config_manager.save()
        await update.message.reply_text(f"✅ Added `{chat_id}` to whitelist")

    elif action == "remove":
        if chat_id not in settings.telegram.allowed_chat_ids:
            await update.message.reply_text("ℹ️ User not in whitelist")
            return

        # Prevent removing last admin
        if chat_id in settings.telegram.admin_chat_ids:
            if len(settings.telegram.admin_chat_ids) == 1:
                await update.message.reply_text("❌ Cannot remove the last admin")
                return
            settings.telegram.admin_chat_ids.discard(chat_id)

        settings.telegram.allowed_chat_ids.discard(chat_id)
        await config_manager.save()
        await update.message.reply_text(f"✅ Removed `{chat_id}` from whitelist")

    elif action == "admin":
        if chat_id not in settings.telegram.allowed_chat_ids:
            await update.message.reply_text("❌ User must be whitelisted first")
            return

        settings.telegram.admin_chat_ids.add(chat_id)
        await config_manager.save()
        await update.message.reply_text(f"✅ `{chat_id}` is now an admin")

    else:
        await update.message.reply_text("❌ Unknown action. Use: add, remove, admin")


@admin_only
async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reboot command - restart the system (admin only)."""
    if not update.message:
        return

    await update.message.reply_text(
        "🔄 *System Reboot*\n\n"
        "Are you sure you want to reboot the Gartenroboter3000?\n"
        "Reply `/reboot confirm` to proceed.",
        parse_mode="Markdown",
    )

    if context.args and context.args[0].lower() == "confirm":
        await update.message.reply_text("🔄 Rebooting system...")

        # Import here to avoid circular imports
        import asyncio

        # Give time for message to send
        await asyncio.sleep(1)

        # Trigger system reboot using asyncio subprocess
        try:
            process = await asyncio.create_subprocess_exec(
                "sudo",
                "reboot",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                await update.message.reply_text(f"❌ Reboot failed: {stderr.decode()}")
        except Exception as e:
            await update.message.reply_text(f"❌ Reboot failed: {e}")
