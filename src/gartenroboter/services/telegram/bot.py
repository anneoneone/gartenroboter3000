"""Main Telegram bot setup and lifecycle management."""

import contextlib
import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gartenroboter.config.settings import Settings
from gartenroboter.services.telegram.commands import (
    cmd_alerts,
    cmd_calibrate,
    cmd_config,
    cmd_help,
    cmd_history,
    cmd_reboot,
    cmd_set,
    cmd_start,
    cmd_status,
    cmd_water,
    cmd_whitelist,
)
from gartenroboter.services.telegram.notifier import TelegramNotifier
from gartenroboter.services.telegram.security import SecurityManager, get_chat_id

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram bot for Gartenroboter3000.

    Handles:
    - Command registration
    - Bot lifecycle (start/stop)
    - Dependency injection into handlers
    - Error handling
    """

    def __init__(
        self,
        settings: Settings,
        notifier: TelegramNotifier | None = None,
    ):
        self.settings = settings
        self.notifier = notifier or TelegramNotifier(settings)
        self.security = SecurityManager(settings)

        self._application: Application | None = None
        self._dependencies: dict[str, Any] = {}

    def set_dependencies(self, **dependencies: Any) -> None:
        """Set dependencies to be injected into command handlers.

        Args:
            database: Database instance
            sensors: SensorManager instance
            pump: PumpController instance
            weather: WeatherService instance
            sun: SunTracker instance
            watering: WateringEngine instance
            config_manager: ConfigManager instance
        """
        self._dependencies = dependencies

    async def start(self) -> None:
        """Start the Telegram bot."""
        logger.info("Starting Telegram bot...")

        # Create application
        self._application = (
            Application.builder().token(self.settings.telegram.bot_token).build()
        )

        # Inject dependencies into bot_data
        self._application.bot_data["settings"] = self.settings
        self._application.bot_data["notifier"] = self.notifier
        self._application.bot_data["security"] = self.security

        for key, value in self._dependencies.items():
            self._application.bot_data[key] = value

        # Register command handlers
        self._register_handlers()

        # Register error handler
        self._application.add_error_handler(self._error_handler)

        # Start notifier
        await self.notifier.start()

        # Initialize and start polling
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        logger.info("Telegram bot started successfully")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        logger.info("Stopping Telegram bot...")

        if self._application:
            # Stop polling
            if self._application.updater:
                await self._application.updater.stop()

            # Stop and shutdown
            await self._application.stop()
            await self._application.shutdown()

        # Stop notifier
        await self.notifier.stop()

        logger.info("Telegram bot stopped")

    def _register_handlers(self) -> None:
        """Register all command handlers."""
        if not self._application:
            return

        handlers = [
            # User commands
            CommandHandler("start", cmd_start),
            CommandHandler("help", cmd_help),
            CommandHandler("status", cmd_status),
            CommandHandler("config", cmd_config),
            CommandHandler("set", cmd_set),
            CommandHandler("water", cmd_water),
            CommandHandler("history", cmd_history),
            CommandHandler("alerts", cmd_alerts),
            CommandHandler("calibrate", cmd_calibrate),
            # Admin commands
            CommandHandler("whitelist", cmd_whitelist),
            CommandHandler("reboot", cmd_reboot),
            # Calibration sub-commands
            CommandHandler("cal_dry", self._cmd_cal_dry),
            CommandHandler("cal_wet", self._cmd_cal_wet),
            CommandHandler("cal_empty", self._cmd_cal_empty),
            CommandHandler("cal_full", self._cmd_cal_full),
            # Unknown command handler
            MessageHandler(filters.COMMAND, self._unknown_command),
        ]

        for handler in handlers:
            self._application.add_handler(handler)

    async def _error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors in command handlers."""
        logger.error(f"Exception while handling update: {context.error}")

        # Try to notify user
        if isinstance(update, Update) and update.effective_message:
            with contextlib.suppress(Exception):
                await update.effective_message.reply_text(
                    "❌ An error occurred while processing your request.\n"
                    "Please try again later."
                )

    async def _unknown_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle unknown commands."""
        if not update.message:
            return

        # Check authorization first
        chat_id = get_chat_id(update)
        if chat_id and chat_id not in self.settings.telegram.allowed_chat_ids:
            return  # Don't respond to unknown users

        await update.message.reply_text(
            "❓ Unknown command. Use /help to see available commands."
        )

    # Calibration command handlers

    async def _cmd_cal_dry(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle dry calibration for soil sensors."""
        if not update.message or not context.args:
            await update.message.reply_text("Usage: `/cal_dry <zone>`")
            return

        try:
            zone = int(context.args[0])
            if zone < 1 or zone > 4:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ Zone must be 1-4")
            return

        sensors = context.bot_data.get("sensors")
        config_manager = context.bot_data.get("config_manager")

        if not sensors:
            await update.message.reply_text("❌ Sensors not available")
            return

        try:
            # Read raw value
            raw_value = await sensors.read_raw_soil(zone - 1)

            # Save as dry calibration
            await config_manager.set_soil_calibration(
                zone=zone - 1, dry_value=raw_value
            )

            await update.message.reply_text(
                f"✅ *Dry Calibration Complete*\n\n"
                f"Zone {zone} dry value: `{raw_value}`\n"
                f"Now proceed with wet calibration: `/cal_wet {zone}`",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Calibration failed: {e}")

    async def _cmd_cal_wet(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle wet calibration for soil sensors."""
        if not update.message or not context.args:
            await update.message.reply_text("Usage: `/cal_wet <zone>`")
            return

        try:
            zone = int(context.args[0])
            if zone < 1 or zone > 4:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ Zone must be 1-4")
            return

        sensors = context.bot_data.get("sensors")
        config_manager = context.bot_data.get("config_manager")

        if not sensors:
            await update.message.reply_text("❌ Sensors not available")
            return

        try:
            # Read raw value
            raw_value = await sensors.read_raw_soil(zone - 1)

            # Save as wet calibration
            await config_manager.set_soil_calibration(
                zone=zone - 1, wet_value=raw_value
            )

            await update.message.reply_text(
                f"✅ *Wet Calibration Complete*\n\n"
                f"Zone {zone} wet value: `{raw_value}`\n"
                f"Calibration saved successfully!",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Calibration failed: {e}")

    async def _cmd_cal_empty(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle empty calibration for water level sensor."""
        if not update.message:
            return

        sensors = context.bot_data.get("sensors")
        config_manager = context.bot_data.get("config_manager")

        if not sensors:
            await update.message.reply_text("❌ Sensors not available")
            return

        try:
            # Read raw distance
            raw_distance = await sensors.read_raw_water_level()

            # Save as empty (max distance)
            await config_manager.set_water_level_calibration(
                empty_distance=raw_distance
            )

            await update.message.reply_text(
                f"✅ *Empty Calibration Complete*\n\n"
                f"Distance at empty: `{raw_distance:.1f}` cm\n"
                f"Now fill the barrel and run `/cal_full`",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Calibration failed: {e}")

    async def _cmd_cal_full(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle full calibration for water level sensor."""
        if not update.message:
            return

        sensors = context.bot_data.get("sensors")
        config_manager = context.bot_data.get("config_manager")

        if not sensors:
            await update.message.reply_text("❌ Sensors not available")
            return

        try:
            # Read raw distance
            raw_distance = await sensors.read_raw_water_level()

            # Save as full (min distance)
            await config_manager.set_water_level_calibration(full_distance=raw_distance)

            await update.message.reply_text(
                f"✅ *Full Calibration Complete*\n\n"
                f"Distance at full: `{raw_distance:.1f}` cm\n"
                f"Calibration saved successfully!",
                parse_mode="Markdown",
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Calibration failed: {e}")
