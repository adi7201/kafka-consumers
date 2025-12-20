import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
import cv2
import numpy as np
import datetime
import json
import re
import os
import sys


triton_client = grpcclient.InferenceServerClient(url="localhost:8001")
inputs = []
outputs = []
input_data_name = "INPUT_DATA"
output_predicts = "OUTPUT_TEXT_AND_BOX"
data= cv2.imread("padded_image.jpg")
print(data.shape)




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
    """
    Group OCR bounding boxes that lie on the same line.

    :param bounding_boxes: A list of bounding boxes in the format [x_min, y_min, x_max, y_max].
    :param line_height_threshold: Maximum difference in y centroids to consider boxes as part of the same line.
    :return: A list of lists, where each sublist contains bounding boxes from the same line.
    """
    # Calculate y centroids for each bounding box
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

# Example usage

# Adjust `line_height_threshold` based on your specific requirements
# Uncomment the next line in actual code to run the function
# lines = group_bounding_boxes_by_line(bounding_boxes, line_height_threshold=10)
# print(lines)
def remove_non_numeric(s):
    """
    Removes all characters from the input string except for numbers.

    :param s: The input string.
    :return: A new string containing only digits.
    """
    return re.sub(r'\D', '', s)
def concatenate_first_elements(array):
    """
    Concatenates the first element of each tuple in the array into a single string.

    :param array: The input array containing tuples.
    :return: A string composed of the first elements of each tuple in the array.
    """
    # Extract the first element from each tuple and join them into a string
    return ''.join([element[0] for element in array])

def extract_initial_numbers(s):
    """
    Extracts the initial sequence of numbers from an alphanumeric string
    until the first occurrence of a non-numeric character.

    :param s: The input alphanumeric string.
    :return: The initial sequence of numbers as a string. Returns an empty
    string if the input does not start with a number.
    """
    match = re.match(r'\d+', s)
    return match.group(0) if match else ''
def extract_numbers_after_keywords(s, keywords):
    """
    Extracts numbers that immediately follow specified keywords in a string.

    :param s: The input string.
    :param keywords: A list of keywords to search for.
    :return: A list of numbers (as strings) found immediately after the specified keywords.
    """
    # Join keywords into a regex pattern that looks for any of the keywords followed by optional whitespace and then a sequence of digits.
    pattern = r'(' + '|'.join(keywords) + r')\s*(\d+)'
    # Find all matches of the pattern in the input string. Each match will have a tuple with the keyword and the number following it.
    matches = re.findall(pattern, s)
    # Extract the numbers from the matches. Each match is a tuple where the second element is the number we're interested in.
    numbers = [match[1] for match in matches]
    return numbers

def remove_special_characters(s):
    """
    Removes special characters from the input string, leaving only alphanumeric characters.

    :param s: The input string.
    :return: A new string with only alphanumeric characters.
    """
    # Replace any character that is not a letter or number with an empty string
    return re.sub(r'[^a-zA-Z0-9]', '', s)
def remove_before_1s(s):
    """
    Removes all characters from the string before '1s'.

    :param s: The input string.
    :return: A new string with all characters before '1s' removed. If '1s' is not found, returns the original string.
    """
    index = s.find('1s')
    if index != -1:
        # Add 2 to the index to include '1s' in the result
        return s[index:]
    else:
        return s

def get_ocr_results(data):
    try:
        output={"mrp":0,"usp":0,"mfg":"","exp":"","qty":0,"batch":""}

        coordinates = []
        for i in data:
            poly = i['poly']
            x1,y1,x2,y2,x3,y3,x4,y4=poly
            centroid_x = (x1 + x2 + x3 + x4) / 4
            centroid_y = (y1 + y2 + y3 + y4) / 4
            coordinates.append((i['text'],centroid_x,centroid_y))
            
        sorted_boxes = group_bounding_boxes_by_line(coordinates)
        mrp_string = ""
        exp_string = ""
        batch_string = ""
        for line in sorted_boxes:
            new_line = sort_coordinates(line)
            print(concatenate_first_elements(new_line))
            for words in new_line:
                print(words)
    except Exception as e:
        print(sys.exc_info()[0])
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)




inputs.append(grpcclient.InferInput(input_data_name, (data.shape[0], data.shape[1], 3), "UINT8"))
outputs.append(grpcclient.InferRequestedOutput(output_predicts))
inputs[0].set_data_from_numpy(data)
results = triton_client.infer(model_name="nvOCDR", inputs=inputs, outputs=outputs)
predict_text_box = results.as_numpy(output_predicts)
predict_text_box = list(map(lambda x: x[0].decode("utf-8"), predict_text_box))
predict_text_box_decode = [json.loads(predict) for predict in predict_text_box]
get_ocr_results(predict_text_box_decode[0])
