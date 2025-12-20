import argparse
import numpy as np
import sys,os
import cv2
import json
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
import re
from processing import preprocess, postprocess
from labels import COCOLabels


def sort_coordinates(coordinates):
   
    sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[1]))
    #sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[2], coord[1]))
    return sorted_coordinates    
   
def concatenate_first_elements(array):
    """
    Concatenates the first element of each tuple in the array into a single string.

    :param array: The input array containing tuples.
    :return: A string composed of the first elements of each tuple in the array.
    """
    # Extract the first element from each tuple and join them into a string
    return ''.join([element[0] for element in array])

def calculate_y_centroids(bounding_boxes):
    """Calculate the y centroids of bounding boxes."""
    y_centroids = []
    for box in bounding_boxes:
        # Assuming box format is [x_min, y_min, x_max, y_max]
        y_centroids.append([box[2]])
    return np.array(y_centroids)
def cluster_bounding_boxes(bounding_boxes, n_clusters=3):
  
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

    # Sort bounding boxes by their y centroid
    sorted_boxes = [box for _, box in sorted(zip(y_centroids, bounding_boxes))]

    # Group boxes that lie on the same line
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







def get_ocr_results(data):
    try:

        coordinates = []
        for i in data:
            poly = i['poly']
            x1,y1,x2,y2,x3,y3,x4,y4=poly
            centroid_x = (x1 + x2 + x3 + x4) / 4
            centroid_y = (y1 + y2 + y3 + y4) / 4
            coordinates.append((i['text'],centroid_x,centroid_y))
        if len(coordinates) > 0:    
            sorted_boxes = group_bounding_boxes_by_line(coordinates)
            for line in sorted_boxes:
                new_line = sort_coordinates(line)
                print(concatenate_first_elements(new_line))
                #for words in new_line:
                #    print(words)
    except Exception as e:
        print(sys.exc_info()[0])
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)


def pad_image(image):
    original_height, original_width = image.shape[:2]
    desired_width = 1024
    desired_height = 768

    # Calculate the padding values
    top_padding = (desired_height - original_height) // 2
    bottom_padding = desired_height - original_height - top_padding
    left_padding = (desired_width - original_width) // 2
    right_padding = desired_width - original_width - left_padding
    desired_width = 1024
    desired_height = 768

    # Calculate the padding values
    top_padding = (desired_height - original_height) // 2
    bottom_padding = desired_height - original_height - top_padding
    left_padding = (desired_width - original_width) // 2
    right_padding = desired_width - original_width - left_padding
    padded_image = cv2.copyMakeBorder(image,top_padding,bottom_padding,left_padding,right_padding,borderType=cv2.BORDER_CONSTANT,value=[0, 0, 0])
    return padded_image



INPUT_NAMES = ["images"]
OUTPUT_NAMES = ["num_dets", "det_boxes", "det_scores", "det_classes"]
triton_client = grpcclient.InferenceServerClient(url="localhost:8001")

def run_triton_inference(data, model_name="nvOCDR"):
    try:
        
        if data is None:
            raise ValueError(f"Could not read image from path: {image_path}")
        print(f"Image shape: {data.shape}")
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
def pad_and_resize_image(image):
    # Desired aspect ratio and size
    target_aspect_ratio = 1024 / 768
    target_size = (1024, 768)

    # Read the input imag
    height, width, _ = image.shape
    current_aspect_ratio = width / height

    # Pad the image if needed to match the target aspect ratio
    if current_aspect_ratio > target_aspect_ratio:
        # Image is too wide, pad height
        new_height = int(width / target_aspect_ratio)
        top_padding = (new_height - height) // 2
        bottom_padding = new_height - height - top_padding
        padded_image = cv2.copyMakeBorder(image, top_padding, bottom_padding, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    elif current_aspect_ratio < target_aspect_ratio:
        # Image is too tall, pad width
        new_width = int(height * target_aspect_ratio)
        left_padding = (new_width - width) // 2
        right_padding = new_width - width - left_padding
        padded_image = cv2.copyMakeBorder(image, 0, 0, left_padding, right_padding, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    else:
        # The image already matches the target aspect ratio
        padded_image = image

    # Resize the padded image to the target size
    resized_image = cv2.resize(padded_image, target_size, interpolation=cv2.INTER_AREA)
    return resized_image
dirname = "/home/nvidia/truck_tab_data/"
img_paths = os.listdir(dirname)
img_paths = sorted(img_paths)
for paths in img_paths:
    filepath = os.path.join(dirname,paths)
    print(filepath)
    frame = cv2.imread(filepath)
    get_ocr_results(run_triton_inference(pad_and_resize_image(frame)))
    print("--------------------------------------------------------------------------------------------------------")
