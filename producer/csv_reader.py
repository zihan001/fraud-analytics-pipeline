"""CSV reader for PaySim transaction dataset."""
import csv
import json
import logging
from typing import Iterator, Dict, Any

logger = logging.getLogger(__name__)


class PaySimReader:
    """Reads and parses PaySim CSV transaction data."""
    
    # PaySim CSV schema from Glue catalog
    COLUMNS = [
        "step",
        "type",
        "amount",
        "nameOrig",
        "oldbalanceOrg",
        "newbalanceOrig",
        "nameDest",
        "oldbalanceDest",
        "newbalanceDest",
        "isFraud",
        "isFlaggedFraud",
    ]
    
    def __init__(self, csv_path: str):
        """Initialize PaySim CSV reader.
        
        Args:
            csv_path: Path to PaySim CSV file
        """
        self.csv_path = csv_path
        self.rows_read = 0
    
    def read_transactions(self) -> Iterator[Dict[str, Any]]:
        """Read transactions from CSV file and yield as dictionaries.
        
        Yields:
            Dictionary with transaction data in JSON-ready format
            
        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        logger.info(f"Opening CSV file: {self.csv_path}")
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Validate CSV headers
                if reader.fieldnames != self.COLUMNS:
                    raise ValueError(
                        f"CSV headers mismatch. Expected {self.COLUMNS}, "
                        f"got {reader.fieldnames}"
                    )
                
                for row in reader:
                    self.rows_read += 1
                    
                    # Convert to proper types for JSON serialization
                    transaction = {
                        "step": int(row["step"]),
                        "type": row["type"],
                        "amount": float(row["amount"]),
                        "nameOrig": row["nameOrig"],
                        "oldbalanceOrg": float(row["oldbalanceOrg"]),
                        "newbalanceOrig": float(row["newbalanceOrig"]),
                        "nameDest": row["nameDest"],
                        "oldbalanceDest": float(row["oldbalanceDest"]),
                        "newbalanceDest": float(row["newbalanceDest"]),
                        "isFraud": int(row["isFraud"]),
                        "isFlaggedFraud": int(row["isFlaggedFraud"]),
                    }
                    
                    yield transaction
                    
                    # Log progress every 10,000 rows
                    if self.rows_read % 10000 == 0:
                        logger.info(f"Read {self.rows_read:,} transactions")
                        
        except FileNotFoundError:
            logger.error(f"CSV file not found: {self.csv_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading CSV at row {self.rows_read}: {e}")
            raise
    
    def transaction_to_json(self, transaction: Dict[str, Any]) -> str:
        """Convert transaction dictionary to JSON string.
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            JSON-formatted string
        """
        return json.dumps(transaction)
