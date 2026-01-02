"""Unit tests for producer/csv_reader.py - PaySim CSV reader."""
import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

from producer.csv_reader import PaySimReader


class TestPaySimReaderInitialization:
    """Test PaySimReader initialization."""

    def test_init_stores_csv_path(self):
        """Test that initialization stores CSV path."""
        csv_path = "/path/to/test.csv"
        reader = PaySimReader(csv_path)
        assert reader.csv_path == csv_path

    def test_init_sets_rows_read_to_zero(self):
        """Test that initialization sets rows_read counter to zero."""
        reader = PaySimReader("/path/to/test.csv")
        assert reader.rows_read == 0


class TestPaySimReaderValidCsvReading:
    """Test reading valid CSV files."""

    @pytest.fixture
    def valid_csv_file(self):
        """Create a temporary valid PaySim CSV file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            writer.writerow({
                "step": "1",
                "type": "PAYMENT",
                "amount": "9839.64",
                "nameOrig": "C1231006815",
                "oldbalanceOrg": "170136.00",
                "newbalanceOrig": "160296.36",
                "nameDest": "M1979787155",
                "oldbalanceDest": "0.00",
                "newbalanceDest": "0.00",
                "isFraud": "0",
                "isFlaggedFraud": "0",
            })
            writer.writerow({
                "step": "1",
                "type": "CASH_OUT",
                "amount": "181.00",
                "nameOrig": "C840083671",
                "oldbalanceOrg": "181.00",
                "newbalanceOrig": "0.00",
                "nameDest": "C38997010",
                "oldbalanceDest": "21182.00",
                "newbalanceDest": "0.00",
                "isFraud": "1",
                "isFlaggedFraud": "0",
            })
            temp_path = f.name

        yield temp_path

        # Cleanup
        os.unlink(temp_path)

    def test_reads_all_transactions(self, valid_csv_file):
        """Test that all transactions are read from CSV."""
        reader = PaySimReader(valid_csv_file)
        transactions = list(reader.read_transactions())
        assert len(transactions) == 2

    def test_converts_types_correctly(self, valid_csv_file):
        """Test that CSV strings are converted to correct Python types."""
        reader = PaySimReader(valid_csv_file)
        transaction = next(reader.read_transactions())

        assert isinstance(transaction["step"], int)
        assert isinstance(transaction["type"], str)
        assert isinstance(transaction["amount"], float)
        assert isinstance(transaction["nameOrig"], str)
        assert isinstance(transaction["oldbalanceOrg"], float)
        assert isinstance(transaction["newbalanceOrig"], float)
        assert isinstance(transaction["nameDest"], str)
        assert isinstance(transaction["oldbalanceDest"], float)
        assert isinstance(transaction["newbalanceDest"], float)
        assert isinstance(transaction["isFraud"], int)
        assert isinstance(transaction["isFlaggedFraud"], int)

    def test_parses_transaction_values_correctly(self, valid_csv_file):
        """Test that transaction values are parsed correctly."""
        reader = PaySimReader(valid_csv_file)
        transaction = next(reader.read_transactions())

        assert transaction["step"] == 1
        assert transaction["type"] == "PAYMENT"
        assert transaction["amount"] == 9839.64
        assert transaction["nameOrig"] == "C1231006815"
        assert transaction["oldbalanceOrg"] == 170136.00
        assert transaction["newbalanceOrig"] == 160296.36
        assert transaction["nameDest"] == "M1979787155"
        assert transaction["oldbalanceDest"] == 0.00
        assert transaction["newbalanceDest"] == 0.00
        assert transaction["isFraud"] == 0
        assert transaction["isFlaggedFraud"] == 0

    def test_reads_multiple_transactions_in_order(self, valid_csv_file):
        """Test that multiple transactions are read in correct order."""
        reader = PaySimReader(valid_csv_file)
        transactions = list(reader.read_transactions())

        assert transactions[0]["type"] == "PAYMENT"
        assert transactions[0]["isFraud"] == 0

        assert transactions[1]["type"] == "CASH_OUT"
        assert transactions[1]["isFraud"] == 1

    def test_increments_rows_read_counter(self, valid_csv_file):
        """Test that rows_read counter is incremented correctly."""
        reader = PaySimReader(valid_csv_file)
        list(reader.read_transactions())
        assert reader.rows_read == 2

    def test_iterator_works_with_for_loop(self, valid_csv_file):
        """Test that read_transactions works as an iterator in for loop."""
        reader = PaySimReader(valid_csv_file)
        count = 0
        for transaction in reader.read_transactions():
            assert isinstance(transaction, dict)
            count += 1
        assert count == 2


class TestPaySimReaderInvalidCsv:
    """Test handling of invalid CSV files."""

    def test_raises_file_not_found_for_missing_file(self):
        """Test that FileNotFoundError is raised for non-existent file."""
        reader = PaySimReader("/nonexistent/path/file.csv")
        with pytest.raises(FileNotFoundError):
            list(reader.read_transactions())

    def test_raises_value_error_for_wrong_headers(self):
        """Test that ValueError is raised when CSV headers don't match."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(["wrong", "headers", "here"])
            writer.writerow(["1", "2", "3"])
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            with pytest.raises(ValueError, match="CSV headers mismatch"):
                list(reader.read_transactions())
        finally:
            os.unlink(temp_path)

    def test_raises_value_error_for_invalid_integer(self):
        """Test that ValueError is raised for invalid integer values."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            writer.writerow({
                "step": "not_an_int",  # Invalid integer
                "type": "PAYMENT",
                "amount": "100.00",
                "nameOrig": "C123",
                "oldbalanceOrg": "0.00",
                "newbalanceOrig": "0.00",
                "nameDest": "M456",
                "oldbalanceDest": "0.00",
                "newbalanceDest": "0.00",
                "isFraud": "0",
                "isFlaggedFraud": "0",
            })
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            with pytest.raises(ValueError):
                list(reader.read_transactions())
        finally:
            os.unlink(temp_path)

    def test_raises_value_error_for_invalid_float(self):
        """Test that ValueError is raised for invalid float values."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            writer.writerow({
                "step": "1",
                "type": "PAYMENT",
                "amount": "not_a_float",  # Invalid float
                "nameOrig": "C123",
                "oldbalanceOrg": "0.00",
                "newbalanceOrig": "0.00",
                "nameDest": "M456",
                "oldbalanceDest": "0.00",
                "newbalanceDest": "0.00",
                "isFraud": "0",
                "isFlaggedFraud": "0",
            })
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            with pytest.raises(ValueError):
                list(reader.read_transactions())
        finally:
            os.unlink(temp_path)


class TestPaySimReaderEmptyFile:
    """Test handling of empty CSV files."""

    def test_reads_zero_transactions_from_empty_csv(self):
        """Test that empty CSV (headers only) yields no transactions."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            transactions = list(reader.read_transactions())
            assert len(transactions) == 0
            assert reader.rows_read == 0
        finally:
            os.unlink(temp_path)


class TestTransactionToJson:
    """Test transaction_to_json method."""

    def test_converts_transaction_to_json_string(self):
        """Test that transaction dictionary is converted to JSON string."""
        reader = PaySimReader("/dummy/path")
        transaction = {
            "step": 1,
            "type": "PAYMENT",
            "amount": 100.50,
            "nameOrig": "C123",
            "oldbalanceOrg": 1000.00,
            "newbalanceOrig": 899.50,
            "nameDest": "M456",
            "oldbalanceDest": 0.00,
            "newbalanceDest": 100.50,
            "isFraud": 0,
            "isFlaggedFraud": 0,
        }

        json_str = reader.transaction_to_json(transaction)
        assert isinstance(json_str, str)

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed == transaction

    def test_json_output_is_valid_format(self):
        """Test that JSON output has correct structure."""
        reader = PaySimReader("/dummy/path")
        transaction = {"step": 1, "type": "PAYMENT", "amount": 100.0}

        json_str = reader.transaction_to_json(transaction)
        parsed = json.loads(json_str)

        assert "step" in parsed
        assert "type" in parsed
        assert "amount" in parsed


class TestPaySimReaderEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_zero_amounts(self):
        """Test that zero amounts are handled correctly."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            writer.writerow({
                "step": "1",
                "type": "PAYMENT",
                "amount": "0.00",  # Zero amount
                "nameOrig": "C123",
                "oldbalanceOrg": "0.00",
                "newbalanceOrig": "0.00",
                "nameDest": "M456",
                "oldbalanceDest": "0.00",
                "newbalanceDest": "0.00",
                "isFraud": "0",
                "isFlaggedFraud": "0",
            })
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            transaction = next(reader.read_transactions())
            assert transaction["amount"] == 0.00
        finally:
            os.unlink(temp_path)

    def test_handles_large_amounts(self):
        """Test that large amounts are handled correctly."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()
            writer.writerow({
                "step": "1",
                "type": "TRANSFER",
                "amount": "9999999.99",  # Large amount
                "nameOrig": "C123",
                "oldbalanceOrg": "10000000.00",
                "newbalanceOrig": "0.01",
                "nameDest": "M456",
                "oldbalanceDest": "0.00",
                "newbalanceDest": "9999999.99",
                "isFraud": "1",
                "isFlaggedFraud": "1",
            })
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            transaction = next(reader.read_transactions())
            assert transaction["amount"] == 9999999.99
        finally:
            os.unlink(temp_path)

    def test_handles_all_transaction_types(self):
        """Test that all PaySim transaction types are handled."""
        transaction_types = ["PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"]

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            writer = csv.DictWriter(f, fieldnames=PaySimReader.COLUMNS)
            writer.writeheader()

            for txn_type in transaction_types:
                writer.writerow({
                    "step": "1",
                    "type": txn_type,
                    "amount": "100.00",
                    "nameOrig": "C123",
                    "oldbalanceOrg": "1000.00",
                    "newbalanceOrig": "900.00",
                    "nameDest": "M456",
                    "oldbalanceDest": "0.00",
                    "newbalanceDest": "100.00",
                    "isFraud": "0",
                    "isFlaggedFraud": "0",
                })
            temp_path = f.name

        try:
            reader = PaySimReader(temp_path)
            transactions = list(reader.read_transactions())
            assert len(transactions) == len(transaction_types)

            for i, txn_type in enumerate(transaction_types):
                assert transactions[i]["type"] == txn_type
        finally:
            os.unlink(temp_path)
