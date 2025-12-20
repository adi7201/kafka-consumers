import psycopg2
import json
from datetime import datetime, date
import os
import time

# Database connection parameters
db_params = {
    'database': 'rhenus',
    'user': 'postgres',
    'password': 'rhenus',
    'host': 'localhost'
}


video_folder = '/home/ai4m/data/smart-record-gate'

def format_timestamp_to_pattern(ts_str):
    """
    Convert ISO format timestamp like '2025-07-30T10:16:43.800'
    into video filename pattern like '20250730-101643'.
    """
    ts_trimmed = ts_str.split('.')[0]  # Remove fractional seconds if present
    dt = datetime.strptime(ts_trimmed, '%Y-%m-%dT%H:%M:%S')
    return dt.strftime('%Y%m%d-%H%M%S')

def find_video_for_pattern(pattern):
    """
    Search for a video filename containing the pattern in the video folder.
    Returns full path if found, else None.
    """
    try:
        for filename in os.listdir(video_folder):
            if pattern in filename and filename.endswith('.mp4'):
                return os.path.join(video_folder, filename)
    except FileNotFoundError:
        print(f"Video folder {video_folder} not found.")
    return None

def main():
    while True:
        try:
            connection = psycopg2.connect(**db_params)
            cursor = connection.cursor()
            print("Database connected successfully.")

            today_str = date.today().strftime('%Y-%m-%d')

            # Fetch only gate_in trucks whose video_path IS NULL or empty
            cursor.execute("""
                SELECT unique_id, event_json
                FROM rhenus_events
                WHERE timestamp::date = %s
                  AND gate_id = %s
                  AND vehicle_type = %s
                  AND (video_path IS NULL OR video_path = '')
            """, (today_str, 'gate_in', 'Truck'))

            rows = cursor.fetchall()
            print(f"Fetched {len(rows)} rows for date {today_str} with gate_id='gate_in', vehicle_type='Truck' and empty video_path.")

            for unique_id, event_json_val in rows:
                try:
                    if isinstance(event_json_val, dict):
                        event_json = event_json_val
                    else:
                        event_json = json.loads(event_json_val)

                    ts = event_json.get("@timestamp")
                    if not ts:
                        print(f"[unique_id {unique_id}] No '@timestamp' found in event_json.")
                        continue

                    ts = ts.rstrip('Z')
                    pattern = format_timestamp_to_pattern(ts)
                    video_path = find_video_for_pattern(pattern)

                    if video_path:
                        cursor.execute("""
                            UPDATE rhenus_events
                            SET video_path = %s
                            WHERE unique_id = %s
                        """, (video_path, unique_id))
                        print(f"[unique_id {unique_id}] Updated video_path to: {video_path}")
                    else:
                        print(f"[unique_id {unique_id}] No matching video found for pattern: {pattern}")

                except json.JSONDecodeError:
                    print(f"[unique_id {unique_id}] Error decoding JSON in event_json.")
                except Exception as ex:
                    print(f"[unique_id {unique_id}] Unexpected error: {ex}")

            connection.commit()
            cursor.close()
            connection.close()
            print("Database connection closed. Sleeping for 5 seconds...\n")

        except Exception as e:
            print("Database connection or query failed:", e)

        # Wait 60 seconds before next poll
        time.sleep(5)

if __name__ == "__main__":
    main()
