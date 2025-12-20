import psycopg2
import boto3
import time
import json
import logging
import os
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Set up logging
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
        logging.info("Initialized UpdateDynomoDB")
        print("initialized UpdateDynomodb")

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
            logging.info(f"Updated DynamoDB: {key_name} = {key_value} for transaction {timestamp}")
            print(f"Updated DynamoDB: {key_name} = {key_value} for transaction {timestamp}")
        except Exception as e:
            logging.error(f"Failed to update DynamoDB: {e}")
            print(f"failed to update dynomoDb:{e}")

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
        logging.info("Initialized Inbound")
        print("initialized inbound")

    def truck_cycle(self):
        try:
            # Iterate over docks 1 to 20
            for dock_no in range(1, 21):
                logging.info(f"Checking dock_no {dock_no}")
                print(f"Checking dock_no {dock_no}")

                # Fetch trucks assigned to this dock
                self.cursor.execute(f"""
                    SELECT * FROM truck_cycle 
                    WHERE dock_no = '{dock_no}'  -- Treat dock_no as text
                    AND dock_assign_time IS NOT NULL 
                    AND update_to_dynomodb = False 
                    AND dock_assign_time > CURRENT_DATE 
                    AND bound_type = 'inbound'
                """)
                trucks = self.cursor.fetchall()
                logging.info(f"Fetched {len(trucks)} trucks for dock_no {dock_no}")
                print(f"Fetched {len(trucks)} trucks for dock_no {dock_no}")

                for truck in trucks:
                    dock_assign_time = truck['dock_assign_time']

                    # Query to fetch state changes after dock_assign_time
                    self.cursor.execute(f"""
                        WITH lead_dock_status AS (
                            SELECT 
                                timestamp,
                                dock_status,
                                lead(dock_status, 1) OVER (ORDER BY timestamp) AS next_dock_status,
                                lead(timestamp, 1) OVER (ORDER BY timestamp) AS next_timestamp
                            FROM time_bucket_dock{dock_no}
                            WHERE timestamp > '{dock_assign_time}'
                        )
                        SELECT 
                            timestamp,
                            next_timestamp,
                            CASE 
                                WHEN next_dock_status = 0 AND dock_status = 0 THEN 0
                                WHEN next_dock_status = 1 AND dock_status = 1 THEN 0
                                WHEN next_dock_status = 2 AND dock_status = 2 THEN 0
                                WHEN next_dock_status = 1 AND dock_status = 0 THEN 0
                                WHEN next_dock_status = 0 AND dock_status = 1 THEN 0
                                WHEN next_dock_status = 2 AND dock_status = 3 THEN 1
                                WHEN next_dock_status = 2 AND dock_status = 1 THEN 1
                                WHEN next_dock_status = 3 AND dock_status = 2 THEN -1
                                WHEN next_dock_status = 1 AND dock_status = 2 THEN -1
                            END AS state_change
                        FROM lead_dock_status
                        WHERE next_dock_status != dock_status;
                    """)
                    dock_data = self.cursor.fetchall()
                    logging.info(f"Dock data for dock_no {dock_no}: {dock_data}")
                    print(f"Dock data for dock_no {dock_no}: {dock_data}")

                    # Process dock_data to determine dock_in and dock_out times
                    for data in dock_data:
                        if data['state_change'] == 1 and truck['dock_in'] is None:
                            # Truck has arrived (dock_in)
                            dock_in_time = data['next_timestamp']
                            try:
                                self.cursor.execute(f"""
                                    UPDATE truck_cycle 
                                    SET dock_in = '{dock_in_time}' 
                                    WHERE truck_no = '{truck['truck_no']}' 
                                    AND timestamp = '{truck['timestamp']}'
                                """)
                                self.connection.commit()
                                logging.info(f"Truck {truck['truck_no']} docked in at {dock_in_time} for dock_no {dock_no}")
                                print(f"Truck {truck['truck_no']} docked in at {dock_in_time} for dock_no {dock_no}")
                                self.update_to_dynomodb.insert("dock_in_time", dock_in_time, truck['timestamp'], "dock_in")
                            except Exception as e:
                                logging.error(f"Error updating dock_in time for dock_no {dock_no}: {e}")
                                print(f"Error updating dock_in time for dock_no {dock_no}: {e}")

                        elif data['state_change'] == -1 and truck['dock_in'] is not None and truck['dock_out'] is None:
                            # Truck has departed (dock_out)
                            dock_out_time = data['next_timestamp']
                            try:
                                self.cursor.execute(f"""
                                    UPDATE truck_cycle 
                                    SET dock_out = '{dock_out_time}' 
                                    WHERE truck_no = '{truck['truck_no']}' 
                                    AND timestamp = '{truck['timestamp']}'
                                """)
                                self.connection.commit()
                                self.update_to_dynomodb.insert("dock_out_time", dock_out_time, truck['timestamp'], "dock_out")
                                logging.info(f"Truck {truck['truck_no']} docked out at {dock_out_time} for dock_no {dock_no}")
                                print(f"Truck {truck['truck_no']} docked out at {dock_out_time} for dock_no {dock_no}")

                                # Fetch transaction start time
                                self.cursor.execute(f"""
                                    SELECT timestamp 
                                    FROM time_bucket_dock{dock_no}
                                    WHERE (reach_truck > 0 OR bopt > 0)
                                    AND timestamp BETWEEN '{truck['dock_in']}' AND '{dock_out_time}'
                                    ORDER BY timestamp ASC 
                                    LIMIT 1
                                """)
                                start_time_result = self.cursor.fetchone()
                                if start_time_result:
                                    start_time = start_time_result['timestamp']
                                    self.cursor.execute(f"""
                                        UPDATE truck_cycle 
                                        SET start_time = '{start_time}' 
                                        WHERE truck_no = '{truck['truck_no']}' 
                                        AND timestamp = '{truck['timestamp']}'
                                    """)
                                    self.connection.commit()
                                    self.update_to_dynomodb.insert("start_time", start_time, truck['timestamp'], "start_time")
                                    logging.info(f"Truck {truck['truck_no']} transaction started at {start_time} for dock_no {dock_no}")
                                    print(f"Truck {truck['truck_no']} transaction started at {start_time} for dock_no {dock_no}")

                                # Fetch transaction end time
                                self.cursor.execute(f"""
                                    SELECT timestamp 
                                    FROM time_bucket_dock{dock_no}
                                    WHERE reach_truck = 1
                                    AND timestamp BETWEEN '{truck['dock_in']}' AND '{dock_out_time}'
                                    ORDER BY timestamp DESC 
                                    LIMIT 1
                                """)
                                end_time_result = self.cursor.fetchone()
                                if end_time_result:
                                    end_time = end_time_result['timestamp']
                                    self.cursor.execute(f"""
                                        UPDATE truck_cycle 
                                        SET end_time = '{end_time}' 
                                        WHERE truck_no = '{truck['truck_no']}' 
                                        AND timestamp = '{truck['timestamp']}'
                                    """)
                                    self.connection.commit()
                                    self.update_to_dynomodb.insert("end_time", end_time, truck['timestamp'], "end_time")
                                    logging.info(f"Truck {truck['truck_no']} transaction ended at {end_time} for dock_no {dock_no}")
                                    print(f"Truck {truck['truck_no']} transaction ended at {end_time} for dock_no {dock_no}")

                            except Exception as e:
                                logging.error(f"Error updating dock_out time for dock_no {dock_no}: {e}")
                                print(f"Error updating dock_out time for dock_no {dock_no}: {e}")

        except Exception as e:
            logging.error(f"Error in truck_cycle: {e}")
            print(f"Error in truck_cycle: {e}")
inbound = Inbound()   
while True:
    inbound.truck_cycle()
    time.sleep(1)
