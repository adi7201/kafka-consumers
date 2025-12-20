import os
import psycopg2
import boto3
import time
import json
import logging
import uuid
from psycopg2.extras import RealDictCursor
from datetime import timedelta, datetime
from botocore.exceptions import ClientError

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

class S3Uploader:
    def __init__(self):
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.s3_client = boto3.client('s3', **self.data['s3'])
        self.bucket_name = self.data['s3']['rhenus-truck-images']
        logging.info('Initialized S3Uploader with bucket: %s', self.bucket_name)
    
    def upload_image(self, image_data, truck_no, event_type, timestamp):
        try:
            # Generate a unique filename
            filename = f"{truck_no}_{event_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
            s3_key = f"dock_images/{filename}"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=image_data,
                ContentType='image/jpeg',
                ACL='public-read'
            )
            
            # Generate public URL
            url = f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}"
            logging.info('Successfully uploaded image to S3: %s', url)
            return url
        except ClientError as e:
            logging.error('Failed to upload image to S3: %s', str(e))
            return None
        except Exception as e:
            logging.error('Unexpected error uploading to S3: %s', str(e))
            return None

class UpdateDynomoDB:
    def __init__(self):
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.partition_key = 'rhenus#transaction#id'
        dynamodb = boto3.resource('dynamodb', **self.data['dynomodb']) 
        table_name = 'rhenus_transaction_testing'
        self.table = dynamodb.Table(table_name)
        logging.info('Initialized UpdateDynomoDB class with table: %s', table_name)
        
    def insert(self, key_name, key_value, timestamp, status_value, image_url=None):
        try:
            update_expression = f'SET {key_name} = :value'
            expression_values = {':value': key_value.strftime('%Y-%m-%dT%H:%M:%SZ')}
            
            if image_url:
                update_expression += ', image_url = :image_url'
                expression_values[':image_url'] = image_url
            
            response = self.table.update_item(
                Key={
                    'transcation_id': self.partition_key,
                    'timestamp': timestamp
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            logging.info('Updated DynamoDB with %s: %s for transaction %s', key_name, key_value, self.partition_key)
        except Exception as e:
            logging.error('Failed to update DynamoDB: %s', str(e))

class Inbound:
    def __init__(self):
        self.s3_uploader = S3Uploader()
        self.update_to_dynomodb = UpdateDynomoDB()
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.connection = psycopg2.connect(
            **self.data['postgres'],
            cursor_factory=RealDictCursor
        )
        self.cursor = self.connection.cursor()
        logging.info('Connected to PostgreSQL database')
        
    def get_dock_image(self, timestamp, dock_no, order='ASC'):
        """Get dock image closest to the specified timestamp"""
        try:
            query = """
            SELECT timestamp, image 
            FROM dock_images 
            WHERE dock = %s
            """
            if order == 'ASC':
                query += " AND timestamp >= %s ORDER BY timestamp ASC"
            else:
                query += " AND timestamp <= %s ORDER BY timestamp DESC"
            query += " FETCH FIRST ROW ONLY"
            
            self.cursor.execute(query, (dock_no, timestamp))
            return self.cursor.fetchone()
        except Exception as e:
            logging.error('Error fetching dock image: %s', str(e))
            return None
        
    def process_and_upload_image(self, image_data, truck_no, event_type, timestamp):
        """Upload image to S3 and return URL"""
        if image_data:
            try:
                image_url = self.s3_uploader.upload_image(
                    image_data,
                    truck_no,
                    event_type,
                    timestamp
                )
                return image_url
            except Exception as e:
                logging.error('Error processing image for truck %s: %s', truck_no, str(e))
        return None
        
    def get_dock_state_change(self, dock_no, dock_assign_time, state_type):
        if state_type == "dock_in":
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
                # Get image for transaction start
                start_image = self.get_dock_image(transaction_start_time, truck['dock_no'], 'ASC')
                start_image_url = None
                
                if start_image and start_image.get('image'):
                    start_image_url = self.process_and_upload_image(
                        start_image['image'],
                        truck['truck_no'],
                        'transaction_start',
                        transaction_start_time
                    )
                
                self.cursor.execute(
                    f"UPDATE truck_cycle SET start_time = %s WHERE truck_no = %s AND timestamp = %s",
                    (transaction_start_time, truck['truck_no'], truck['timestamp'])
                )
                self.update_to_dynomodb.insert(
                    "transaction_start_time", 
                    transaction_start_time, 
                    truck['timestamp'], 
                    "transaction_start",
                    start_image_url
                )
                logging.info('Updated transaction start time for truck %s', truck['truck_no'])

        # Check if transaction end time is already set
        if truck['end_time'] is None and truck['dock_out'] is not None:
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
                # Get image for transaction end
                end_image = self.get_dock_image(transaction_end_time, truck['dock_no'], 'DESC')
                end_image_url = None
                
                if end_image and end_image.get('image'):
                    end_image_url = self.process_and_upload_image(
                        end_image['image'],
                        truck['truck_no'],
                        'transaction_end',
                        transaction_end_time
                    )
                
                self.cursor.execute(
                    f"UPDATE truck_cycle SET end_time = %s WHERE truck_no = %s AND timestamp = %s",
                    (transaction_end_time, truck['truck_no'], truck['timestamp'])
                )
                self.update_to_dynomodb.insert(
                    "transaction_end_time", 
                    transaction_end_time, 
                    truck['timestamp'], 
                    "transaction_end",
                    end_image_url
                )
                logging.info('Updated transaction end time for truck %s', truck['truck_no'])

        self.connection.commit()
        
    def truck_cycle(self):
        try:
            self.cursor.execute("SELECT DISTINCT dock_no FROM truck_cycle WHERE dock_assign_time IS NOT NULL AND update_to_dynomodb=False AND dock_assign_time > CURRENT_DATE AND bound_type='inbound'")
            dock_numbers = self.cursor.fetchall() 
            logging.info('Found %d unique dock numbers to process', len(dock_numbers))
            
            for dock_entry in dock_numbers:
                dock_no = dock_entry['dock_no']
                
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
                            # Get image for dock in
                            dock_in_image = self.get_dock_image(dock_in_time, dock_no, 'ASC')
                            dock_in_image_url = None
                            
                            if dock_in_image and dock_in_image.get('image'):
                                dock_in_image_url = self.process_and_upload_image(
                                    dock_in_image['image'],
                                    truck['truck_no'],
                                    'dock_in',
                                    dock_in_time
                                )
                            
                            self.cursor.execute(
                                "UPDATE truck_cycle SET dock_in = %s WHERE truck_no = %s AND timestamp = %s",
                                (dock_in_time, truck['truck_no'], truck['timestamp'])
                            )
                            self.update_to_dynomodb.insert(
                                "dock_in_time", 
                                dock_in_time, 
                                truck['timestamp'], 
                                "dock_in",
                                dock_in_image_url
                            )
                            self.connection.commit()
                    
                    # Process dock_out time (only if dock_in is set)
                    if truck['dock_in'] is not None and truck['dock_out'] is None:
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
                            # Get image for dock out
                            dock_out_image = self.get_dock_image(dock_out_time, dock_no, 'DESC')
                            dock_out_image_url = None
                            
                            if dock_out_image and dock_out_image.get('image'):
                                dock_out_image_url = self.process_and_upload_image(
                                    dock_out_image['image'],
                                    truck['truck_no'],
                                    'dock_out',
                                    dock_out_time
                                )
                            
                            self.cursor.execute(
                                "UPDATE truck_cycle SET dock_out = %s WHERE truck_no = %s AND timestamp = %s",
                                (dock_out_time, truck['truck_no'], truck['timestamp'])
                            )
                            self.update_to_dynomodb.insert(
                                "dock_out_time", 
                                dock_out_time, 
                                truck['timestamp'], 
                                "dock_out",
                                dock_out_image_url
                            )
                            self.connection.commit()
                    
                    # Process transaction times
                    if truck['dock_in'] is not None and truck['dock_out'] is not None:
                        self.update_transaction_times(truck)
                        
                        # Mark this truck as processed in DynamoDB
                        self.cursor.execute(
                            "UPDATE truck_cycle SET update_to_dynomodb = TRUE WHERE truck_no = %s AND timestamp = %s",
                            (truck['truck_no'], truck['timestamp'])
                        )
                        self.connection.commit()
                
        except Exception as e:
            logging.error('Error in truck_cycle: %s', str(e))
            print(f"Error updating PostgreSQL: {str(e)}")

while True:
    inbound = Inbound()
    inbound.truck_cycle()
