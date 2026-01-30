"""Telegram notification service for sending alerts and updates."""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

from telegram import Bot
from telegram.error import TelegramError

from gartenroboter.config.settings import Settings

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """A notification to be sent."""

    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    chat_ids: list[int] | None = None  # None = send to all allowed
    parse_mode: str = "Markdown"
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class NotificationQueue(Protocol):
    """Protocol for notification queue."""

    async def put(self, notification: Notification) -> None:
        """Add notification to queue."""
        ...

    async def get(self) -> Notification:
        """Get next notification from queue."""
        ...


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._bot: Bot | None = None
        self._queue: asyncio.Queue[Notification] = asyncio.Queue()
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._alerts_enabled = True

    @property
    def bot(self) -> Bot:
        """Get or create bot instance."""
        if self._bot is None:
            self._bot = Bot(token=self.settings.telegram.bot_token)
        return self._bot

    @property
    def alerts_enabled(self) -> bool:
        """Check if alerts are enabled."""
        return self._alerts_enabled

    @alerts_enabled.setter
    def alerts_enabled(self, value: bool) -> None:
        """Enable or disable alerts."""
        self._alerts_enabled = value
        logger.info(f"Alerts {'enabled' if value else 'disabled'}")

    async def start(self) -> None:
        """Start the notification worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Telegram notifier started")

    async def stop(self) -> None:
        """Stop the notification worker."""
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        logger.info("Telegram notifier stopped")

    async def _worker(self) -> None:
        """Process notification queue."""
        while self._running:
            try:
                # Wait for notification with timeout
                try:
                    notification = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except TimeoutError:
                    continue

                # Process notification
                await self._send_notification(notification)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in notification worker: {e}")
                await asyncio.sleep(1)

    async def _send_notification(self, notification: Notification) -> None:
        """Send a single notification."""
        if (
            not self._alerts_enabled
            and notification.priority != NotificationPriority.CRITICAL
        ):
            logger.debug("Alerts disabled, skipping non-critical notification")
            return

        # Determine recipients
        chat_ids = notification.chat_ids
        if chat_ids is None:
            chat_ids = list(self.settings.telegram.allowed_chat_ids)

        # Send to each recipient
        for chat_id in chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=notification.message,
                    parse_mode=notification.parse_mode,
                )
                logger.debug(f"Sent notification to {chat_id}")

            except TelegramError as e:
                logger.error(f"Failed to send to {chat_id}: {e}")

                # Retry logic
                if notification.retry_count < notification.max_retries:
                    notification.retry_count += 1
                    await self._queue.put(notification)
                    retries = notification.retry_count
                    max_retries = notification.max_retries
                    logger.info(f"Queued retry {retries}/{max_retries}")

    async def send(
        self,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        chat_ids: list[int] | None = None,
        parse_mode: str = "Markdown",
    ) -> None:
        """Queue a notification for sending.

        Args:
            message: The message text
            priority: Notification priority
            chat_ids: Specific recipients (None = all allowed)
            parse_mode: Telegram parse mode (Markdown, HTML, etc.)
        """
        notification = Notification(
            message=message, priority=priority, chat_ids=chat_ids, parse_mode=parse_mode
        )
        await self._queue.put(notification)

    async def send_immediate(
        self,
        message: str,
        chat_ids: list[int] | None = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Send a notification immediately, bypassing the queue.

        Returns:
            True if sent successfully to at least one recipient
        """
        if chat_ids is None:
            chat_ids = list(self.settings.telegram.allowed_chat_ids)

        success = False
        for chat_id in chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=message, parse_mode=parse_mode
                )
                success = True
            except TelegramError as e:
                logger.error(f"Failed to send immediate message to {chat_id}: {e}")

        return success

    # Convenience methods for common notifications

    async def notify_water_level_low(self, level_percent: float) -> None:
        """Send low water level alert."""
        message = (
            "⚠️ *Low Water Level Alert*\n\n"
            f"Rain barrel water level is at *{level_percent:.1f}%*\n"
            "Please refill soon to ensure watering can continue."
        )
        await self.send(message, priority=NotificationPriority.HIGH)

    async def notify_water_level_critical(self, level_percent: float) -> None:
        """Send critical water level alert."""
        message = (
            "🚨 *CRITICAL: Water Level Very Low*\n\n"
            f"Rain barrel water level is at *{level_percent:.1f}%*\n"
            "Automatic watering has been *disabled* to protect the pump.\n"
            "Please refill immediately!"
        )
        await self.send(message, priority=NotificationPriority.CRITICAL)

    async def notify_watering_started(
        self, zones: list[int], moisture_values: list[float]
    ) -> None:
        """Send watering started notification."""
        zone_info = ", ".join(
            f"Zone {z} ({m:.1f}%)" for z, m in zip(zones, moisture_values, strict=True)
        )
        message = (
            "💧 *Watering Started*\n\n"
            f"Watering zones: {zone_info}\n"
            f"Time: {datetime.now().strftime('%H:%M')}"
        )
        await self.send(message, priority=NotificationPriority.NORMAL)

    async def notify_watering_completed(
        self, zones: list[int], duration_seconds: float
    ) -> None:
        """Send watering completed notification."""
        message = (
            "✅ *Watering Completed*\n\n"
            f"Zones: {', '.join(str(z) for z in zones)}\n"
            f"Duration: {duration_seconds:.0f} seconds"
        )
        await self.send(message, priority=NotificationPriority.LOW)

    async def notify_pi_temperature_warning(self, temp_celsius: float) -> None:
        """Send Pi temperature warning."""
        message = (
            "🌡️ *Raspberry Pi Temperature Warning*\n\n"
            f"Current temperature: *{temp_celsius:.1f}°C*\n"
            "The system may throttle or shut down if temperature continues to rise.\n"
            "Consider improving ventilation."
        )
        await self.send(message, priority=NotificationPriority.HIGH)

    async def notify_pi_temperature_critical(self, temp_celsius: float) -> None:
        """Send Pi temperature critical alert."""
        message = (
            "🔥 *CRITICAL: Raspberry Pi Overheating*\n\n"
            f"Temperature: *{temp_celsius:.1f}°C*\n"
            "System operations are being limited to prevent damage.\n"
            "Immediate attention required!"
        )
        await self.send(message, priority=NotificationPriority.CRITICAL)

    async def notify_sensor_error(self, sensor_name: str, error: str) -> None:
        """Send sensor error notification."""
        message = (
            "⚠️ *Sensor Error*\n\n"
            f"Sensor: {sensor_name}\n"
            f"Error: {error}\n"
            "Check sensor connection and wiring."
        )
        await self.send(message, priority=NotificationPriority.HIGH)

    async def notify_pump_error(self, error: str) -> None:
        """Send pump error notification."""
        message = (
            f"🚨 *Pump Error*\n\nError: {error}\nAutomatic watering may be affected."
        )
        await self.send(message, priority=NotificationPriority.CRITICAL)

    async def notify_system_startup(self) -> None:
        """Send system startup notification."""
        message = (
            "🌱 *Gartenroboter3000 Started*\n\n"
            f"System is online and monitoring.\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "Use /status to check current readings."
        )
        await self.send(message, priority=NotificationPriority.NORMAL)

    async def notify_system_shutdown(self) -> None:
        """Send system shutdown notification."""
        message = (
            "🔌 *Gartenroboter3000 Shutting Down*\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "Automatic watering is now disabled."
        )
        await self.send_immediate(message)  # Send immediately, don't queue

    async def notify_config_changed(
        self, key: str, old_value: str, new_value: str, changed_by: str
    ) -> None:
        """Send configuration change notification."""
        # Only notify admins
        admin_ids = list(self.settings.telegram.admin_chat_ids)
        message = (
            "⚙️ *Configuration Changed*\n\n"
            f"Setting: `{key}`\n"
            f"Old value: `{old_value}`\n"
            f"New value: `{new_value}`\n"
            f"Changed by: {changed_by}"
        )
        await self.send(
            message, priority=NotificationPriority.NORMAL, chat_ids=admin_ids
        )
