import psycopg2
from psycopg2.extras import RealDictCursor
import time
import datetime
from datetime import datetime
import boto3, json
# Get current date
current_data = datetime.now().date()
#current_data = '16-03-2025'

DYNAMODB_TABLE = 'rhenus_dock_cycle'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)


def upload_to_s3(timestamp, local_file, dock):
    s3_file = str(datetime.now().date()) + "/" + dock + "/" + str(timestamp) + '.jpg'
    s3_file = s3_file.replace(' ', '')
    bucket = 'rhenus-truck-images'

    s3 = boto3.client('s3')
    try:
        s3.upload_file(local_file, bucket, s3_file)
        print("Upload Successful")
        return 'https://rhenus-truck-images.s3.ap-south-1.amazonaws.com/' + s3_file
    except FileNotFoundError:
        print("The file was not found")
        return False

 


def insert_into_dynamodb(record_data, cursor, conn):
    try:
        dock_no = record_data.get('dock')
        # Remove timezone offset and ensure T format
        dock_in_time = record_data.get('arrival', 'N/A').split('+')[0].replace(' ', 'T')
        dock_out_time = record_data.get('departure', 'N/A').split('+')[0].replace(' ', 'T')
        dock_in = dock_in_time.replace('T', ' ')  # Keep space for DB query
        
        # Query for the image
        """
        cursor.execute(f"SELECT timestamp, image FROM dock_images WHERE timestamp >= '{dock_in}' AND dock='{dock_no}' ORDER BY timestamp FETCH FIRST ROW ONLY")
        result = cursor.fetchone()
        
        # Check if an image was found
        if result is None:
            print(f"No image found for dock {dock_no} at time {dock_in}")
            dock_in_image = None
        else:
            image = result[1]
            dock_in_image = upload_to_s3(dock_in, image, dock_no)
        """
        # Create item with all required fields
        item = {
            'dock': "dock#data",
            'timestamp': record_data['timestamp'].split('+')[0].replace(' ', 'T'),
            'dock_no': str(dock_no),
            'dock_in_time': dock_in_time,
            'dock_out_time': dock_out_time
        }

        table.put_item(Item=item)
        print(f"Inserted into DynamoDB: {item}")
        # cursor.execute(f"UPDATE dock_cycle SET upload_to_dynamo_arrival = TRUE WHERE arrival = '{arrival}' AND dock = '{dock_no}'")
        # conn.commit()
    except Exception as e:
        print(f"Error inserting into DynamoDB for record_data: {record_data}: {e}")

def update_dynamodb(record_data, cursor, conn):
    try:
        dock_no = record_data.get('dock')
        # Remove timezone offset and ensure T format
        dock_out_time = record_data.get('departure', 'N/A').split('+')[0].replace(' ', 'T')
        arrival_time = record_data.get('arrival', 'N/A').split('+')[0].replace(' ', 'T')
        dock_out = dock_out_time.replace('T', ' ')  # Keep space for DB query
        
        """
        cursor.execute(f"SELECT timestamp, image FROM dock_images WHERE timestamp <= '{dock_out}' AND dock='{dock_no}' ORDER BY timestamp DESC FETCH FIRST ROW ONLY")
        result = cursor.fetchone()
        
        if result is None:
            print(f"No image found for dock {dock_no} at time {dock_out}")
            dock_out_image = None
        else:
            image = result[1]
            dock_out_image = upload_to_s3(dock_out, image, dock_no)
        """
        if dock_out_time != 'N/A':
            update_expression = "SET dock_out_time = :dock_out_time"
            expression_values = {':dock_out_time': dock_out_time}
            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(record_data['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            print(f"Updated in DynamoDB: {record_data}")
            # cursor.execute(f"UPDATE dock_cycle SET upload_to_dynamo_departure = TRUE WHERE arrival = '{arrival_time}' AND dock = '{dock_no}'")
            # conn.commit()

    except Exception as e:
        print(f"Error updating DynamoDB for record : {e}")




# Database connection settings
db_config = {
    "dbname": "rhenus",
    "user": "postgres",
    "password": "rhenus",
    "host": "localhost",
}

states = []
trucks = [] 
conn = psycopg2.connect(**db_config)
cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# Modified query to handle multiple docks

base_query = """ 
WITH lead_dock_status AS (
    SELECT 
        timestamp,
        dock_status,
        lead(dock_status, 1) OVER (ORDER BY timestamp) AS next_dock_status,
        lead(timestamp, 1) OVER (ORDER BY timestamp) AS next_timestamp
    FROM time_bucket_dock{}
    WHERE timestamp > '{}'
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

"""


arrival_time = None
while True:
    # retry_failed_uploads(cursor, conn)
    time.sleep(10)
    
    last_cycle_query = "SELECT * FROM dock_cycle WHERE dock='dock{}' ORDER BY timestamp DESC FETCH FIRST ROW ONLY"
    for dock_no in range(1, 21):

        cursor.execute(last_cycle_query.format(dock_no))
        last_dock_cycle = cursor.fetchone()
    
        if last_dock_cycle is None:
            last_dock_cycle_status = -1
            cursor.execute(base_query.format(dock_no, current_data))
            arrival_time = None
            

        else:
            if last_dock_cycle['status'] == 'incomplete':
                last_dock_cycle_status = 1
                arrival_time = last_dock_cycle['arrival']
                #print(f"Last Arrival Time for dock{dock_no}: {last_dock_cycle['arrival']}")
            else:
                last_dock_cycle_status = -1
                arrival_time = None
            cursor.execute(base_query.format(dock_no, last_dock_cycle['arrival']))


        dock_data = cursor.fetchall()
        
            

        for data in dock_data:
            if data['state_change'] == 1 and last_dock_cycle_status == -1:
                print("########################################################")
                
                # Use current timestamp for arrival (latest timestamp before state change)
                arrival_time = str(data['next_timestamp']).split('+')[0].replace(' ', 'T')
                upload_timestamp = str(datetime.now()).split('.')[0].replace(' ', 'T')
                
                insert_into_dynamodb({
                    'arrival': arrival_time,
                    'dock': f'dock{dock_no}',
                    'timestamp': upload_timestamp
                }, cursor, conn)
                
                cursor.execute(f"""
                    INSERT INTO dock_cycle (timestamp, arrival, status, dock) 
                    VALUES ('{upload_timestamp}', '{arrival_time}', 'incomplete', 'dock{dock_no}')
                """)
                conn.commit()
                
                print(f"Dock_no: dock{dock_no}, Arrival: {arrival_time}")
                last_dock_cycle_status = 1
                time.sleep(1)
            
            elif data['state_change'] == -1 and last_dock_cycle_status == 1:
                # Use next timestamp for departure (timestamp after state change)
                departure_time = str(data['next_timestamp']).split('+')[0].replace(' ', 'T')
                
                cursor.execute(f"""
                    UPDATE dock_cycle
                    SET departure='{departure_time}', status='complete' 
                    WHERE arrival='{arrival_time}' AND dock='dock{dock_no}' 
                    RETURNING *
                """)
                updated_row_timestamp = cursor.fetchone()['timestamp']
                
                arrival_time_formatted = str(arrival_time).split('+')[0].replace(' ', 'T')
                print(f"Dock_no: dock{dock_no}, Departure: {departure_time}")
                
                update_dynamodb({
                    'timestamp': updated_row_timestamp,
                    'arrival': arrival_time_formatted,
                    'departure': departure_time,
                    'dock': f'dock{dock_no}'
                }, cursor, conn)
                
                last_dock_cycle_status = -1
                conn.commit()
                print("*****************************************************")
                time.sleep(1)
