import json
import boto3
import os,sys
import traceback
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
import cv2
import numpy as np
import psycopg2
# Initialize the SQS and S3 clients
sqs = boto3.client("sqs")
s3 = boto3.client('s3')
sqs_queue_url = "https://sqs.ap-south-1.amazonaws.com/115935124242/rhenus"
s3_bucket_name = 'rhenus-truck-tab-images'  # Define your S3 bucket name
triton_url = "localhost:8001"
triton_client = grpcclient.InferenceServerClient(url=triton_url)
# Directory to save downloaded images
local_image_dir = "/home/ai4m/truck_tab_data"
os.makedirs(local_image_dir, exist_ok=True)


def sort_coordinates(coordinates):
    # Sort coordinates based on y-coordinate (second element) and then x-coordinate (first element)
    sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[1]))
    #sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[2], coord[1]))
    return sorted_coordinates    
    
def calculate_y_centroids(bounding_boxes):
    """Calculate the y centroids of bounding boxes."""
    y_centroids = []
    for box in bounding_boxes:
        # Assuming box format is [x_min, y_min, x_max, y_max]
        y_centroids.append([box[2]])
    return np.array(y_centroids)
def cluster_bounding_boxes(bounding_boxes, n_clusters=3):
    """Cluster bounding boxes based on their y centroids."""
    y_centroids = calculate_y_centroids(bounding_boxes)
    # K-Means clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(y_centroids)
    labels = kmeans.labels_
    # Group bounding boxes by their cluster labels
    clustered_boxes = {}
    for label, box in zip(labels, bounding_boxes):
        if label not in clustered_boxes:
            clustered_boxes[label] = []
        clustered_boxes[label].append(box)
    return clustered_boxes
def group_bounding_boxes_by_line(bounding_boxes, line_height_threshold=12):
    y_centroids = [(box[2]) for box in bounding_boxes]
    sorted_boxes = [box for _, box in sorted(zip(y_centroids, bounding_boxes))]
    lines = []
    current_line = [sorted_boxes[0]]

    for box in sorted_boxes[1:]:
        # Check if the current box is close enough to the previous box to be on the same line
        if (box[2])  - (current_line[-1][2]) <= line_height_threshold:
            current_line.append(box)
        else:
            lines.append(current_line)
            current_line = [box]
    lines.append(current_line)  # Add the last line
    return lines



def concatenate_first_elements(array):
    return ''.join([element[0] for element in array])


def pad_and_resize_image(image):
   
    target_aspect_ratio = 1024 / 768
    target_size = (1024, 768)

    
    height, width, _ = image.shape
    current_aspect_ratio = width / height

   
    if current_aspect_ratio > target_aspect_ratio:
        new_height = int(width / target_aspect_ratio)
        top_padding = (new_height - height) // 2
        bottom_padding = new_height - height - top_padding
        padded_image = cv2.copyMakeBorder(image, top_padding, bottom_padding, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    elif current_aspect_ratio < target_aspect_ratio:
       
        new_width = int(height * target_aspect_ratio)
        left_padding = (new_width - width) // 2
        right_padding = new_width - width - left_padding
        padded_image = cv2.copyMakeBorder(image, 0, 0, left_padding, right_padding, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    else:
       
        padded_image = image

   
    resized_image = cv2.resize(padded_image, target_size, interpolation=cv2.INTER_AREA)
    return resized_image




def get_ocr_results(data):
    try:
        output =""
        coordinates = []
        for i in data:
            poly = i['poly']
            x1,y1,x2,y2,x3,y3,x4,y4=poly
            centroid_x = (x1 + x2 + x3 + x4) / 4
            centroid_y = (y1 + y2 + y3 + y4) / 4
            coordinates.append((i['text'],centroid_x,centroid_y))
            
        sorted_boxes = group_bounding_boxes_by_line(coordinates)
        for line in sorted_boxes:
            new_line = sort_coordinates(line)
            print(concatenate_first_elements(new_line))
            output += concatenate_first_elements(new_line)
        return output
    except Exception as e:
        print(sys.exc_info()[0])
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)





# PostgreSQL connection function
def get_postgres_connection():
    return psycopg2.connect(
        dbname="rhenus",
        user="postgres",
        password="rhenus",
        host="localhost",
        port="5432"
    )

# Function to insert data into PostgreSQL
def insert_to_postgres(timestamp, image_filename, license_number):
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO tab_number_plate (timestamp, image, number)
        VALUES (%s, %s, %s)
        """
        cursor.execute(insert_query, (timestamp, image_filename, license_number))
        conn.commit()
        
        print(f"Inserted into PostgreSQL: {timestamp}, {image_filename}, {license_number}")
    except Exception as e:
        print(f"Error inserting into PostgreSQL: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def download_image_from_s3(image_filename, download_path):
    try:
        s3_key = image_filename   
        s3.download_file(s3_bucket_name, s3_key, download_path)
        print(f"Downloaded image from S3: {download_path}")
        return download_path
    except Exception as e:
        print(f"Error downloading image from S3: {str(e)}")
        return None

# Function to run Triton inference
def run_triton_inference(image_path, model_name="nvOCDR"):
    try:
        data = cv2.imread(image_path)
        if data is None:
            raise ValueError(f"Could not read image from path: {image_path}")

        data = pad_and_resize_image(data)
        print(f"Image shape after padding and resizing: {data.shape}")
        inputs = []
        outputs = []
        input_data_name = "INPUT_DATA"
        output_predicts = "OUTPUT_TEXT_AND_BOX"

        inputs.append(
            grpcclient.InferInput(
                input_data_name, (data.shape[0], data.shape[1], 3), "UINT8"
            )
        )
        outputs.append(grpcclient.InferRequestedOutput(output_predicts))
        inputs[0].set_data_from_numpy(data)
        results = triton_client.infer(
            model_name=model_name, inputs=inputs, outputs=outputs
        )
        predict_text_box = results.as_numpy(output_predicts)
        predict_text_box = list(map(lambda x: x[0].decode("utf-8"), predict_text_box))
        predict_text_box_decode = [json.loads(predict) for predict in predict_text_box]
        return predict_text_box_decode[0]
    except InferenceServerException as e:
        print(f"Error during Triton inference: {str(e)}")
        return None


def receive_and_process_messages():
    response = sqs.receive_message(
        QueueUrl=sqs_queue_url,
        MaxNumberOfMessages=10,   
        WaitTimeSeconds=10,  
    )
    if "Messages" not in response:
        print("No messages to process.")
        return

    for message in response["Messages"]:
        message_body = json.loads(message["Body"])
        image_filename = message_body.get("image_url")  
        timestamp = message_body.get("timestamp")
        local_image_path = os.path.join(local_image_dir, image_filename)
        downloaded_image_path = download_image_from_s3(image_filename, local_image_path)
        
        if downloaded_image_path:
            ocr_result = run_triton_inference(downloaded_image_path)
            license_number = get_ocr_results(ocr_result)
            print(license_number)            
            if license_number:
                print(f"OCR result for {downloaded_image_path}: {license_number}")
                insert_to_postgres(timestamp, image_filename, license_number)

        sqs.delete_message(
            QueueUrl=sqs_queue_url, ReceiptHandle=message["ReceiptHandle"]
        )
        print(f"Deleted message with ReceiptHandle: {message['ReceiptHandle']}")
if __name__ == "__main__":
    while True:
        receive_and_process_messages()
