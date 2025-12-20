import psycopg2
import time
import boto3
from datetime import datetime
from psycopg2.extras import RealDictCursor

# Database connection settings
db_config = {
    "dbname": "rhenus",
    "user": "postgres",
    "password": "rhenus",
    "host": "localhost",
}

DYNAMODB_TABLE = 'rhenus_dock_cycle'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)

def update_dynamodb(record_data):
    try:
        expression_values = {}
        if 'transaction_start_time' in record_data:
            update_expression = "SET transaction_start_time = :transaction_start_time"
            expression_values[':transaction_start_time'] = record_data['transaction_start_time']
        if 'transaction_end_time' in record_data:
            update_expression = "SET transaction_end_time = :transaction_end_time"
            expression_values[':transaction_end_time'] = record_data['transaction_end_time']

        if expression_values:
            table.update_item(
                Key={
                    'dock': "dock#data",
                    'timestamp': str(record_data['timestamp']).replace(' ', 'T')
                },
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            print(f"Updated in DynamoDB: {record_data}")

    except Exception as e:
        print(f"Error updating DynamoDB: {e}")

def process_dock_cycle(dock):
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:
        # Fetch cycles that need processing
        cursor.execute(
            """
            SELECT timestamp, arrival, departure, transaction_start_time, transaction_end_time
            FROM dock_cycle
            WHERE dock = %s 
            AND arrival > CURRENT_DATE
            AND (transaction_start_time IS NULL OR transaction_end_time IS NULL)
            ORDER BY arrival DESC
            """,
            (dock,)
        )

        cycles = cursor.fetchall()
        if not cycles:
            print(f"No dock cycle data found for {dock}")
            return

        table_name = f"time_bucket_{dock}"
        for cycle in cycles:
            print(f"[{dock}] Processing cycle: Arrival={cycle['arrival']}, Departure={cycle['departure']}")

            # Clear variables for each cycle
            transaction_start_time = None
            transaction_end_time = None

            # Process transaction start time if not set
            if not cycle['transaction_start_time']:
                # Define strict boundaries for this cycle
                lower_bound = cycle['arrival']
                upper_bound = cycle['departure'] if cycle['departure'] else datetime.now()
                
                # 1. First try with reach_truck/bopt within cycle boundaries
                cursor.execute(
                    f"""
                    SELECT timestamp FROM {table_name}
                    WHERE (reach_truck > 0 OR bopt > 0)
                    AND timestamp >= %s AND timestamp <= %s
                    ORDER BY timestamp ASC LIMIT 1
                    """,
                    (lower_bound, upper_bound)
                )
                start_time_result = cursor.fetchone()

                if start_time_result:
                    transaction_start_time = start_time_result['timestamp']
                    print(f"Found start time via reach_truck/bopt: {transaction_start_time}")
                elif cycle['departure']:  # Only check material if we have departure time
                    # 2. Fallback to material check WITHIN THE SAME CYCLE BOUNDARIES
                    cursor.execute(
                        f"""
                        SELECT timestamp FROM {table_name}
                        WHERE material > 0
                        AND timestamp >= %s AND timestamp <= %s
                        ORDER BY timestamp ASC LIMIT 1
                        """,
                        (lower_bound, upper_bound)  # Same boundaries as primary check
                    )
                    material_start_result = cursor.fetchone()
                    
                    if material_start_result:
                        transaction_start_time = material_start_result['timestamp']
                        print(f"Found start time via material: {transaction_start_time}")

                if transaction_start_time:
                    cursor.execute(
                        """
                        UPDATE dock_cycle
                        SET transaction_start_time = %s
                        WHERE dock = %s AND timestamp = %s
                        """,
                        (transaction_start_time, dock, cycle['timestamp'])
                    )
                    conn.commit()
                    record_data = {
                        'timestamp': str(cycle['timestamp']).replace(' ', 'T'),
                        'transaction_start_time': str(transaction_start_time).split('+')[0].replace(' ', 'T')
                    }
                    update_dynamodb(record_data)

            # Process transaction end time if departure exists and end time not set
            if cycle['departure'] and not cycle['transaction_end_time']:
                # Define strict boundaries for this cycle
                lower_bound = cycle['arrival']
                upper_bound = cycle['departure']
                
                # 1. First try with reach_truck/bopt within cycle boundaries
                cursor.execute(
                    f"""
                    SELECT timestamp FROM {table_name}
                    WHERE (reach_truck = 1 OR bopt = 1)
                    AND timestamp >= %s AND timestamp <= %s
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (lower_bound, upper_bound)
                )
                end_time_result = cursor.fetchone()

                if end_time_result:
                    transaction_end_time = end_time_result['timestamp']
                    print(f"Found end time via reach_truck/bopt: {transaction_end_time}")
                else:
                    # 2. Fallback to material check WITHIN THE SAME CYCLE BOUNDARIES
                    cursor.execute(
                        f"""
                            SELECT timestamp FROM {table_name}
                            WHERE material > 0
                            AND timestamp >= %s AND timestamp <= %s
                            ORDER BY timestamp DESC LIMIT 1
                            """,
                        (lower_bound, upper_bound)  # Same boundaries as primary check
                    )
                    material_end_result = cursor.fetchone()
                    
                    if material_end_result:
                        transaction_end_time = material_end_result['timestamp']
                        print(f"Found end time via material: {transaction_end_time}")

                if transaction_end_time:
                    cursor.execute(
                        """
                        UPDATE dock_cycle
                        SET transaction_end_time = %s
                        WHERE dock = %s AND timestamp = %s
                        """,
                        (transaction_end_time, dock, cycle['timestamp'])
                    )
                    conn.commit()
                    record_data = {
                        'timestamp': str(cycle['timestamp']).replace(' ', 'T'),
                        'transaction_end_time': str(transaction_end_time).split('+')[0].replace(' ', 'T')
                    }
                    update_dynamodb(record_data)

    except Exception as e:
        print(f"Error processing {dock}: {e}")
    finally:
        cursor.close()
        conn.close()
# Main loop
while True:
    for i in range(1, 21):
        dock_name = f"dock{i}"
        print(f"Processing {dock_name}")
        process_dock_cycle(dock_name)

    print("Waiting for next cycle...")
    time.sleep(10)
