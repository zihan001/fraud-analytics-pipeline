#!/usr/bin/env python3
"""
Fraud Analytics Producer - PaySim CSV to Kinesis Stream

Replays PaySim transaction data to AWS Kinesis at a configurable rate
to simulate live transaction streaming for fraud detection.
"""
import argparse
import logging
import sys
import time
from typing import Optional

from config import ProducerConfig
from csv_reader import PaySimReader
from kinesis_client import KinesisPublisher


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.
    
    Args:
        verbose: Enable debug-level logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Replay PaySim CSV data to Kinesis stream',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        '--stream-name',
        type=str,
        help='Kinesis stream name (overrides KINESIS_STREAM_NAME env var)',
    )
    
    parser.add_argument(
        '--region',
        type=str,
        help='AWS region (overrides AWS_REGION env var)',
    )
    
    parser.add_argument(
        '--rate',
        type=int,
        metavar='EVENTS_PER_SEC',
        help='Event emission rate in events/second (5-100, overrides EVENTS_PER_SECOND env var)',
    )
    
    parser.add_argument(
        '--csv',
        type=str,
        metavar='PATH',
        help='Path to PaySim CSV file (overrides CSV_PATH env var)',
    )
    
    parser.add_argument(
        '--max-events',
        type=int,
        metavar='N',
        help='Maximum number of events to send (default: all)',
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose debug logging',
    )
    
    return parser.parse_args()


def run_producer(
    config: ProducerConfig,
    max_events: Optional[int] = None,
) -> None:
    """Run the producer to replay CSV data to Kinesis.
    
    Args:
        config: Producer configuration
        max_events: Maximum number of events to send (None = all)
    """
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Fraud Analytics Producer - Starting")
    logger.info("=" * 60)
    logger.info(f"Configuration: {config}")
    logger.info(f"Max events: {max_events or 'unlimited'}")
    logger.info("=" * 60)
    
    # Initialize components
    reader = PaySimReader(config.csv_path)
    publisher = KinesisPublisher(config.stream_name, config.region)
    
    # Calculate sleep time for rate limiting
    sleep_time = 1.0 / config.events_per_second
    
    logger.info(f"Rate limiting: {config.events_per_second} events/sec")
    logger.info(f"Sleep time between events: {sleep_time*1000:.2f}ms")
    logger.info("Starting event replay...")
    
    start_time = time.time()
    events_processed = 0
    
    try:
        for transaction in reader.read_transactions():
            # Rate limiting - sleep before sending
            time.sleep(sleep_time)
            
            # Publish to Kinesis
            success = publisher.publish_event(transaction)
            
            if not success:
                logger.warning(f"Failed to publish transaction at row {reader.rows_read}")
            
            events_processed += 1
            
            # Check if we've hit the max events limit
            if max_events and events_processed >= max_events:
                logger.info(f"Reached max events limit: {max_events}")
                break
    
    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal, shutting down...")
    
    except Exception as e:
        logger.error(f"Fatal error during replay: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Print final metrics
        elapsed_time = time.time() - start_time
        metrics = publisher.get_metrics()
        
        logger.info("=" * 60)
        logger.info("Fraud Analytics Producer - Summary")
        logger.info("=" * 60)
        logger.info(f"Total runtime: {elapsed_time:.2f}s")
        logger.info(f"Events processed: {events_processed:,}")
        logger.info(f"Events sent: {metrics['events_sent']:,}")
        logger.info(f"Errors: {metrics['errors']}")
        logger.info(f"Success rate: {metrics['success_rate']}%")
        logger.info(f"Average latency: {metrics['avg_latency_ms']}ms")
        
        if elapsed_time > 0:
            actual_rate = events_processed / elapsed_time
            logger.info(f"Actual throughput: {actual_rate:.2f} events/sec")
        
        logger.info("=" * 60)


def main() -> None:
    """Main entry point for the producer application."""
    args = parse_args()
    setup_logging(args.verbose)
    
    try:
        # Initialize configuration
        config = ProducerConfig(
            stream_name=args.stream_name,
            region=args.region,
            events_per_second=args.rate,
            csv_path=args.csv,
        )
        
        # Run producer
        run_producer(config, max_events=args.max_events)
        
    except Exception as e:
        logging.error(f"Failed to start producer: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
