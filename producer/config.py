"""Configuration management for fraud analytics producer."""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class ProducerConfig:
    """Configuration settings for the producer application."""

    def __init__(
        self,
        stream_name: Optional[str] = None,
        region: Optional[str] = None,
        events_per_second: Optional[int] = None,
        csv_path: Optional[str] = None,
    ):
        """Initialize producer configuration.
        
        Args:
            stream_name: Kinesis stream name (overrides env var)
            region: AWS region (overrides env var)
            events_per_second: Rate limit for event emission (overrides env var)
            csv_path: Path to PaySim CSV file (overrides env var)
        """
        self.stream_name = stream_name or os.getenv(
            "KINESIS_STREAM_NAME", "fraud-analytics-dev-transactions"
        )
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.events_per_second = int(
            events_per_second or os.getenv("EVENTS_PER_SECOND", "10")
        )
        self.csv_path = csv_path or os.getenv(
            "CSV_PATH", "PS_20174392719_1491204439457_log.csv"
        )
        
        # Validate rate limits per REQUIREMENTS.md §5.1 (5-100 events/sec)
        if not 5 <= self.events_per_second <= 100:
            raise ValueError(
                f"events_per_second must be between 5 and 100, got {self.events_per_second}"
            )

    def __repr__(self) -> str:
        """Return string representation of config."""
        return (
            f"ProducerConfig(stream_name={self.stream_name}, "
            f"region={self.region}, "
            f"events_per_second={self.events_per_second}, "
            f"csv_path={self.csv_path})"
        )
