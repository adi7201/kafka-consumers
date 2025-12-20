import psycopg2
import pytz
import time
import json
from datetime import datetime

DB_PARAMS = {
    'database': 'rhenus',
    'user': 'postgres',
    'password': 'ai4m2024',
    'host': 'localhost'
}

TIMEZONE = pytz.timezone('Asia/Kolkata')


def connect_to_database():
    try:
        connection = psycopg2.connect(**DB_PARAMS)
        print("Database connected successfully")
        return connection
    except Exception as error:
        print('Database connection failed:', error)
        return None


# Fetch the last processed timestamp for a specific dock
def fetch_last_processed_timestamp(cursor, dock_no):
    query = """
    SELECT MAX(timestamp)
    FROM dock_status
    WHERE dock->>'dock_in' IS NOT NULL AND dock_no = %s;
    """
    cursor.execute(query, (dock_no,))
    result = cursor.fetchone()
    return result[0] if result and result[0] else datetime.now(TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)

def fetch_events(cursor, dock_table, last_timestamp):
    query = f"""
    SELECT 
        time_bucket('5 seconds', timestamp) AS bucket,
        mode() WITHIN GROUP (ORDER BY dock_status) AS status
    FROM 
        {dock_table}
    WHERE 
        timestamp > %s
    GROUP BY 
        bucket
    ORDER BY 
        bucket ASC;
    """
    cursor.execute(query, (last_timestamp,))
    return cursor.fetchall()

def insert_dock_status(cursor, dock_no, dock_data, event):
    query = """
    SELECT 1 FROM dock_status WHERE dock_no = %s AND timestamp = %s;
    """
    cursor.execute(query, (dock_no, dock_data["dock_in"]))
    if not cursor.fetchone():
        query = """
        INSERT INTO dock_status (dock_no, timestamp, dock, event)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (dock_no, dock_data["dock_in"], json.dumps(dock_data), event))

def update_dock_status(cursor, dock_no, dock_data,event):
    query = """
    UPDATE dock_status
    SET dock = jsonb_set(dock, '{dock_out}', %s)
    WHERE dock_no = %s AND dock->>'dock_in' = %s AND dock->>'dock_out' IS NULL;
    """
    cursor.execute(query, (json.dumps(dock_data["dock_out"]), dock_no, dock_data["dock_in"]))

def process_events(cursor, connection, dock_no, dock_table, last_timestamp, dock_state):
    events = fetch_events(cursor, dock_table, last_timestamp)
    for timestamp, status in events:
        if status == 2 and dock_state[dock_no] is None:  # Entry event
            dock_data = {"dock_in": timestamp.isoformat(), "dock_out": None}
            insert_dock_status(cursor, dock_no, dock_data, "entry")
            dock_state[dock_no] = dock_data["dock_in"]

        elif status == 0 and dock_state[dock_no]:  # Exit event
            dock_data = {"dock_in": dock_state[dock_no], "dock_out": timestamp.isoformat()}
            update_dock_status(cursor, dock_no, dock_data,"exit")
            dock_state[dock_no] = None

    connection.commit()


def main():
    dock_numbers = [1, 2, 3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]  # List of dock numbers
    dock_state = {f"dock{dock}": None for dock in dock_numbers}

    connection = connect_to_database()
    if not connection:
        print("Failed to connect to the database. Exiting.")
        return

    cursor = connection.cursor()
    try:
        while True:
            for dock_number in dock_numbers:
                dock_no = f"dock{dock_number}"
                dock_table = f"dock{dock_number}"

                last_timestamp = fetch_last_processed_timestamp(cursor, dock_no)
                print(f"Processing {dock_no} from {last_timestamp}...")

                process_events(cursor, connection, dock_no, dock_table, last_timestamp, dock_state)

            time.sleep(10)
    except KeyboardInterrupt:
        print("\nExiting the program.")
    finally:
        cursor.close()
        connection.close()
        print("Database connection closed.")


if __name__ == "__main__":
    main()
