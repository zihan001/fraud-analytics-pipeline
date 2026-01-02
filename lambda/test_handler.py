"""
Unit tests for Lambda fraud scoring handler.
"""
import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest

# Set environment variables before importing handler
os.environ['ENRICHED_BUCKET'] = 'test-bucket'
os.environ['ENRICHED_PREFIX'] = 'enriched/'
os.environ['METRICS_TABLE'] = 'test-metrics'
os.environ['LATEST_STATE_TABLE'] = 'test-state'
os.environ['DLQ_URL'] = 'https://sqs.us-west-2.amazonaws.com/123456789/test-dlq'

from handler import (
    lambda_handler,
    validate_event,
    enrich_event,
    calculate_fraud_score,
    process_event,
    update_metric_counter,
    update_latest_state,
    send_to_dlq
)


@pytest.fixture
def valid_transaction_event():
    """Valid transaction event payload."""
    return {
        'event_id': 'evt_12345',
        'event_type': 'transaction',
        'event_ts': '2026-01-01T12:00:00Z',
        'source': 'paysim/v1.0',
        'payload': {
            'type': 'PAYMENT',
            'amount': 1000.50,
            'nameOrig': 'C123456',
            'nameDest': 'M789012',
            'isFraud': 0
        }
    }


@pytest.fixture
def high_risk_transaction():
    """High risk transaction for fraud scoring."""
    return {
        'event_id': 'evt_99999',
        'event_type': 'transaction',
        'event_ts': '2026-01-01T14:30:00Z',
        'source': 'paysim/v1.0',
        'payload': {
            'type': 'CASH_OUT',
            'amount': 9000.00,  # High amount, round number
            'nameOrig': 'C999999',
            'isFraud': 1
        }
    }


@pytest.fixture
def kinesis_record(valid_transaction_event):
    """Kinesis event record structure."""
    return {
        'kinesis': {
            'partitionKey': 'C123456',
            'sequenceNumber': '49624450867430322871966858201536618369469192501878366210',
            'data': base64.b64encode(json.dumps(valid_transaction_event).encode('utf-8')).decode('utf-8'),
            'approximateArrivalTimestamp': 1704110400.0
        },
        'eventID': 'shardId-000000000000:49624450867430322871966858201536618369469192501878366210',
        'eventName': 'aws:kinesis:record',
        'eventVersion': '1.0',
        'eventSource': 'aws:kinesis',
        'awsRegion': 'us-west-2'
    }


@pytest.fixture
def kinesis_batch(kinesis_record):
    """Kinesis batch event."""
    return {
        'Records': [kinesis_record]
    }


class TestValidation:
    """Test event validation."""
    
    def test_valid_event(self, valid_transaction_event):
        """Valid event should pass validation."""
        error = validate_event(valid_transaction_event)
        assert error is None
    
    def test_missing_event_id(self, valid_transaction_event):
        """Missing event_id should fail validation."""
        del valid_transaction_event['event_id']
        error = validate_event(valid_transaction_event)
        assert error == "Missing required field: event_id"
    
    def test_missing_event_type(self, valid_transaction_event):
        """Missing event_type should fail validation."""
        del valid_transaction_event['event_type']
        error = validate_event(valid_transaction_event)
        assert error == "Missing required field: event_type"
    
    def test_invalid_event_type(self, valid_transaction_event):
        """Invalid event_type should fail validation."""
        valid_transaction_event['event_type'] = 'invalid_type'
        error = validate_event(valid_transaction_event)
        assert 'Invalid event_type' in error
    
    def test_invalid_timestamp(self, valid_transaction_event):
        """Invalid timestamp format should fail validation."""
        valid_transaction_event['event_ts'] = 'not-a-timestamp'
        error = validate_event(valid_transaction_event)
        assert 'Invalid event_ts format' in error


class TestFraudScoring:
    """Test fraud scoring logic."""
    
    def test_low_risk_transaction(self, valid_transaction_event):
        """Low risk transaction should score appropriately."""
        score = calculate_fraud_score(valid_transaction_event)
        
        assert score['risk_score'] < 40
        assert score['risk_level'] == 'LOW'
        assert score['is_flagged'] is False
        assert 'scored_at' in score
    
    def test_high_amount_risk(self):
        """High amount should increase risk score."""
        event = {
            'payload': {'amount': 8000.00, 'type': 'PAYMENT', 'isFraud': 0}
        }
        score = calculate_fraud_score(event)
        
        assert score['risk_score'] >= 30
        assert 'high_amount' in score['risk_reasons']
    
    def test_round_amount_risk(self):
        """Round amount should increase risk score."""
        event = {
            'payload': {'amount': 5000.00, 'type': 'PAYMENT', 'isFraud': 0}
        }
        score = calculate_fraud_score(event)
        
        assert 'round_amount' in score['risk_reasons']
    
    def test_upstream_fraud_flag(self):
        """Upstream fraud flag should significantly increase risk."""
        event = {
            'payload': {'amount': 100.00, 'type': 'PAYMENT', 'isFraud': 1}
        }
        score = calculate_fraud_score(event)
        
        assert score['risk_score'] >= 50
        assert 'upstream_fraud_flag' in score['risk_reasons']
    
    def test_high_risk_type(self):
        """High risk transaction type should increase score."""
        event = {
            'payload': {'amount': 100.00, 'type': 'CASH_OUT', 'isFraud': 0}
        }
        score = calculate_fraud_score(event)
        
        assert 'high_risk_type_cash_out' in score['risk_reasons']
    
    def test_maximum_score_capped(self, high_risk_transaction):
        """Risk score should be capped at 100."""
        score = calculate_fraud_score(high_risk_transaction)
        
        assert score['risk_score'] <= 100
        assert score['risk_level'] == 'HIGH'
        assert score['is_flagged'] is True


class TestEnrichment:
    """Test event enrichment."""
    
    def test_enrichment_adds_metadata(self, valid_transaction_event, kinesis_record):
        """Enrichment should add ingestion metadata."""
        enriched = enrich_event(valid_transaction_event, kinesis_record)
        
        assert 'ingested_ts' in enriched
        assert 'schema_version' in enriched
        assert enriched['schema_version'] == '1.0'
        assert 'kinesis_metadata' in enriched
        assert enriched['kinesis_metadata']['partitionKey'] == 'C123456'
    
    def test_enrichment_adds_fraud_scoring(self, valid_transaction_event, kinesis_record):
        """Enrichment should add fraud analysis for transactions."""
        enriched = enrich_event(valid_transaction_event, kinesis_record)
        
        assert 'fraud_analysis' in enriched
        assert 'risk_score' in enriched['fraud_analysis']
        assert 'risk_level' in enriched['fraud_analysis']


class TestDLQRouting:
    """Test DLQ message routing."""
    
    @patch('handler.sqs_client')
    def test_send_to_dlq(self, mock_sqs):
        """Should send properly formatted message to DLQ."""
        kinesis_metadata = {
            'partitionKey': 'test-key',
            'sequenceNumber': '12345',
            'approxArrivalTimestamp': 1704110400.0
        }
        
        send_to_dlq(
            error_type='ValidationError',
            error_message='Missing field',
            kinesis_metadata=kinesis_metadata,
            raw_payload='{"bad": "json"'
        )
        
        mock_sqs.send_message.assert_called_once()
        call_args = mock_sqs.send_message.call_args
        
        message_body = json.loads(call_args[1]['MessageBody'])
        assert message_body['error_type'] == 'ValidationError'
        assert message_body['error_message'] == 'Missing field'
        assert 'handled_at' in message_body
        assert message_body['kinesis'] == kinesis_metadata


class TestDynamoDBUpdates:
    """Test DynamoDB update logic."""
    
    @patch('handler.metrics_table')
    def test_update_metric_counter(self, mock_table):
        """Should atomically increment metric counter."""
        update_metric_counter(
            metric_name='purchases',
            window='2026-01-01T12:00',
            updated_ts='2026-01-01T12:00:30Z',
            increment=1
        )
        
        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args[1]
        
        assert call_args['Key']['pk'] == 'metric#purchases'
        assert call_args['Key']['sk'] == 'window#2026-01-01T12:00'
        assert call_args['ExpressionAttributeValues'][':inc'] == Decimal('1')
    
    @patch('handler.latest_state_table')
    def test_update_latest_state(self, mock_table):
        """Should update latest state for entity."""
        update_latest_state(
            entity_type='user',
            entity_id='C123456',
            event_ts='2026-01-01T12:00:00Z',
            state={'last_purchase_cents': 100050},
            updated_ts='2026-01-01T12:00:30Z'
        )
        
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]
        
        assert call_args['Item']['pk'] == 'user#C123456'
        assert call_args['Item']['last_event_ts'] == '2026-01-01T12:00:00Z'
        assert call_args['Item']['state']['last_purchase_cents'] == Decimal('100050')


class TestLambdaHandler:
    """Test main Lambda handler."""
    
    @patch('handler.s3_client')
    @patch('handler.metrics_table')
    @patch('handler.latest_state_table')
    def test_successful_processing(
        self,
        mock_state_table,
        mock_metrics_table,
        mock_s3,
        kinesis_batch
    ):
        """Valid event should be processed successfully."""
        response = lambda_handler(kinesis_batch, None)
        
        # Should have no failed items
        assert response['batchItemFailures'] == []
        
        # Should write to S3
        assert mock_s3.put_object.called
        
        # Should update DynamoDB
        assert mock_metrics_table.update_item.called
    
    @patch('handler.sqs_client')
    def test_invalid_json_to_dlq(self, mock_sqs):
        """Invalid JSON should be sent to DLQ."""
        kinesis_batch = {
            'Records': [{
                'kinesis': {
                    'partitionKey': 'test-key',
                    'sequenceNumber': '12345',
                    'data': base64.b64encode(b'not valid json').decode('utf-8'),
                    'approximateArrivalTimestamp': 1704110400.0
                }
            }]
        }
        
        response = lambda_handler(kinesis_batch, None)
        
        # Should send to DLQ
        assert mock_sqs.send_message.called
        
        # Should not include in batch failures (handled)
        assert response['batchItemFailures'] == []
    
    @patch('handler.sqs_client')
    def test_validation_error_to_dlq(self, mock_sqs):
        """Validation error should be sent to DLQ, not retried."""
        invalid_event = {'event_id': 'test', 'bad': 'data'}  # Missing required fields
        
        kinesis_batch = {
            'Records': [{
                'kinesis': {
                    'partitionKey': 'test-key',
                    'sequenceNumber': '12345',
                    'data': base64.b64encode(json.dumps(invalid_event).encode('utf-8')).decode('utf-8'),
                    'approximateArrivalTimestamp': 1704110400.0
                }
            }]
        }
        
        response = lambda_handler(kinesis_batch, None)
        
        # Should send to DLQ
        assert mock_sqs.send_message.called
        
        # Should not retry
        assert response['batchItemFailures'] == []
    
    @patch('handler.s3_client')
    @patch('handler.metrics_table')
    def test_transient_error_marked_for_retry(
        self,
        mock_metrics_table,
        mock_s3,
        kinesis_batch
    ):
        """Transient DynamoDB error should be marked for retry."""
        from botocore.exceptions import ClientError
        
        # Simulate throttling error
        mock_metrics_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException'}},
            'UpdateItem'
        )
        
        response = lambda_handler(kinesis_batch, None)
        
        # Should include sequence number for retry
        assert len(response['batchItemFailures']) == 1
        assert 'itemIdentifier' in response['batchItemFailures'][0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
