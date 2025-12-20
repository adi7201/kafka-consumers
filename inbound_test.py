import os
import psycopg2
import boto3
import time
import json
import logging
from psycopg2.extras import RealDictCursor
from datetime import timedelta, datetime

# Configure logging
todays_date = datetime.now().strftime("%Y-%m-%d")
log_directory = os.path.join("logs", todays_date)
os.makedirs(log_directory, exist_ok=True)
log_filename = os.path.join(log_directory, f"{todays_date}_insert_inbound.log")

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class UpdateDynomoDB():
    def __init__(self):
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.partition_key = 'rhenus#transaction#id'
        dynamodb = boto3.resource('dynamodb', **self.data['dynomodb']) 
        table_name = 'rhenus_transaction'
        self.table = dynamodb.Table(table_name)
        logging.info('Initialized UpdateDynomoDB class with table: %s', table_name)
        
    def insert(self, key_name, key_value, timestamp, status_value):
        try:
            response = self.table.update_item(
                Key={
                    'transcation_id': self.partition_key,
                    'timestamp': timestamp
                },
                UpdateExpression=f'SET {key_name} = :value',
                ExpressionAttributeValues={
                    ':value': key_value.strftime('%Y-%m-%dT%H:%M:%SZ'),
                }
            )
            logging.info('Updated DynamoDB with %s: %s for transaction %s', key_name, key_value, self.partition_key)
        except Exception as e:
            logging.error('Failed to update DynamoDB: %s', str(e))

class Inbound():
    def __init__(self):
        self.update_to_dynomodb = UpdateDynomoDB()
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.connection = psycopg2.connect(
            **self.data['postgres'],
            cursor_factory=RealDictCursor
        )
        self.cursor = self.connection.cursor()
        logging.info('Connected to PostgreSQL database')
        
    def get_dock_state_change(self, dock_no, dock_assign_time, state_type):
        if state_type == "dock_in":
            # Simple query to get first dock_status = 2 after dock_assign_time
            dock_in_query = """
            SELECT timestamp 
            FROM time_bucket_dock{}
            WHERE timestamp > '{}'
            AND dock_status = 2
            ORDER BY timestamp ASC
            LIMIT 1;
            """
            self.cursor.execute(dock_in_query.format(dock_no, dock_assign_time))
            result = self.cursor.fetchone()
            if result:
                return result['timestamp']
        else:
            # Existing logic for dock_out using state changes
            state_change_query = """
            WITH lead_dock_status AS (
                SELECT 
                    timestamp,
                    dock_status,
                    lead(dock_status, 1) OVER (ORDER BY timestamp) AS next_dock_status,
                    lead(timestamp, 1) OVER (ORDER BY timestamp) AS next_timestamp
                FROM time_bucket_dock{}
                WHERE timestamp > '{}'
                ORDER BY timestamp
            )
            SELECT 
                timestamp,
                next_timestamp,
                CASE 
                    WHEN next_dock_status = 3 AND dock_status = 2 THEN -1
                    WHEN next_dock_status = 1 AND dock_status = 2 THEN -1
                END AS state_change
            FROM lead_dock_status
            WHERE next_dock_status != dock_status
            AND (
                (next_dock_status = 3 AND dock_status = 2) OR
                (next_dock_status = 1 AND dock_status = 2)
            )
            LIMIT 1;
            """
            
            self.cursor.execute(state_change_query.format(dock_no, dock_assign_time))
            result = self.cursor.fetchone()
            if result and result['state_change'] == -1:
                return result['next_timestamp']
            
        return None

    def update_transaction_times(self, truck):
        table_name = f"time_bucket_dock{truck['dock_no']}"

        # Check if transaction start time is already set
        if truck['start_time'] is None:
            # Primary check using reach_truck or bopt
            self.cursor.execute(
                f"""
                SELECT timestamp FROM {table_name}
                WHERE (reach_truck > 0 OR bopt > 0)
                AND timestamp >= %s
                ORDER BY timestamp ASC LIMIT 1
                """,
                (truck['dock_in'],)
            )
            start_time_result = self.cursor.fetchone()

            if start_time_result:
                transaction_start_time = start_time_result['timestamp']
            elif truck['dock_out']:  # fallback using material > 0
                self.cursor.execute(
                    f"""
                    SELECT timestamp FROM {table_name}
                    WHERE material > 0
                    AND timestamp >= %s AND timestamp <= %s
                    ORDER BY timestamp ASC LIMIT 1
                    """,
                    (truck['dock_in'], truck['dock_out'])
                )
                fallback_start = self.cursor.fetchone()
                transaction_start_time = fallback_start['timestamp'] if fallback_start else None
            else:
                transaction_start_time = None

            if transaction_start_time:
                self.cursor.execute(
                    f"UPDATE truck_cycle SET start_time = %s WHERE truck_no = %s AND timestamp = %s",
                    (transaction_start_time, truck['truck_no'], truck['timestamp'])
                )
                self.update_to_dynomodb.insert("transaction_start_time", transaction_start_time, truck['timestamp'], "transaction_start")
                logging.info('Successfully updated PostgreSQL: Truck %s transaction start time at %s', truck['truck_no'], transaction_start_time)
                print(f"PostgreSQL Update: Truck {truck['truck_no']} transaction start time recorded at {transaction_start_time}")
            else:
                logging.warning(f"No transaction start time found for truck {truck['truck_no']}")
                print(f"Warning: No transaction start time found for truck {truck['truck_no']}")

        # Check if transaction end time is already set
        if truck['end_time'] is None and truck['dock_out'] is not None:
            # Primary check using reach_truck or bopt
            self.cursor.execute(
                f"""
                SELECT timestamp FROM {table_name}
                WHERE (reach_truck = 1 OR bopt = 1)
                AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp DESC LIMIT 1
                """,
                (truck['dock_in'], truck['dock_out'])
            )
            end_time_result = self.cursor.fetchone()

            if end_time_result:
                transaction_end_time = end_time_result['timestamp']
            else:
                # Fallback using material > 0
                self.cursor.execute(
                    f"""
                    SELECT timestamp FROM {table_name}
                    WHERE material > 0
                    AND timestamp >= %s AND timestamp <= %s
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (truck['dock_in'], truck['dock_out'])
                )
                fallback_end = self.cursor.fetchone()
                transaction_end_time = fallback_end['timestamp'] if fallback_end else None

            if transaction_end_time:
                self.cursor.execute(
                    f"UPDATE truck_cycle SET end_time = %s WHERE truck_no = %s AND timestamp = %s",
                    (transaction_end_time, truck['truck_no'], truck['timestamp'])
                )
                self.update_to_dynomodb.insert("transaction_end_time", transaction_end_time, truck['timestamp'], "transaction_end")
                logging.info('Successfully updated PostgreSQL: Truck %s transaction end time at %s', truck['truck_no'], transaction_end_time)
                print(f"PostgreSQL Update: Truck {truck['truck_no']} transaction end time recorded at {transaction_end_time}")
            else:
                logging.warning(f"No transaction end time found for truck {truck['truck_no']}")
                print(f"Warning: No transaction end time found for truck {truck['truck_no']}")

        self.connection.commit()
        
    def truck_cycle(self):
        try:
            # Get all unique dock numbers that have assigned trucks
            self.cursor.execute("SELECT DISTINCT dock_no FROM truck_cycle WHERE dock_assign_time IS NOT NULL AND update_to_dynomodb=False AND dock_assign_time > CURRENT_DATE AND bound_type='inbound'")
            dock_numbers = self.cursor.fetchall() 
            logging.info('Found %d unique dock numbers to process', len(dock_numbers))
            
            # Process each dock number individually
            for dock_entry in dock_numbers:
                dock_no = dock_entry['dock_no']
                
                # Get all trucks assigned to this dock, ordered by dock_assign_time
                self.cursor.execute("""
                    SELECT * FROM truck_cycle 
                    WHERE dock_no = %s AND dock_assign_time IS NOT NULL 
                    AND update_to_dynomodb=False AND dock_assign_time > CURRENT_DATE 
                    AND bound_type='inbound'
                    ORDER BY dock_assign_time ASC
                """, (dock_no,))
                
                trucks = self.cursor.fetchall()
                logging.info('Processing %d trucks for dock %s', len(trucks), dock_no)
                
                for truck in trucks:
                    # Process dock_in time
                    if truck['dock_in'] is None:
                        # Get first dock_status = 2 after dock_assign_time
                        dock_in_query = """
                        SELECT timestamp 
                        FROM time_bucket_dock{}
                        WHERE timestamp > %s
                        AND dock_status = 2
                        ORDER BY timestamp ASC
                        LIMIT 1
                        """
                        
                        self.cursor.execute(dock_in_query.format(dock_no), (truck['dock_assign_time'],))
                        dock_in_result = self.cursor.fetchone()
                        
                        if dock_in_result:
                            dock_in_time = dock_in_result['timestamp']
                            self.cursor.execute(
                                "UPDATE truck_cycle SET dock_in = %s WHERE truck_no = %s AND timestamp = %s",
                                (dock_in_time, truck['truck_no'], truck['timestamp'])
                            )
                            self.update_to_dynomodb.insert("dock_in_time", dock_in_time, truck['timestamp'], "dock_in")
                            self.connection.commit()
                            logging.info('Updated PostgreSQL: Truck %s (dock %s) dock_in time at %s', 
                                        truck['truck_no'], dock_no, dock_in_time)
                            print(f"PostgreSQL Update: Truck {truck['truck_no']} (dock {dock_no}) dock_in time recorded at {dock_in_time}")
                    
                    # Process dock_out time (only if dock_in is set)
                    if truck['dock_in'] is not None and truck['dock_out'] is None:
                        # Get state change for dock_out
                        dock_out_query = """
                        WITH lead_dock_status AS (
                            SELECT 
                                timestamp,
                                dock_status,
                                lead(dock_status, 1) OVER (ORDER BY timestamp) AS next_dock_status,
                                lead(timestamp, 1) OVER (ORDER BY timestamp) AS next_timestamp
                            FROM time_bucket_dock{}
                            WHERE timestamp > %s
                            ORDER BY timestamp
                        )
                        SELECT 
                            timestamp,
                            next_timestamp
                        FROM lead_dock_status
                        WHERE (next_dock_status = 3 AND dock_status = 2) OR
                              (next_dock_status = 1 AND dock_status = 2)
                        ORDER BY timestamp ASC
                        LIMIT 1
                        """
                        
                        self.cursor.execute(dock_out_query.format(dock_no), (truck['dock_in'],))
                        dock_out_result = self.cursor.fetchone()
                        
                        if dock_out_result:
                            dock_out_time = dock_out_result['next_timestamp']
                            self.cursor.execute(
                                "UPDATE truck_cycle SET dock_out = %s WHERE truck_no = %s AND timestamp = %s",
                                (dock_out_time, truck['truck_no'], truck['timestamp'])
                            )
                            self.update_to_dynomodb.insert("dock_out_time", dock_out_time, truck['timestamp'], "dock_out")
                            self.connection.commit()
                            logging.info('Updated PostgreSQL: Truck %s (dock %s) dock_out time at %s', 
                                        truck['truck_no'], dock_no, dock_out_time)
                            print(f"PostgreSQL Update: Truck {truck['truck_no']} (dock {dock_no}) dock_out time recorded at {dock_out_time}")
                    
                    # Process transaction times
                    if truck['dock_in'] is not None and truck['dock_out'] is not None:
                        self.update_transaction_times(truck)
                        
                        # Mark this truck as processed in DynamoDB
                        self.cursor.execute(
                            "UPDATE truck_cycle SET update_to_dynomodb = TRUE WHERE truck_no = %s AND timestamp = %s",
                            (truck['truck_no'], truck['timestamp'])
                        )
                        self.connection.commit()
                        logging.info('Marked truck %s as processed in DynamoDB', truck['truck_no'])
                
        except Exception as e:
            logging.error('Error in truck_cycle: %s', str(e))
            print(f"Error updating PostgreSQL: {str(e)}")

while True:
    inbound = Inbound()
    inbound.truck_cycle()
    time.sleep(0.1)