import time
from kafka import KafkaConsumer
import json
import psycopg2
from datetime import datetime
import pytz
import cv2
import grpc
import numpy as np
from tritonclient import grpc as grpcclient
import re
import os
from pprint import pprint


# Kafka Setup
consumer = KafkaConsumer(
   'dstest',
   bootstrap_servers='localhost:9092',
   value_deserializer=lambda m: json.loads(m.decode('utf-8')),
   auto_offset_reset='latest'
)


# PostgreSQL Setup
db_params = {
   'database': 'rhenus',
   'user': 'postgres',
   'password': 'rhenus',
   'host': 'localhost'
}
connection = psycopg2.connect(**db_params)
cursor = connection.cursor()


# Directory to save blacked cropped images
BLACKED_CROP_BASE_DIR = "./blacked_cropped_images"
os.makedirs(BLACKED_CROP_BASE_DIR, exist_ok=True)


def get_centroid(poly):
   x_coords = poly[::2]
   y_coords = poly[1::2]
   centroid_x = sum(x_coords) / 4
   centroid_y = sum(y_coords) / 4
   return centroid_x, centroid_y


def send_to_triton(frame):
   try:
       client = grpcclient.InferenceServerClient(url="localhost:8001")
       input_tensor = grpcclient.InferInput("INPUT_DATA", frame.shape, "UINT8")
       input_tensor.set_data_from_numpy(frame)
       output = grpcclient.InferRequestedOutput("OUTPUT_TEXT_AND_BOX")
       result = client.infer("nvOCDR", [input_tensor], outputs=[output])
       output_data = result.as_numpy("OUTPUT_TEXT_AND_BOX")
       decoded = [json.loads(x[0].decode()) for x in output_data]
       return decoded[0]
   except Exception as e:
       print("Triton error:", e)
       return []


def format_number_plate(text):
   clean = re.sub(r'[^A-Za-z0-9]', '', text.upper())
   match = re.match(r'^([A-Z]{2})(\d{2})([A-Z0-9]{1,6})$', clean)
   return f"{match.group(1)}{match.group(2)} {match.group(3)}" if match else clean


def insert_number_plate(dock_name, timestamp, number_plate, text_conf):
   try:
       cursor.execute("""
           INSERT INTO dock_number_plate (timestamp, dock, number_plate, text_conf)
           VALUES (%s, %s, %s, %s)
       """, (timestamp, dock_name, number_plate, text_conf))
       connection.commit()
       print(f"[INSERTED] {dock_name} | {number_plate} | {text_conf:.2f} | {timestamp}")
   except Exception as e:
       print("Insert error:", e)
       connection.rollback()


def visualize_results(image, results, save_path):
   for item in results:
       text = item.get("text", "")
       poly = item["poly"]
       cx, cy = get_centroid(poly)
       pts = np.array([[poly[0], poly[1]], [poly[2], poly[3]], [poly[4], poly[5]], [poly[6], poly[7]]], np.int32)
       pts = pts.reshape((-1, 1, 2))
       cv2.polylines(image, [pts], True, (0, 255, 0), 1)
       cv2.putText(image, text, (int(cx), int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
   cv2.imwrite(save_path, image)


# Simple grouping logic: each result is its own group, sorted by Y
def group_by_y(results):
   return [[item] for item in sorted(results, key=lambda x: get_centroid(x['poly'])[1])]


# Kafka loop
# ... [imports and setup remain unchanged]


# Kafka loop
for msg in consumer:
 
   message = msg.value
  


   sensor_id = message.get("sensorId", "")
   #print(f"[INFO] Sensor ID: {sensor_id}")


   if sensor_id not in [f'dock{i}' for i in range(1, 21)]:
       #print("[SKIPPED] Not a valid dock sensor.")
       continue


   timestamp_str = message.get('@timestamp')
   #print(f"[INFO] Timestamp: {timestamp_str}")


   try:
       timestamp_utc = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%fZ')
       timestamp_ist = timestamp_utc.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata'))
   except Exception as e:
       #print(f"[ERROR] Failed to parse timestamp: {e}")
       continue


   linecross = message.get('linecross', {})
   print(f"linecross: {linecross}")
   if (linecross.get('entry') or 0) > 0 or (linecross.get('exit') or 0) > 0:
       print(f"[LINECROSS] {sensor_id} | Entry: {linecross.get('entry')} | Exit: {linecross.get('exit')} | Time: {timestamp_ist}")


       objects = message.get('objects', [])
       print(f"[INFO] Found {len(objects)} objects")


       for obj in objects:
           fields = obj.split('|')
           if len(fields) < 8:
               print("[WARNING] Unexpected object format:", obj)
               continue


           if fields[6] != 'number_plate':
               continue


           print("[INFO] Processing number_plate object")
           bbox = list(map(int, map(float, fields[2:6])))
           image_path = fields[7]
           print(f"[INFO] Image path: {image_path}")


           frame = cv2.imread(image_path)
           if frame is None:
               print("[ERROR] Image not found or failed to load:", image_path)
               continue


           x1, y1, x2, y2 = bbox
           crop = frame[y1:y2, x1:x2]
           print("[INFO] Cropped image extracted.")


           crop = cv2.resize(crop, (500, 400))
           blacked_img = np.zeros((768, 1024, 3), dtype=np.uint8)
           blacked_img[300:700, 450:950] = crop


           dock_folder = os.path.join(BLACKED_CROP_BASE_DIR, sensor_id)
           os.makedirs(dock_folder, exist_ok=True)
           blacked_filename = f"{sensor_id}_{timestamp_ist.strftime('%Y%m%d_%H%M%S')}.jpg"
           blacked_path = os.path.join(dock_folder, blacked_filename)
           cv2.imwrite(blacked_path, blacked_img)
           print(f"[SAVED] Blacked cropped image: {blacked_path}")


           print("[INFO] Sending image to Triton...")
           result = send_to_triton(blacked_img)


           if not result:
               print("[WARNING] No result from Triton")
               continue


           print("\n[OCR RESULTS]")
           for idx, item in enumerate(result):
               text = item.get("text", "")
               conf = item.get("text_conf", 0)
               poly = item["poly"]
               cx, cy = get_centroid(poly)
               y_coords = poly[1::2]
               min_y = min(y_coords)
               print(f"{idx+1}. Text: {text}, Conf: {conf:.2f}, Centroid: ({cx:.1f}, {cy:.1f}), Min Y: {min_y:.1f}, Poly: {poly}")


           grouped = group_by_y(result)
           sorted_rows = [sorted(row, key=lambda item: get_centroid(item['poly'])[0]) for row in grouped]
           merged_text = ' '.join([''.join([item['text'] for item in row if 'text' in item]) for row in sorted_rows])
           formatted = format_number_plate(merged_text)
           sum_conf = sum([item.get('text_conf', 0) for item in result])


           print(f"[MERGED] {merged_text}")
           print(f"[FORMATTED] {formatted}")


           if formatted:
               insert_number_plate(
                   dock_name=sensor_id,
                   timestamp=timestamp_ist,
                   number_plate=formatted,
                   text_conf=sum_conf
               )


           debug_path = os.path.join(dock_folder, f"debug_{blacked_filename}")
           visualize_results(blacked_img, result, save_path=debug_path)
           print(f"[DEBUG IMAGE] Saved: {debug_path}")


