"""
Lambda handler for fraud analytics pipeline.

Processes Kinesis events with:
- Fraud scoring and enrichment
- DynamoDB updates for live metrics/state
- DLQ routing for invalid events
- Partial batch failure response
- Structured JSON logging
"""
import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

# AWS Clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sqs_client = boto3.client('sqs')

# Environment configuration
ENRICHED_BUCKET = os.environ.get('ENRICHED_BUCKET', '')
ENRICHED_PREFIX = os.environ.get('ENRICHED_PREFIX', 'enriched/')
METRICS_TABLE = os.environ.get('METRICS_TABLE', '')
LATEST_STATE_TABLE = os.environ.get('LATEST_STATE_TABLE', '')
DLQ_URL = os.environ.get('DLQ_URL', '')

# Initialize DynamoDB tables
metrics_table = dynamodb.Table(METRICS_TABLE) if METRICS_TABLE else None
latest_state_table = dynamodb.Table(LATEST_STATE_TABLE) if LATEST_STATE_TABLE else None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Kinesis event processing.
    
    Returns partial batch failure response for transient errors.
    """
    records = event.get('Records', [])
    
    # Processing metrics
    total_records = len(records)
    success_count = 0
    dlq_count = 0
    failed_items = []
    
    print(json.dumps({
        'message': 'Starting batch processing',
        'total_records': total_records,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }))
    
    for record in records:
        try:
            # Extract Kinesis metadata
            sequence_number = record['kinesis']['sequenceNumber']
            partition_key = record['kinesis']['partitionKey']
            approx_arrival = record['kinesis']['approximateArrivalTimestamp']
            
            # Decode and parse event
            payload_bytes = base64.b64decode(record['kinesis']['data'])
            payload_str = payload_bytes.decode('utf-8')
            event_data = json.loads(payload_str)
            
            # Validate required fields
            validation_error = validate_event(event_data)
            if validation_error:
                # Send to DLQ and mark as handled (don't retry)
                send_to_dlq(
                    error_type='ValidationError',
                    error_message=validation_error,
                    kinesis_metadata={
                        'partitionKey': partition_key,
                        'sequenceNumber': sequence_number,
                        'approxArrivalTimestamp': approx_arrival
                    },
                    raw_payload=payload_str  # Truncation handled in send_to_dlq
                )
                dlq_count += 1
                print(json.dumps({
                    'level': 'WARNING',
                    'message': 'Validation error - sent to DLQ',
                    'error': validation_error,
                    'sequence_number': sequence_number
                }))
                continue
            
            # Enrich event with metadata
            enriched_event = enrich_event(event_data, record)
            
            # Process based on event type
            process_success = process_event(enriched_event)
            
            if process_success:
                success_count += 1
                print(json.dumps({
                    'level': 'INFO',
                    'message': 'Event processed successfully',
                    'event_id': event_data.get('event_id'),
                    'event_type': event_data.get('event_type'),
                    'sequence_number': sequence_number
                }))
            else:
                # Transient failure - mark for retry
                failed_items.append({'itemIdentifier': sequence_number})
                print(json.dumps({
                    'level': 'ERROR',
                    'message': 'Transient processing failure',
                    'sequence_number': sequence_number
                }))
                
        except json.JSONDecodeError as e:
            # Invalid JSON - send to DLQ
            send_to_dlq(
                error_type='JSONDecodeError',
                error_message=str(e),
                kinesis_metadata={
                    'partitionKey': record['kinesis']['partitionKey'],
                    'sequenceNumber': record['kinesis']['sequenceNumber'],
                    'approxArrivalTimestamp': record['kinesis']['approximateArrivalTimestamp']
                },
                raw_payload=base64.b64decode(record['kinesis']['data']).decode('utf-8', errors='replace')[:4000]
            )
            dlq_count += 1
            print(json.dumps({
                'level': 'WARNING',
                'message': 'JSON decode error - sent to DLQ',
                'error': str(e),
                'sequence_number': record['kinesis']['sequenceNumber']
            }))
            
        except Exception as e:
            # Unexpected error - log and mark for retry
            print(json.dumps({
                'level': 'ERROR',
                'message': 'Unexpected error processing record',
                'error': str(e),
                'error_type': type(e).__name__,
                'sequence_number': record['kinesis']['sequenceNumber']
            }))
            failed_items.append({'itemIdentifier': record['kinesis']['sequenceNumber']})
    
    # Log final metrics
    print(json.dumps({
        'message': 'Batch processing complete',
        'total_records': total_records,
        'success': success_count,
        'dlq_count': dlq_count,
        'transient_failures': len(failed_items),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }))
    
    # Return partial batch failure response
    return {
        'batchItemFailures': failed_items
    }


def validate_event(event: Dict[str, Any]) -> Optional[str]:
    """Validate required fields in event. Returns error message if invalid."""
    required_fields = ['event_id', 'event_type', 'event_ts', 'payload']
    
    for field in required_fields:
        if field not in event:
            return f"Missing required field: {field}"
    
    # Validate event_type
    valid_types = ['page_view', 'purchase', 'error', 'heartbeat', 'device_status', 'transaction']
    if event['event_type'] not in valid_types:
        return f"Invalid event_type: {event['event_type']}. Must be one of {valid_types}"
    
    # Validate event_ts format
    try:
        datetime.fromisoformat(event['event_ts'].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return f"Invalid event_ts format: {event.get('event_ts')}. Must be ISO8601"
    
    # Validate event-type-specific requirements
    payload = event.get('payload', {})
    if event['event_type'] in ['device_status', 'heartbeat']:
        if not payload.get('device_id'):
            return f"Missing required field 'device_id' for {event['event_type']} events"
    
    return None


def enrich_event(event: Dict[str, Any], kinesis_record: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich event with fraud scoring and metadata."""
    enriched = event.copy()
    
    # Add ingestion metadata
    enriched['ingested_ts'] = datetime.now(timezone.utc).isoformat()
    enriched['schema_version'] = '1.0'
    enriched['kinesis_metadata'] = {
        'partitionKey': kinesis_record['kinesis']['partitionKey'],
        'sequenceNumber': kinesis_record['kinesis']['sequenceNumber'],
        'approxArrivalTimestamp': kinesis_record['kinesis']['approximateArrivalTimestamp']
    }
    
    # Add fraud scoring for transaction events
    if event['event_type'] in ['transaction', 'purchase']:
        enriched['fraud_analysis'] = calculate_fraud_score(event)
    
    return enriched


def calculate_fraud_score(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate fraud risk score based on transaction characteristics.
    
    Fraud indicators:
    - High transaction amount (>$5000)
    - Round amounts (potential structuring)
    - Unusual velocity patterns
    - Known fraud flag from upstream
    """
    payload = event.get('payload', {})
    risk_reasons = []
    risk_score = 0
    
    # Check amount-based rules
    amount = float(payload.get('amount', 0))
    if amount > 5000:
        risk_score += 30
        risk_reasons.append('high_amount')
    
    if amount != 0 and amount % 1000 == 0:
        risk_score += 20
        risk_reasons.append('round_amount')
    
    # Check for upstream fraud flag
    if payload.get('isFraud') == 1 or payload.get('is_fraud'):
        risk_score += 50
        risk_reasons.append('upstream_fraud_flag')
    
    # Check transaction type risk
    tx_type = payload.get('type', '').upper()
    high_risk_types = ['CASH_OUT', 'TRANSFER']
    if tx_type in high_risk_types:
        risk_score += 15
        risk_reasons.append(f'high_risk_type_{tx_type.lower()}')
    
    # Cap score at 100
    risk_score = min(risk_score, 100)
    
    # Determine risk level
    if risk_score >= 70:
        risk_level = 'HIGH'
        is_flagged = True
    elif risk_score >= 40:
        risk_level = 'MEDIUM'
        is_flagged = True
    else:
        risk_level = 'LOW'
        is_flagged = False
    
    return {
        'risk_score': risk_score,
        'risk_level': risk_level,
        'is_flagged': is_flagged,
        'risk_reasons': risk_reasons,
        'scored_at': datetime.now(timezone.utc).isoformat()
    }


def process_event(event: Dict[str, Any]) -> bool:
    """
    Process event by writing to S3 and updating DynamoDB.
    
    Returns True on success, False on transient failure (for retry).
    """
    try:
        # Write enriched event to S3
        write_to_s3(event)
        
        # Update DynamoDB based on event type
        update_dynamodb(event)
        
        return True
    
    except ValueError as e:
        # Validation errors discovered during processing - send to DLQ
        print(json.dumps({
            'level': 'WARNING',
            'message': 'Validation error during processing - sending to DLQ',
            'error': str(e),
            'event_id': event.get('event_id')
        }))
        send_to_dlq(
            error_type='ProcessingValidationError',
            error_message=str(e),
            kinesis_metadata=event.get('kinesis_metadata', {}),
            raw_payload=json.dumps(event, default=str)[:4000],
            decoded_json=event
        )
        return True  # Mark as handled (don't retry)
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        
        # Transient errors that should be retried
        transient_errors = [
            'ProvisionedThroughputExceededException',
            'ThrottlingException',
            'RequestLimitExceeded',
            'ServiceUnavailable',
            'InternalServerError'
        ]
        
        if error_code in transient_errors or error_code.startswith('5'):
            print(json.dumps({
                'level': 'WARNING',
                'message': 'Transient AWS error',
                'error_code': error_code,
                'error': str(e)
            }))
            return False  # Signal retry
        else:
            # Non-transient error - log but don't retry
            print(json.dumps({
                'level': 'ERROR',
                'message': 'Non-transient AWS error',
                'error_code': error_code,
                'error': str(e)
            }))
            return True  # Mark as "handled"
            
    except Exception as e:
        print(json.dumps({
            'level': 'ERROR',
            'message': 'Unexpected error in process_event',
            'error': str(e),
            'error_type': type(e).__name__
        }))
        return False  # Signal retry for unknown errors


def write_to_s3(event: Dict[str, Any]) -> None:
    """Write enriched event to S3 with partitioning by date/hour."""
    if not ENRICHED_BUCKET:
        return
    
    # Parse event timestamp for partitioning
    event_ts = datetime.fromisoformat(event['event_ts'].replace('Z', '+00:00'))
    dt = event_ts.strftime('%Y-%m-%d')
    hr = event_ts.strftime('%H')
    
    # Generate S3 key
    event_id = event.get('event_id', 'unknown')
    s3_key = f"{ENRICHED_PREFIX}dt={dt}/hr={hr}/{event_id}.json"
    
    # Write to S3
    s3_client.put_object(
        Bucket=ENRICHED_BUCKET,
        Key=s3_key,
        Body=json.dumps(event, default=str),
        ContentType='application/json'
    )


def update_dynamodb(event: Dict[str, Any]) -> None:
    """Update DynamoDB metrics and latest_state based on event type."""
    if not metrics_table or not latest_state_table:
        return
    
    event_type = event['event_type']
    event_ts = event['event_ts']
    payload = event.get('payload', {})
    
    # Extract minute window for metrics
    ts = datetime.fromisoformat(event_ts.replace('Z', '+00:00'))
    minute_window = ts.strftime('%Y-%m-%dT%H:%M')
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Update metrics based on event type
    if event_type == 'page_view':
        update_metric_counter('page_views', minute_window, now_iso)
        
    elif event_type in ['purchase', 'transaction']:
        update_metric_counter('purchases', minute_window, now_iso)
        
        # Update revenue if amount present
        amount_cents = int(float(payload.get('amount', 0)) * 100)
        if amount_cents > 0:
            update_metric_counter('revenue_cents', minute_window, now_iso, increment=amount_cents)
        
        # Update latest state for user
        user_id = payload.get('user_id') or payload.get('nameOrig')
        if user_id:
            update_latest_state(
                entity_type='user',
                entity_id=str(user_id),
                event_ts=event_ts,
                state={
                    'last_purchase_cents': amount_cents,
                    'last_purchase_ts': event_ts,
                    'transaction_type': payload.get('type', 'UNKNOWN')
                },
                updated_ts=now_iso
            )
            
    elif event_type == 'error':
        update_metric_counter('errors', minute_window, now_iso)
        
        # Update latest error state for service
        service_name = payload.get('service_name')
        if service_name:
            update_latest_state(
                entity_type='service',
                entity_id=service_name,
                event_ts=event_ts,
                state={
                    'last_error': payload.get('error_code', 'unknown'),
                    'message': payload.get('message', '')[:256],  # Truncate
                    'last_error_ts': event_ts
                },
                updated_ts=now_iso
            )
            
    elif event_type in ['heartbeat', 'device_status']:
        update_metric_counter('heartbeats', minute_window, now_iso)
        
        # Update device state
        device_id = payload.get('device_id')
        if device_id:
            update_latest_state(
                entity_type='device',
                entity_id=device_id,
                event_ts=event_ts,
                state={
                    'status': payload.get('status', 'unknown'),
                    'battery': payload.get('battery'),
                    'temp': payload.get('temp'),
                    'last_seen': event_ts
                },
                updated_ts=now_iso
            )
        else:
            # Defensive check - should be caught by validate_event
            raise ValueError(f"device_id required for {event_type} events (validation missed)")


def update_metric_counter(
    metric_name: str,
    window: str,
    updated_ts: str,
    increment: int = 1
) -> None:
    """Atomically increment metric counter for time window."""
    if not metrics_table:
        return
    
    try:
        metrics_table.update_item(
            Key={
                'pk': f'metric#{metric_name}',
                'sk': f'window#{window}'
            },
            UpdateExpression='SET updated_ts = :ts ADD #count :inc',
            ExpressionAttributeNames={
                '#count': 'count'
            },
            ExpressionAttributeValues={
                ':ts': updated_ts,
                ':inc': Decimal(str(increment))
            }
        )
    except ClientError as e:
        # Let transient errors propagate for retry
        raise


def update_latest_state(
    entity_type: str,
    entity_id: str,
    event_ts: str,
    state: Dict[str, Any],
    updated_ts: str
) -> None:
    """Update latest state for an entity."""
    if not latest_state_table:
        return
    
    try:
        # Convert numeric values to Decimal for DynamoDB
        state_converted = {
            k: Decimal(str(v)) if isinstance(v, (int, float)) else v
            for k, v in state.items()
            if v is not None
        }
        
        latest_state_table.put_item(
            Item={
                'pk': f'{entity_type}#{entity_id}',
                'last_event_ts': event_ts,
                'updated_ts': updated_ts,
                'state': state_converted
            }
        )
    except ClientError as e:
        # Let transient errors propagate for retry
        raise


def send_to_dlq(
    error_type: str,
    error_message: str,
    kinesis_metadata: Dict[str, Any],
    raw_payload: str,
    decoded_json: Optional[Dict[str, Any]] = None
) -> None:
    """Send invalid event to DLQ with error context."""
    if not DLQ_URL:
        return
    
    dlq_message = {
        'error_type': error_type,
        'error_message': error_message,
        'handled_at': datetime.now(timezone.utc).isoformat(),
        'kinesis': kinesis_metadata,
        'raw_payload_truncated': raw_payload[:4000]
    }
    
    if decoded_json:
        dlq_message['decoded_json_if_any'] = decoded_json
    
    try:
        sqs_client.send_message(
            QueueUrl=DLQ_URL,
            MessageBody=json.dumps(dlq_message, default=str)
        )
    except Exception as e:
        print(json.dumps({
            'level': 'ERROR',
            'message': 'Failed to send message to DLQ',
            'error': str(e)
        }))
