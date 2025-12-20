import psycopg2
import boto3
import json
import pytz
import logging
from datetime import datetime
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from botocore.exceptions import NoCredentialsError, ClientError
import os
import sys

# Set up logging
logging.basicConfig(
    filename='error_log.log',  # Log file
    level=logging.ERROR,  # Log only errors and higher
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
)

# DynamoDB uploader class
class DynamoDBUploader:
    def __init__(self, table_name, db_conn):
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.s3_client = boto3.client('s3')
        self.table = self.dynamodb.Table(table_name)
        self.db_conn = db_conn
        self.s3_bucket = 'rhenus-truck-images'
        self.s3_video_prefix = 'rhenus-gatein-smart-record-video/'

    def upload_video_to_s3(self, video_path):
        """Upload video file to S3 and return the S3 HTTP URL"""
        try:
            if not video_path or not os.path.exists(video_path):
                print(f"Video file not found: {video_path}")
                return None
            
            filename = os.path.basename(video_path)
            s3_key = f"{self.s3_video_prefix}{filename}"
            self.s3_client.upload_file(video_path, self.s3_bucket, s3_key)
            
            # Return S3 HTTP URL (not s3://)
            s3_url = f"https://{self.s3_bucket}.s3.ap-south-1.amazonaws.com/{s3_key}"
            print(f"Video uploaded to S3: {s3_url}")
            return s3_url

        except Exception as e:
            error_message = f"Error uploading video to S3: {str(e)}"
            print(error_message)
            logging.error(error_message)
            return None

    def update_upload_status(self, unique_id, status):
        cursor = self.db_conn.cursor()
        try:
            cursor.execute(
                "UPDATE rhenus_events SET upload_to_dynamo = %s WHERE unique_id = %s",
                (status, unique_id),
            )
            self.db_conn.commit()
        except Exception as e:
            error_message = f"Error updating upload_to_dynamo status: {str(e)}"
            logging.error(error_message)
        finally:
            cursor.close()

    def update_video_upload_status(self, unique_id, status):
        cursor = self.db_conn.cursor()
        try:
            cursor.execute(
                "UPDATE rhenus_events SET video_uploaded_to_s3 = %s WHERE unique_id = %s",
                (status, unique_id),
            )
            self.db_conn.commit()
        except Exception as e:
            error_message = f"Error updating video_uploaded_to_s3 status: {str(e)}"
            logging.error(error_message)
        finally:
            cursor.close()

    def upload_to_dynamodb(self, vehicle_data):
        try:
            print(vehicle_data)
            s3_url = "https://rhenus-truck-images.s3.ap-south-1.amazonaws.com"
            full_path = vehicle_data['filename']
            filename = os.path.basename(full_path)
            vehicle_number = vehicle_data['vehicle_number']
            vehicle_number = vehicle_number.upper() if vehicle_number else "Not Detected"

            # Upload video to S3 if video_path exists
            video_s3_uri = None
            if 'video_path' in vehicle_data and vehicle_data['video_path']:
                video_s3_uri = self.upload_video_to_s3(vehicle_data['video_path'])

            # Prepare DynamoDB item
            dynamo_item = {
                'vechicle_number_type': vehicle_data['event_source'],
                'timestamp': vehicle_data['timestamp'],
                'active': vehicle_data['active'],
                'entry_image_url': f'{s3_url}/{filename}',
                'vehicle_number': vehicle_number,
                'vehicle_type': vehicle_data['vehicle_type'],
            }
            
            # Add video S3 URL if available
            if video_s3_uri:
                dynamo_item['videopath'] = video_s3_uri
                self.update_video_upload_status(vehicle_data['unique_id'], True)
            else:
                self.update_video_upload_status(vehicle_data['unique_id'], False)

            response = self.table.put_item(Item=dynamo_item)
            print(f"Data uploaded to DynamoDB: {response}")
            self.update_upload_status(vehicle_data['unique_id'], True)   
        except (NoCredentialsError, ClientError) as e:
            error_message = f"Error uploading to DynamoDB: {str(e)}"
            print(error_message)
            logging.error(error_message)
            self.update_upload_status(vehicle_data['unique_id'], False)   
        except Exception as e:
            error_message = f"General error: {str(e)}"
            logging.error(error_message)
            self.update_upload_status(vehicle_data['unique_id'], False)

    def fetch_video_path(self, unique_id):
        cursor = self.db_conn.cursor()
        try:
            cursor.execute("SELECT video_path FROM rhenus_events WHERE unique_id = %s", (unique_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            cursor.close()

# Retry failed uploads
def retry_failed_uploads(conn, dynamo_uploader):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM rhenus_events WHERE upload_to_dynamo = FALSE")
        rows = cursor.fetchall()
        for row in rows:
            data = {
                "event_source": row[2],
                "timestamp": row[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "active": row[3],
                "filename": row[4],
                "vehicle_number": row[1],
                "vehicle_type": row[5],
                "unique_id": row[7],
                "video_path": row[12] if len(row) > 8 else None,  # Assuming video_path is the 9th column
            }
            dynamo_uploader.upload_to_dynamodb(data)
    except Exception as e:
        error_message = f"Error in retry logic: {str(e)}"
        logging.error(error_message)
    finally:
        cursor.close()

# Retry failed video uploads
def retry_failed_video_uploads(conn, dynamo_uploader):
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM rhenus_events WHERE video_path IS NOT NULL AND video_uploaded_to_s3 = FALSE"
        )
        rows = cursor.fetchall()
        for row in rows:
            data = {
                "event_source": row[2],
                "timestamp": row[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "active": row[3],
                "filename": row[4],
                "vehicle_number": row[1],
                "vehicle_type": row[5],
                "unique_id": row[7],
                "video_path": row[12],
            }
            dynamo_uploader.upload_to_dynamodb(data)
    except Exception as e:
        error_message = f"Error in video retry logic: {str(e)}"
        logging.error(error_message)
    finally:
        cursor.close()

# PostgreSQL listener
def listen_to_postgres_and_upload():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="rhenus",
            user="postgres",
            password="rhenus",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        cursor.execute("LISTEN watchdog_channel;")
        print("Listening to PostgreSQL notifications...")

        dynamo_uploader = DynamoDBUploader('rhenus_vehicle_number', conn)

        while True:
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                data = json.loads(notify.payload)
                print(f"Received notification: {data}")

                if isinstance(data['timestamp'], str):
                    data['timestamp'] = data['timestamp'].replace('+05:30', 'Z')
                # Always fetch the latest video_path from DB
                data['video_path'] = dynamo_uploader.fetch_video_path(data['unique_id'])
                dynamo_uploader.upload_to_dynamodb(data)

            
            retry_failed_uploads(conn, dynamo_uploader)
            retry_failed_video_uploads(conn, dynamo_uploader)
    except Exception as e:
        error_message = f"Error in PostgreSQL listener: {str(e)}"
        print(error_message)
        logging.error(error_message)

if __name__ == "__main__":
    try:
        listen_to_postgres_and_upload()
    except KeyboardInterrupt:
        print("Process interrupted, shutting down...")
