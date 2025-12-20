import time
from kafka import KafkaConsumer, KafkaProducer
import json
import psycopg2
from datetime import datetime
import pytz
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


consumer = KafkaConsumer(
    bootstrap_servers='localhost:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest'
)
consumer.subscribe(['dstest'])


producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


db_params = {
    'database': 'rhenus',
    'user': 'postgres',
    'password': 'rhenus',
    'host': 'localhost'
}

try:
    connection = psycopg2.connect(**db_params)
    cursor = connection.cursor()
    logging.info(" Database connected successfully")
except Exception as error:
    logging.error(f"Database connection failed: {error}")
    exit(1)


all_possible_classes = [
    'truck_present', 'person', 'material', 'shutter_down',
    'bopt', 'reach_truck', 'empty_dock'
]


def send_recording_command(data):
    """Send recording command to Kafka topic 'record'."""
    try:
        producer.send('record', value=data)
        producer.flush()
        logging.info(f" ⚠️ Recording command sent: {data}")
    except Exception as e:
        logging.error(f"❌ Failed to send recording command: {e}")


for msg in consumer:
    object_counters = {key: 0 for key in all_possible_classes}
    message = msg.value
    #print(f" Received message: {message}")

    # Parse timestamp to IST
    raw_timestamp = message['@timestamp']
    utc_time = datetime.strptime(raw_timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    ist_time = utc_time.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata'))

    # Count objects
    for data in message['objects']:
        obj_data = data.split('|')[6]
        if obj_data in object_counters:
            object_counters[obj_data] += 1

    # Detect linecross events
    events = []
    linecross_data = message.get('linecross', {})

    if str(linecross_data.get('entry', 0)) == '1':
        events.append('entry')
    if str(linecross_data.get('exit', 0)) == '1':
        events.append('exit')

    event = ', '.join(events)

    # If entry or exit, trigger recording
    if event:
        duration = 137
        recording_data = {
            "command": "start-recording",
            "start": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "stop": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "sensor": {"id": message["sensorId"]},
        }
        #send_recording_command(recording_data)

    # Dock status
    if object_counters['truck_present'] > 0:
        dock_status = 2
    elif object_counters['shutter_down'] > 0:
        dock_status = 1
    elif object_counters['empty_dock'] > 0:
        dock_status = 3
    else:
        dock_status = 0

    # Object counts
    person_count = object_counters['person']
    reach_truck = object_counters['reach_truck']
    material = object_counters['material']
    bopt = object_counters['bopt']

    # Validate sensor_id
    sensor_id = message['sensorId']
    if sensor_id not in [f'dock{i}' for i in range(1, 21)]:
        logging.warning(f"⚠️ Invalid sensorId: {sensor_id}")
        continue

    # Convert objects list to JSON for DB
    objects_json = json.dumps(message.get('objects', []))

    # Insert into DB
    insert_query = f"""
        INSERT INTO {sensor_id} 
        (timestamp, dock_status, person_count, reach_truck, material, event, bopt, objects) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """

    try:
        execution_start_time = time.time()
        cursor.execute(insert_query, (
            ist_time, dock_status, person_count,
            reach_truck, material, event, bopt, objects_json
        ))
        connection.commit()
        execution_end_time = time.time()
        print(f"Inserted into {sensor_id} event='{event}' in {execution_end_time - execution_start_time:.4f} sec")

    except Exception as error:
        logging.error(f"❌ Error inserting into DB: {error}")
        connection.rollback()

