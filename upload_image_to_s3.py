import psycopg2
from psycopg2.extras import RealDictCursor
import time
import datetime
from datetime import datetime
import boto3, json
from botocore.exceptions import EndpointConnectionError  # Import the exception
# Get current date
current_data = datetime.now().date()
#current_data = '03-02-2025'

db_config = {
    "dbname": "rhenus",
    "user": "postgres",
    "password": "rhenus",
    "host": "localhost",
}
DYNAMODB_TABLE = 'rhenus_dock_cycle'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)


def upload_to_s3(timestamp, local_file, dock):
    s3_file = f"{datetime.now().date()}/{dock}/{timestamp}.jpg"
    s3_file = s3_file.replace(' ', '')
    bucket = 'rhenus-truck-images'
    s3 = boto3.client('s3')
    try:
        s3.upload_file(local_file, bucket, s3_file)
        print("Upload Successful")
        return f"https://rhenus-truck-images.s3.ap-south-1.amazonaws.com/{s3_file}"
    except FileNotFoundError:
        print("The file was not found:", local_file)
        return False
    except Exception as e:
        print("An unexpected error occurred while uploading to S3:", e)
        return False

conn = psycopg2.connect(**db_config)
cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

while True:
    cursor.execute("SELECT * FROM dock_cycle WHERE arrival > CURRENT_DATE ORDER BY arrival")
    dock_cycle = cursor.fetchall()
    for cycle in dock_cycle:
        if not cycle['arrival_image'] and cycle['arrival']:
            cursor.execute(f"SELECT image, timestamp from dock_images WHERE timestamp > '{cycle['arrival']}' AND dock='{cycle['dock']}' ORDER BY timestamp limit 1")
            arrival_image = cursor.fetchone()
            if not arrival_image:
                time.sleep(10)
                continue
            arrival_image = arrival_image['image']
            image = upload_to_s3(cycle['arrival'], arrival_image, cycle['dock'])
            update_expression = "SET dock_in_image = :dock_in_image"
            expression_values = {':dock_in_image': image}

            # if dock_out_image:
            #     update_expression += ", dock_out_image = :dock_out_image"
            #     expression_values[':dock_out_image'] = dock_out_image

            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(cycle['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            cursor.execute(f"UPDATE dock_cycle set arrival_image=True WHERE arrival='{cycle['arrival']}' AND dock='{cycle['dock']}'")
            conn.commit()
            print(arrival_image)
        if not cycle['departure_image'] and cycle['departure']:
            cursor.execute(f"SELECT image, timestamp from dock_images WHERE timestamp <= '{cycle['departure']}' AND dock='{cycle['dock']}' ORDER BY timestamp DESC limit 1")
            departure_image = cursor.fetchone()
            if not departure_image:
                continue
            departure_image = departure_image['image']
            image = upload_to_s3(cycle['departure'], departure_image, cycle['dock'])
            print(image)
            update_expression = "SET dock_out_image = :dock_out_image"
            expression_values = {':dock_out_image': image}

            # if dock_out_image:
            #     update_expression += ", dock_out_image = :dock_out_image"
            #     expression_values[':dock_out_image'] = dock_out_image

            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(cycle['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            cursor.execute(f"UPDATE dock_cycle set departure_image=True WHERE arrival='{cycle['arrival']}' AND dock='{cycle['dock']}'")
            conn.commit()
            print(departure_image)
        if not cycle['transaction_start_image'] and cycle['transaction_start_time']:
            cursor.execute(f"SELECT image, timestamp from dock_images WHERE timestamp >= '{cycle['transaction_start_time']}' AND dock='{cycle['dock']}' ORDER BY timestamp limit 1")
            transaction_start_image = cursor.fetchone()
            if not transaction_start_image:
                continue
            transaction_start_image = transaction_start_image['image']
            image = upload_to_s3(cycle['transaction_start_time'], transaction_start_image, cycle['dock'])
            print(image)
            update_expression = "SET transaction_start_image = :transaction_start_image"
            expression_values = {':transaction_start_image': image}

            # if dock_out_image:
            #     update_expression += ", dock_out_image = :dock_out_image"
            #     expression_values[':dock_out_image'] = dock_out_image

            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(cycle['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            cursor.execute(f"UPDATE dock_cycle set transaction_start_image=True WHERE arrival='{cycle['arrival']}' AND dock='{cycle['dock']}'")
            conn.commit()
            print(transaction_start_image)
        if not cycle['transaction_end_image'] and cycle['transaction_end_time']:
            cursor.execute(f"SELECT image, timestamp from dock_images WHERE timestamp <= '{cycle['transaction_end_time']}' AND dock='{cycle['dock']}' ORDER BY timestamp DESC limit 1")
            transaction_end_image = cursor.fetchone()
            if not transaction_end_image:
                continue
            transaction_end_image =  transaction_end_image['image']
            image = upload_to_s3(cycle['transaction_end_time'], transaction_end_image, cycle['dock'])
            print(image)
            update_expression = "SET transaction_end_image = :transaction_end_image"
            expression_values = {':transaction_end_image': image}

            # if dock_out_image:
            #     update_expression += ", dock_out_image = :dock_out_image"
            #     expression_values[':dock_out_image'] = dock_out_image

            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(cycle['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            cursor.execute(f"UPDATE dock_cycle set transaction_end_image=True WHERE arrival='{cycle['arrival']}' AND dock='{cycle['dock']}'")
            conn.commit()
            print(transaction_end_image)

