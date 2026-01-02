"""Unit tests for producer/kinesis_client.py - Kinesis publisher."""
import json
import time
from unittest.mock import Mock, patch, MagicMock

import pytest
from botocore.exceptions import ClientError
from moto import mock_kinesis

from producer.kinesis_client import KinesisPublisher


@pytest.fixture
def mock_kinesis_stream():
    """Create a mock Kinesis stream for testing."""
    with mock_kinesis():
        import boto3
        client = boto3.client('kinesis', region_name='us-east-1')
        client.create_stream(StreamName='test-stream', ShardCount=1)
        
        # Wait for stream to become active
        waiter = client.get_waiter('stream_exists')
        waiter.wait(StreamName='test-stream')
        
        yield client


@pytest.fixture
def sample_transaction():
    """Sample transaction data for testing."""
    return {
        "step": 1,
        "type": "PAYMENT",
        "amount": 9839.64,
        "nameOrig": "C1231006815",
        "oldbalanceOrg": 170136.00,
        "newbalanceOrig": 160296.36,
        "nameDest": "M1979787155",
        "oldbalanceDest": 0.00,
        "newbalanceDest": 0.00,
        "isFraud": 0,
        "isFlaggedFraud": 0,
    }


class TestKinesisPublisherInitialization:
    """Test KinesisPublisher initialization."""

    def test_init_stores_stream_name_and_region(self, mock_kinesis_stream):
        """Test that initialization stores stream name and region."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        assert publisher.stream_name == 'test-stream'
        assert publisher.region == 'us-east-1'

    def test_init_creates_boto3_client(self, mock_kinesis_stream):
        """Test that initialization creates a boto3 Kinesis client."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        assert publisher.client is not None
        assert hasattr(publisher.client, 'put_record')

    def test_init_sets_metrics_to_zero(self, mock_kinesis_stream):
        """Test that initialization sets all metrics to zero."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        assert publisher.events_sent == 0
        assert publisher.errors == 0
        assert publisher.total_latency == 0.0

    def test_init_raises_error_for_nonexistent_stream(self):
        """Test that initialization raises ValueError for non-existent stream."""
        with mock_kinesis():
            with pytest.raises(ValueError, match="does not exist"):
                KinesisPublisher(stream_name='nonexistent-stream', region='us-east-1')

    def test_init_raises_error_for_inactive_stream(self):
        """Test that initialization raises ValueError for inactive stream."""
        with mock_kinesis():
            import boto3
            client = boto3.client('kinesis', region_name='us-east-1')
            client.create_stream(StreamName='creating-stream', ShardCount=1)
            
            # Mock describe_stream to return CREATING status
            with patch.object(client, 'describe_stream') as mock_describe:
                mock_describe.return_value = {
                    'StreamDescription': {
                        'StreamStatus': 'CREATING',
                        'Shards': [{'ShardId': 'shard-001'}]
                    }
                }
                
                with patch('producer.kinesis_client.boto3.client', return_value=client):
                    with pytest.raises(ValueError, match="is not active"):
                        KinesisPublisher(stream_name='creating-stream', region='us-east-1')


class TestPublishEvent:
    """Test publish_event method."""

    def test_publishes_event_successfully(self, mock_kinesis_stream, sample_transaction):
        """Test that event is published successfully to Kinesis."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        result = publisher.publish_event(sample_transaction)
        
        assert result is True
        assert publisher.events_sent == 1
        assert publisher.errors == 0

    def test_creates_event_envelope_with_correct_structure(self, mock_kinesis_stream, sample_transaction):
        """Test that event envelope has correct structure."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(sample_transaction)
            
            # Get the data that was sent
            call_args = mock_put.call_args
            data = call_args.kwargs['Data']
            event = json.loads(data)
            
            assert 'event_id' in event
            assert event['event_type'] == 'transaction'
            assert 'event_ts' in event
            assert event['source'] == 'paysim/v1.0'
            assert event['payload'] == sample_transaction

    def test_uses_nameOrig_as_default_partition_key(self, mock_kinesis_stream, sample_transaction):
        """Test that nameOrig is used as default partition key."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(sample_transaction)
            
            call_args = mock_put.call_args
            partition_key = call_args.kwargs['PartitionKey']
            assert partition_key == sample_transaction['nameOrig']

    def test_uses_custom_partition_key_when_provided(self, mock_kinesis_stream, sample_transaction):
        """Test that custom partition key is used when provided."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(sample_transaction, partition_key='custom-key')
            
            call_args = mock_put.call_args
            partition_key = call_args.kwargs['PartitionKey']
            assert partition_key == 'custom-key'

    def test_uses_default_partition_key_when_nameOrig_missing(self, mock_kinesis_stream):
        """Test that 'default' is used when nameOrig is missing."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        transaction = {"type": "PAYMENT", "amount": 100.0}
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(transaction)
            
            call_args = mock_put.call_args
            partition_key = call_args.kwargs['PartitionKey']
            assert partition_key == 'default'

    def test_increments_events_sent_counter(self, mock_kinesis_stream, sample_transaction):
        """Test that events_sent counter is incremented."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        publisher.publish_event(sample_transaction)
        assert publisher.events_sent == 1
        
        publisher.publish_event(sample_transaction)
        assert publisher.events_sent == 2

    def test_tracks_latency(self, mock_kinesis_stream, sample_transaction):
        """Test that latency is tracked."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        publisher.publish_event(sample_transaction)
        assert publisher.total_latency > 0.0


class TestPublishEventRetry:
    """Test retry logic in publish_event."""

    def test_retries_on_throttling_exception(self, mock_kinesis_stream, sample_transaction):
        """Test that throttling errors trigger retries with exponential backoff."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        # Mock put_record to fail once with throttling, then succeed
        call_count = 0
        original_put = publisher.client.put_record
        
        def mock_put_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                error_response = {'Error': {'Code': 'ProvisionedThroughputExceededException'}}
                raise ClientError(error_response, 'PutRecord')
            return original_put(*args, **kwargs)
        
        with patch.object(publisher.client, 'put_record', side_effect=mock_put_record):
            with patch('time.sleep') as mock_sleep:
                result = publisher.publish_event(sample_transaction, max_retries=3)
                
                assert result is True
                assert call_count == 2
                assert mock_sleep.call_count == 1
                # First retry should wait 0.1 seconds (2^0 * 0.1)
                mock_sleep.assert_called_with(0.1)

    def test_exponential_backoff_on_multiple_throttles(self, mock_kinesis_stream, sample_transaction):
        """Test exponential backoff on multiple throttling errors."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        call_count = 0
        original_put = publisher.client.put_record
        
        def mock_put_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                error_response = {'Error': {'Code': 'ProvisionedThroughputExceededException'}}
                raise ClientError(error_response, 'PutRecord')
            return original_put(*args, **kwargs)
        
        with patch.object(publisher.client, 'put_record', side_effect=mock_put_record):
            with patch('time.sleep') as mock_sleep:
                result = publisher.publish_event(sample_transaction, max_retries=3)
                
                assert result is True
                assert call_count == 3
                assert mock_sleep.call_count == 2
                # Check exponential backoff: 0.1, 0.2
                assert mock_sleep.call_args_list[0][0][0] == 0.1
                assert mock_sleep.call_args_list[1][0][0] == 0.2

    def test_fails_after_max_retries(self, mock_kinesis_stream, sample_transaction):
        """Test that publish fails after exceeding max retries."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        def mock_put_record(*args, **kwargs):
            error_response = {'Error': {'Code': 'ProvisionedThroughputExceededException'}}
            raise ClientError(error_response, 'PutRecord')
        
        with patch.object(publisher.client, 'put_record', side_effect=mock_put_record):
            with patch('time.sleep'):
                result = publisher.publish_event(sample_transaction, max_retries=2)
                
                assert result is False
                assert publisher.errors == 1

    def test_does_not_retry_on_non_throttling_errors(self, mock_kinesis_stream, sample_transaction):
        """Test that non-throttling errors are not retried."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        call_count = 0
        
        def mock_put_record(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            error_response = {'Error': {'Code': 'InvalidArgumentException'}}
            raise ClientError(error_response, 'PutRecord')
        
        with patch.object(publisher.client, 'put_record', side_effect=mock_put_record):
            result = publisher.publish_event(sample_transaction, max_retries=3)
            
            assert result is False
            assert call_count == 1  # No retries
            assert publisher.errors == 1

    def test_handles_unexpected_exceptions(self, mock_kinesis_stream, sample_transaction):
        """Test that unexpected exceptions are handled gracefully."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', side_effect=Exception("Unexpected error")):
            result = publisher.publish_event(sample_transaction)
            
            assert result is False
            assert publisher.errors == 1


class TestGetMetrics:
    """Test get_metrics method."""

    def test_returns_initial_metrics(self, mock_kinesis_stream):
        """Test that initial metrics are all zeros."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        metrics = publisher.get_metrics()
        
        assert metrics['events_sent'] == 0
        assert metrics['errors'] == 0
        assert metrics['avg_latency_ms'] == 0.0
        assert metrics['success_rate'] == 0.0

    def test_returns_metrics_after_successful_publishes(self, mock_kinesis_stream, sample_transaction):
        """Test that metrics are updated after successful publishes."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        publisher.publish_event(sample_transaction)
        publisher.publish_event(sample_transaction)
        
        metrics = publisher.get_metrics()
        assert metrics['events_sent'] == 2
        assert metrics['errors'] == 0
        assert metrics['avg_latency_ms'] > 0.0
        assert metrics['success_rate'] == 100.0

    def test_returns_metrics_after_errors(self, mock_kinesis_stream, sample_transaction):
        """Test that metrics include errors."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        # Successful publish
        publisher.publish_event(sample_transaction)
        
        # Failed publish
        with patch.object(publisher.client, 'put_record', side_effect=Exception("Error")):
            publisher.publish_event(sample_transaction)
        
        metrics = publisher.get_metrics()
        assert metrics['events_sent'] == 1
        assert metrics['errors'] == 1
        assert metrics['success_rate'] == 50.0

    def test_calculates_average_latency(self, mock_kinesis_stream, sample_transaction):
        """Test that average latency is calculated correctly."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        # Mock latency
        publisher.total_latency = 0.5  # 500ms total
        publisher.events_sent = 5
        
        metrics = publisher.get_metrics()
        assert metrics['avg_latency_ms'] == 100.0  # 500ms / 5 events = 100ms avg

    def test_rounds_metrics_correctly(self, mock_kinesis_stream, sample_transaction):
        """Test that metrics are rounded to 2 decimal places."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        publisher.total_latency = 0.123456
        publisher.events_sent = 3
        publisher.errors = 1
        
        metrics = publisher.get_metrics()
        assert metrics['avg_latency_ms'] == 41.15  # (123.456ms / 3) rounded
        assert metrics['success_rate'] == 75.0  # (3 / 4) * 100


class TestEventEnvelope:
    """Test event envelope creation."""

    def test_event_id_is_unique(self, mock_kinesis_stream, sample_transaction):
        """Test that each event gets a unique event_id."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        event_ids = []
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            for _ in range(3):
                publisher.publish_event(sample_transaction)
            
            for call in mock_put.call_args_list:
                data = call.kwargs['Data']
                event = json.loads(data)
                event_ids.append(event['event_id'])
        
        assert len(event_ids) == 3
        assert len(set(event_ids)) == 3  # All unique

    def test_event_timestamp_is_iso8601_utc(self, mock_kinesis_stream, sample_transaction):
        """Test that event timestamp is in ISO8601 UTC format."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(sample_transaction)
            
            data = mock_put.call_args.kwargs['Data']
            event = json.loads(data)
            
            # Check format (should end with +00:00 or Z for UTC)
            assert 'T' in event['event_ts']
            assert event['event_ts'].endswith(('+00:00', 'Z'))

    def test_payload_contains_original_transaction(self, mock_kinesis_stream, sample_transaction):
        """Test that payload contains the original transaction unchanged."""
        publisher = KinesisPublisher(stream_name='test-stream', region='us-east-1')
        
        with patch.object(publisher.client, 'put_record', wraps=publisher.client.put_record) as mock_put:
            publisher.publish_event(sample_transaction)
            
            data = mock_put.call_args.kwargs['Data']
            event = json.loads(data)
            
            assert event['payload'] == sample_transaction
            assert event['payload']['nameOrig'] == 'C1231006815'
            assert event['payload']['amount'] == 9839.64
