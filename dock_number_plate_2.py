import time
import psycopg2
from datetime import timedelta
import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Attr


# PostgreSQL connection setup
db_params = {
    'database': 'rhenus',
    'user': 'postgres',
    'password': 'rhenus',
    'host': 'localhost'
}
connection = psycopg2.connect(**db_params)
cursor = connection.cursor()

dynamodb = boto3.resource('dynamodb', region_name='ap-south-1') 
dynamo_table = dynamodb.Table('rhenus_dock_cycle_testing') 

def update_number_plate_in_cycle():
    while True:
        try:
            cursor.execute("""
                SELECT dock, timestamp, arrival, departure
                FROM dock_cycle_testing
                WHERE number_plate IS NULL
                AND arrival IS NOT NULL
                AND departure IS NOT NULL
            """)
            dock_cycles = cursor.fetchall()

            for dock, ts, arrival, departure in dock_cycles:
                arrival_with_buffer = arrival - timedelta(minutes=1)

                cursor.execute("""
                    SELECT number_plate, text_conf, timestamp
                    FROM dock_number_plate
                    WHERE dock = %s
                    AND timestamp BETWEEN %s AND %s
                    AND text_conf > 0.9
                    ORDER BY timestamp ASC
                    LIMIT 1
                """, (dock, arrival_with_buffer, departure))
                plate_result = cursor.fetchone()

                if plate_result:
                    number_plate, text_conf, plate_ts = plate_result

                    cursor.execute("""
                        UPDATE dock_cycle_testing
                        SET number_plate = %s
                        WHERE dock = %s AND timestamp = %s
                    """, (number_plate, dock, ts))
                    connection.commit()
                    print(f"[UPDATED] PostgreSQL: {dock}, {ts} → {number_plate}")

                    

                    try:
                        dock_key = "dock#data"
                        ts_key = ts.strftime('%Y-%m-%dT%H:%M:%S')
                        in_time = arrival.strftime('%Y-%m-%dT%H:%M:%S')
                        out_time = departure.strftime('%Y-%m-%dT%H:%M:%S')

                        print("Updating:", dock_key, ts_key, in_time, out_time)

                        dynamo_table.update_item(
                            Key={
                                'dock': dock_key,
                                'timestamp': ts_key
                            },
                            UpdateExpression="SET vehicle_number = :np",
                            ConditionExpression=Attr('dock_in_time').eq(in_time) & Attr('dock_out_time').eq(out_time) & Attr('dock_no').eq(dock), 
                            ExpressionAttributeValues={
                                ':np': number_plate
                            }
                        )
                        print(f"[DYNAMO ✅] Updated: {dock_key} @ {ts_key} → {number_plate}")
                    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                        print(f"[DYNAMO ⚠️] Skipped update — dock_in_time or dock_out_time mismatch")
                    except Exception as e:
                        print(f"[DYNAMO ❌] Error: {e}")
            
        except Exception as e:
            print("Update error:", e)
            connection.rollback()

        time.sleep(3)

update_number_plate_in_cycle()
