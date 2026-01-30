"""Security decorators and utilities for Telegram bot."""

import functools
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from gartenroboter.config.settings import Settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def get_chat_id(update: Update) -> int | None:
    """Extract chat ID from update."""
    if update.effective_chat:
        return update.effective_chat.id
    if update.message:
        return update.message.chat_id
    return None


def get_user_info(update: Update) -> str:
    """Get user info string for logging."""
    user = update.effective_user
    if user:
        return f"{user.full_name} (@{user.username}, id={user.id})"
    return "Unknown user"


def authorized(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to check if user is in allowed_chat_ids whitelist.

    Usage:
        @authorized
        async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ) -> T | None:
        chat_id = get_chat_id(update)

        if chat_id is None:
            logger.warning("Could not determine chat_id from update")
            return None

        # Get settings from context
        settings: Settings | None = context.bot_data.get("settings")
        if settings is None:
            logger.error("Settings not found in bot_data")
            if update.message:
                await update.message.reply_text(
                    "❌ Bot configuration error. Please contact admin."
                )
            return None

        # Check if chat_id is in allowed list
        if chat_id not in settings.telegram.allowed_chat_ids:
            user_info = get_user_info(update)
            logger.warning(
                f"Unauthorized access attempt from {user_info}, chat_id={chat_id}"
            )

            # Log to database if available
            db = context.bot_data.get("database")
            if db:
                try:
                    await db.log_alert(
                        alert_type="unauthorized_access",
                        message=f"Unauthorized access from {user_info}",
                        severity="warning",
                    )
                except Exception as e:
                    logger.error(f"Failed to log unauthorized access: {e}")

            if update.message:
                await update.message.reply_text(
                    "⛔ You are not authorized to use this bot.\n"
                    f"Your chat ID: `{chat_id}`\n"
                    "Contact the admin to get access.",
                    parse_mode="Markdown",
                )
            return None

        # User is authorized, proceed
        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_only(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to check if user is in admin_chat_ids list.

    Requires user to be both authorized AND an admin.

    Usage:
        @admin_only
        async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """

    @functools.wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ) -> T | None:
        chat_id = get_chat_id(update)

        if chat_id is None:
            logger.warning("Could not determine chat_id from update")
            return None

        # Get settings from context
        settings: Settings | None = context.bot_data.get("settings")
        if settings is None:
            logger.error("Settings not found in bot_data")
            if update.message:
                await update.message.reply_text(
                    "❌ Bot configuration error. Please contact admin."
                )
            return None

        # Check if chat_id is in allowed list first
        if chat_id not in settings.telegram.allowed_chat_ids:
            user_info = get_user_info(update)
            logger.warning(
                f"Unauthorized access attempt from {user_info}, chat_id={chat_id}"
            )
            if update.message:
                await update.message.reply_text(
                    "⛔ You are not authorized to use this bot."
                )
            return None

        # Check if chat_id is admin
        if chat_id not in settings.telegram.admin_chat_ids:
            user_info = get_user_info(update)
            logger.warning(
                f"Non-admin tried admin command: {user_info}, chat_id={chat_id}"
            )
            if update.message:
                await update.message.reply_text(
                    "🔐 This command requires admin privileges."
                )
            return None

        # User is admin, proceed
        return await func(update, context, *args, **kwargs)

    return wrapper


class SecurityManager:
    """Manage security-related operations for the bot."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._unauthorized_attempts: dict[int, int] = {}  # chat_id -> count
        self._max_attempts = 5

    def is_authorized(self, chat_id: int) -> bool:
        """Check if chat_id is authorized."""
        return chat_id in self.settings.telegram.allowed_chat_ids

    def is_admin(self, chat_id: int) -> bool:
        """Check if chat_id is admin."""
        return chat_id in self.settings.telegram.admin_chat_ids

    def record_unauthorized_attempt(self, chat_id: int) -> int:
        """Record an unauthorized access attempt, return total attempts."""
        self._unauthorized_attempts[chat_id] = (
            self._unauthorized_attempts.get(chat_id, 0) + 1
        )
        return self._unauthorized_attempts[chat_id]

    def should_block(self, chat_id: int) -> bool:
        """Check if chat_id has exceeded max unauthorized attempts."""
        return self._unauthorized_attempts.get(chat_id, 0) >= self._max_attempts

    def get_unauthorized_attempts(self) -> dict[int, int]:
        """Get all unauthorized attempts."""
        return self._unauthorized_attempts.copy()

    def clear_attempts(self, chat_id: int) -> None:
        """Clear unauthorized attempts for a chat_id."""
        self._unauthorized_attempts.pop(chat_id, None)
