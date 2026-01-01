"""Kinesis client for publishing transaction events."""
import json
import logging
import time
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class KinesisPublisher:
    """Publishes transaction events to AWS Kinesis stream."""
    
    def __init__(self, stream_name: str, region: str):
        """Initialize Kinesis publisher.
        
        Args:
            stream_name: Name of the Kinesis stream
            region: AWS region
        """
        self.stream_name = stream_name
        self.region = region
        self.client = boto3.client('kinesis', region_name=region)
        
        # Metrics
        self.events_sent = 0
        self.errors = 0
        self.total_latency = 0.0
        
        logger.info(f"Initialized Kinesis publisher for stream: {stream_name}")
        self._verify_stream()
    
    def _verify_stream(self) -> None:
        """Verify that the Kinesis stream exists and is active.
        
        Raises:
            ValueError: If stream doesn't exist or isn't active
        """
        try:
            response = self.client.describe_stream(StreamName=self.stream_name)
            status = response['StreamDescription']['StreamStatus']
            
            if status != 'ACTIVE':
                raise ValueError(
                    f"Stream {self.stream_name} is not active (status: {status})"
                )
            
            shard_count = len(response['StreamDescription']['Shards'])
            logger.info(
                f"Stream {self.stream_name} is active with {shard_count} shard(s)"
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                raise ValueError(f"Stream {self.stream_name} does not exist")
            raise
    
    def publish_event(
        self,
        transaction: Dict[str, Any],
        partition_key: Optional[str] = None,
        max_retries: int = 3,
    ) -> bool:
        """Publish a single transaction event to Kinesis.
        
        Args:
            transaction: Transaction dictionary to publish
            partition_key: Partition key for distribution (defaults to nameOrig)
            max_retries: Maximum retry attempts on failure
            
        Returns:
            True if successful, False otherwise
        """
        # Use nameOrig as partition key for even distribution across shards
        if partition_key is None:
            partition_key = transaction.get("nameOrig", "default")
        
        data = json.dumps(transaction)
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                
                response = self.client.put_record(
                    StreamName=self.stream_name,
                    Data=data,
                    PartitionKey=partition_key,
                )
                
                latency = time.time() - start_time
                self.total_latency += latency
                self.events_sent += 1
                
                if self.events_sent % 1000 == 0:
                    avg_latency = self.total_latency / self.events_sent
                    logger.info(
                        f"Published {self.events_sent:,} events "
                        f"(avg latency: {avg_latency*1000:.2f}ms)"
                    )
                
                return True
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code == 'ProvisionedThroughputExceededException':
                    # Exponential backoff for throttling
                    wait_time = (2 ** attempt) * 0.1
                    logger.warning(
                        f"Throttled by Kinesis, retrying in {wait_time:.2f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Kinesis error: {error_code} - {e}")
                    self.errors += 1
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected error publishing to Kinesis: {e}")
                self.errors += 1
                return False
        
        # Max retries exceeded
        logger.error(f"Failed to publish event after {max_retries} retries")
        self.errors += 1
        return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get publisher metrics.
        
        Returns:
            Dictionary with metrics (events_sent, errors, avg_latency_ms)
        """
        avg_latency = (
            (self.total_latency / self.events_sent * 1000)
            if self.events_sent > 0
            else 0.0
        )
        
        return {
            "events_sent": self.events_sent,
            "errors": self.errors,
            "avg_latency_ms": round(avg_latency, 2),
            "success_rate": (
                round(self.events_sent / (self.events_sent + self.errors) * 100, 2)
                if (self.events_sent + self.errors) > 0
                else 0.0
            ),
        }
