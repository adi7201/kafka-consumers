import psycopg2
import boto3
import json
import pytz
from datetime import datetime
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from botocore.exceptions import NoCredentialsError, ClientError

# DynamoDB uploader class
class DynamoDBUploader:
    def __init__(self, table_name):
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.table_name)

    def upload_to_dynamodb(self, vehicle_data):
        try:
            if 'number' in vehicle_data.keys():
                response = self.table.put_item(
                    Item={
                    'vechicle_number_type': 'tab',
                    'timestamp': vehicle_data['timestamp'],  
                    'vehicle_number': vehicle_data['number'].upper(), 
                    }
                )
                print(f"Data uploaded to DynamoDB: {response}")
        except NoCredentialsError:
            print("Credentials not available for DynamoDB")
        except ClientError as e:
            print(f"Error uploading to DynamoDB: {e.response['Error']['Message']}")

# PostgreSQL listener that listens for data insertions and triggers DynamoDB uploads
def listen_to_postgres_and_upload():
    conn = psycopg2.connect(
        host="localhost",  
        database="rhenus",   
        user="postgres",   
        password="rhenus",  
    )
    
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute("LISTEN dynamodb_channel;")
    print("Listening to PostgreSQL notifications...")

    dynamo_uploader = DynamoDBUploader('rhenus_vehicle_number')

    while True:
        conn.poll()  # Poll the PostgreSQL connection for new notifications
        while conn.notifies:
            notify = conn.notifies.pop(0)
            data = json.loads(notify.payload)
            print(f"Received notification: {data}")

            
            kolkata_tz = pytz.timezone("Asia/Kolkata")
            kolkata_time = datetime.now(kolkata_tz)

            # Format the timestamp as required
            data["timestamp"] = kolkata_time.strftime("%Y-%m-%dT%H:%M:%SZ")

           
            dynamo_uploader.upload_to_dynamodb(data)

if __name__ == "__main__":
    try:
        listen_to_postgres_and_upload()
    except KeyboardInterrupt:
        print("Process interrupted, shutting down...")
