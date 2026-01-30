"""Application factory and dependency container."""

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass, field
from pathlib import Path

from gartenroboter.config.config_manager import ConfigManager
from gartenroboter.config.settings import Settings
from gartenroboter.core.pump import PumpController
from gartenroboter.core.sensors import SensorManager
from gartenroboter.core.watering import WateringEngine
from gartenroboter.infra.database import Database
from gartenroboter.infra.gpio import GpioInterface, create_gpio
from gartenroboter.infra.scheduler import Scheduler, create_default_scheduler
from gartenroboter.services.sun import SunTracker
from gartenroboter.services.telegram import TelegramBot, TelegramNotifier
from gartenroboter.services.weather import WeatherService

logger = logging.getLogger(__name__)


@dataclass
class Container:
    """Dependency container for the application.

    Holds all service instances and provides access to them.
    """

    settings: Settings
    config_manager: ConfigManager
    gpio: GpioInterface
    database: Database
    sensors: SensorManager
    pump: PumpController
    watering: WateringEngine
    weather: WeatherService
    sun: SunTracker
    notifier: TelegramNotifier
    telegram_bot: TelegramBot
    scheduler: Scheduler

    # Internal state
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)

    async def shutdown(self) -> None:
        """Signal shutdown to all components."""
        self._shutdown_event.set()

    @property
    def shutdown_event(self) -> asyncio.Event:
        """Get shutdown event."""
        return self._shutdown_event


async def create_app(
    config_path: Path | None = None,
    mock_mode: bool = False,
) -> Container:
    """Create and initialize the application.

    Args:
        config_path: Path to config.json file
        mock_mode: If True, use mock GPIO (for development)

    Returns:
        Initialized Container with all dependencies
    """
    logger.info("Creating application...")

    # Load configuration
    if config_path is None:
        config_path = Path("config.json")

    config_manager = ConfigManager(config_path)
    settings = await config_manager.load()

    logger.info(f"Loaded configuration from {config_path}")

    # Create GPIO interface
    gpio = create_gpio(settings=settings.gpio, mock_mode=mock_mode)
    logger.info(f"GPIO interface: {'mock' if mock_mode else 'real'}")

    # Initialize database
    database = Database(settings.database)
    await database.connect()
    logger.info(f"Database initialized at {database.db_path}")

    # Create sensor manager
    sensors = SensorManager(
        gpio=gpio,
        settings=settings.sensor,
        gpio_settings=settings.gpio,
    )

    # Create pump controller
    pump = PumpController(
        gpio=gpio,
        settings=settings.pump,
        gpio_settings=settings.gpio,
    )

    # Create weather service
    weather = WeatherService(
        settings=settings.weather,
        location=settings.location,
    )

    # Create sun tracker
    sun = SunTracker(location=settings.location, weather_settings=settings.weather)

    # Create notifier
    notifier = TelegramNotifier(settings=settings)

    # Create watering engine
    watering = WateringEngine(
        settings=settings,
        sensor_manager=sensors,
        pump_controller=pump,
        sun_tracker=sun,
        weather_service=weather,
    )

    # Create Telegram bot
    telegram_bot = TelegramBot(
        settings=settings,
        notifier=notifier,
    )

    # Set dependencies for bot commands
    telegram_bot.set_dependencies(
        database=database,
        sensors=sensors,
        pump=pump,
        weather=weather,
        sun=sun,
        watering=watering,
        config_manager=config_manager,
    )

    # Create scheduler with callbacks
    async def sensor_callback() -> None:
        """Read all sensors and log to database."""
        try:
            soil_readings, water_level, pi_temp = await sensors.read_all()
            # Log each soil moisture reading
            for reading in soil_readings:
                await database.insert_sensor_reading(
                    sensor_type="soil_moisture",
                    zone_id=reading.zone_id,
                    raw_value=reading.raw_value,
                    normalized_value=reading.moisture_percent,
                    is_warning=reading.is_dry,
                )
            # Log water level
            await database.insert_sensor_reading(
                sensor_type="water_level",
                raw_value=None,
                normalized_value=water_level.level_percent,
                is_warning=water_level.is_low,
            )
            # Log Pi temperature
            await database.insert_sensor_reading(
                sensor_type="pi_temperature",
                raw_value=None,
                normalized_value=pi_temp.temperature_celsius,
                is_warning=pi_temp.is_warning,
            )
        except Exception as e:
            logger.error(f"Sensor polling failed: {e}")

    async def watering_callback() -> None:
        """Check watering conditions and water if needed."""
        try:
            result = await watering.check_and_water()
            if result.watered:
                logger.info(f"Watered zones: {result.zones}")
        except Exception as e:
            logger.error(f"Watering check failed: {e}")

    async def rotation_callback() -> None:
        """Rotate old data from database."""
        try:
            deleted = await database.rotate_data(
                retention_days=settings.database.retention_days
            )
            logger.info(f"Data rotation: deleted {deleted} old records")
        except Exception as e:
            logger.error(f"Data rotation failed: {e}")

    async def temperature_callback() -> None:
        """Check Pi temperature and send alerts if needed."""
        try:
            temp = await sensors.read_pi_temperature()

            if temp.temperature_celsius >= settings.system.pi_temp_critical:
                await notifier.notify_pi_temperature_critical(temp.temperature_celsius)
                await database.insert_alert(
                    alert_type="pi_temp_critical",
                    message=f"Pi temperature critical: {temp.temperature_celsius}°C",
                )
            elif temp.temperature_celsius >= settings.system.pi_temp_warning:
                await notifier.notify_pi_temperature_warning(temp.temperature_celsius)
                await database.insert_alert(
                    alert_type="pi_temp_warning",
                    message=f"Pi temperature warning: {temp.temperature_celsius}°C",
                )
        except Exception as e:
            logger.error(f"Temperature check failed: {e}")

    async def weather_callback() -> None:
        """Update weather data cache."""
        try:
            await weather.get_current()
        except Exception as e:
            logger.error(f"Weather update failed: {e}")

    scheduler = create_default_scheduler(
        sensor_callback=sensor_callback,
        watering_callback=watering_callback,
        rotation_callback=rotation_callback,
        temperature_callback=temperature_callback,
        weather_callback=weather_callback,
    )

    # Build container
    container = Container(
        settings=settings,
        config_manager=config_manager,
        gpio=gpio,
        database=database,
        sensors=sensors,
        pump=pump,
        watering=watering,
        weather=weather,
        sun=sun,
        notifier=notifier,
        telegram_bot=telegram_bot,
        scheduler=scheduler,
    )

    logger.info("Application created successfully")
    return container


async def run_app(container: Container) -> None:
    """Run the application main loop.

    Args:
        container: Initialized Container from create_app()
    """
    logger.info("Starting application...")

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    shutdown_task: asyncio.Task[None] | None = None

    def signal_handler(sig: signal.Signals) -> None:
        nonlocal shutdown_task
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        shutdown_task = asyncio.create_task(container.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        # Start all services
        await container.telegram_bot.start()
        await container.scheduler.start()

        # Send startup notification
        await container.notifier.notify_system_startup()

        logger.info("Application started, waiting for shutdown signal...")

        # Wait for shutdown
        await container.shutdown_event.wait()

    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        raise

    finally:
        # Graceful shutdown
        logger.info("Shutting down application...")

        # Send shutdown notification
        with contextlib.suppress(Exception):
            await container.notifier.notify_system_shutdown()

        # Stop services in reverse order
        await container.scheduler.stop()
        await container.telegram_bot.stop()

        # Cleanup
        await container.pump.emergency_stop()
        await container.database.close()
        await container.gpio.cleanup()

        logger.info("Application shutdown complete")


async def main(
    config_path: Path | None = None,
    mock_mode: bool = False,
) -> None:
    """Main entry point for the application.

    Args:
        config_path: Path to config.json
        mock_mode: Use mock GPIO for development
    """
    # Create and run application
    container = await create_app(
        config_path=config_path,
        mock_mode=mock_mode,
    )

    await run_app(container)
