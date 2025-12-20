
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import time

# Function to safely get the max value
def safe_max(x):
    try:
        return x.max() if not x.isnull().all() else None  # Return None if all values are NaN
    except Exception as e:
        print(f"Error in max aggregation: {e}")
        return None

# Function to safely get the mode value
def safe_mode(x):
    try:
        return x.mode()[0] if not x.mode().empty else None  # Return None if mode is empty
    except Exception as e:
        print(f"Error in mode aggregation: {e}")
        return None

# Function to process and insert the data for a given table
def process_dock_data_for_table(cur, dock_table, time_bucket_table):
    # Define the query to fetch the data for the last 30 seconds
    query = f"""
    SELECT timestamp, dock_status, person_count, reach_truck, material, bopt
    FROM {dock_table}
    WHERE timestamp > %s
    """

    # Define the time range (last 30 seconds)
    thirty_seconds_ago = datetime.now() - timedelta(seconds=30)
    cur.execute(query, (thirty_seconds_ago,))

    # Fetch the result into a DataFrame
    data = cur.fetchall()
    columns = ["timestamp", "dock_status", "person_count", "reach_truck", "material", "bopt"]
    df = pd.DataFrame(data, columns=columns)

    # Ensure the timestamp column is of datetime type
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Bucket the data into 30-second intervals
    df['timestamp_bucket'] = df['timestamp'].dt.floor('30S')

    # Apply the aggregation functions (using safe functions)
    bucketed_df = df.groupby('timestamp_bucket').agg(
        dock_status=('dock_status', safe_max),  # Use safe_max for dock_status
        person_count=('person_count', safe_mode),  # Use safe_mode for person_count
        reach_truck=('reach_truck', safe_max),  # Use safe_mode for reach_truck
        material=('material', safe_mode),  # Use safe_mode for material
        bopt=('bopt', safe_max)  # Use safe_mode for bopt
    ).reset_index()

    # Connect again to insert the result into the time_bucket_dock table
    insert_query = f"""
    INSERT INTO {time_bucket_table} (timestamp, dock_status, person_count, reach_truck, material, bopt)
    SELECT %s, %s, %s, %s, %s, %s
    WHERE NOT EXISTS (
        SELECT 1 FROM {time_bucket_table} WHERE timestamp = %s
    )
    """

    # Loop through each row in the bucketed DataFrame and insert if not already in the table
    for _, row in bucketed_df.iterrows():
        cur.execute(insert_query, (
            row['timestamp_bucket'],
            row['dock_status'],
            row['person_count'],
            row['reach_truck'],
            row['material'],
            row['bopt'],
            row['timestamp_bucket']
        ))

    print(f"Data for {dock_table} processed and inserted into {time_bucket_table} successfully!")

# Main loop to run the process for all dock tables every minute
def run_process():
    # Connect to PostgreSQL (keeping the connection open for multiple iterations)
    conn = psycopg2.connect(
        dbname="rhenus",
        user="postgres",
        password="rhenus",
        host="localhost",
        port="5432"
    )
    
    # Create a cursor object to interact with the database
    cur = conn.cursor()

    # Process all tables in a single transaction
    for i in range(1, 21):
        dock_table = f'dock{i}'
        time_bucket_table = f'time_bucket_dock{i}'
        process_dock_data_for_table(cur, dock_table, time_bucket_table)  # Process each table

    # Commit the changes after processing all tables
    conn.commit()
    print("All tables processed and committed successfully!")

    # Sleep for 30 seconds before the next run
    time.sleep(30)

# Loop to keep the program running every 30 seconds
while True:
    run_process()  # Run the process for all tables
