import psycopg2
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
import pytz
import json
import time
import os
import logging

class AssingDock:
    def __init__(self):
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.connection = psycopg2.connect(
            **self.data['postgres']
        )
        self.cursor = self.connection.cursor()
       
        self.partition_key = 'rhenus#transaction#id'  # Replace this with the actual partition key value
        self.dynamodb = boto3.resource('dynamodb', **self.data['dynomodb'])
        table_name = 'rhenus_transaction'  # Your table name
        self.table = self.dynamodb.Table(table_name)
        
        # Set up logging
        todays_date = datetime.now().strftime("%Y-%m-%d")
        log_directory = os.path.join("logs", todays_date)
        os.makedirs(log_directory, exist_ok=True)
        log_filename = os.path.join(log_directory, f"{todays_date}_dock_assign.log")
        
        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("AssingDock initialized")
        print("AssingDock initialized")

    def insert_assign_dock(self):
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.combine(datetime.now().date(), datetime.min.time())  # start_date
            end_date = datetime.combine(datetime.now().date(), datetime.max.time())    # end_date
            items = []
            print(items)
            response = self.table.query(
                KeyConditionExpression=Key('transcation_id').eq(self.partition_key) &
                                      Key('timestamp').between(start_date.isoformat(), end_date.isoformat())
            )
            items.extend(response['Items'])

            check_query = "SELECT COUNT(*) FROM truck_cycle WHERE timestamp = '{}' AND truck_no = '{}'"
            for item in items:
                if item.get('dock_assign_time', False) and item.get('dock_no', False):
                    self.cursor.execute(f"SELECT dock_no, dock_assign_time FROM truck_cycle where timestamp='{item['timestamp']}' and truck_no='{item['vehicle_number']}'")
                    dock_no = self.cursor.fetchone()

                    if dock_no is not None:
                        existing_dock_no, existing_dock_assign_time = dock_no
                        if (
                            int(item['dock_no']) != existing_dock_no or
                            item['dock_assign_time'] != str(existing_dock_assign_time)
                        ):
                            self.cursor.execute(
                                f"""
                                UPDATE truck_cycle 
                                SET dock_no = '{item['dock_no']}', dock_assign_time = '{item['dock_assign_time']}'
                                WHERE timestamp = '{item['timestamp']}' AND truck_no = '{item['vehicle_number']}'
                                """
                            )
                            self.connection.commit()
                            self.logger.info(f"Updated entry for truck_no '{item['vehicle_number']}' with timestamp '{item['timestamp']}': new dock_no='{item['dock_no']}', new dock_assign_time='{item['dock_assign_time']}'")
                        else:
                            continue
                    else:                    
                        self.cursor.execute(f"INSERT INTO truck_cycle (timestamp, truck_no, gate_in, dock_no, dock_assign_time, bound_type) VALUES('{item['timestamp']}', '{item['vehicle_number']}', '{item['timestamp']}', '{item['dock_no']}', '{item['dock_assign_time']}', '{item['transaction_type']}')")
                        self.logger.info(f"Inserted new entry for truck_no '{item['vehicle_number']}' with timestamp '{item['timestamp']}' and dock_no '{item['dock_no']}'")
                        print(f"Inserted new entry for truck_no '{item['vehicle_number']}' with timestamp '{item['timestamp']}' and dock_no '{item['dock_no']}")

        except Exception as e:
            self.logger.error(f"Error in insert_assign_dock: {str(e)}")
            print(f"error: {e}")
if __name__ == "__main__":
    assigndock = AssingDock()
    while True:
        assigndock.insert_assign_dock()
        time.sleep(1)