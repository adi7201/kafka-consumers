import numpy as np
import sys,json
import cv2, os 
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
# from utils import *
from utils.processing import preprocess, postprocess
from utils.labels import COCOLabels
from utils import boundingbox 
#import BoundingBox
sys.path.append('/home/ai4m/develop/rhenus_backend_Script/Testing_Consumer/utils')
INPUT_NAMES = ["images"]
OUTPUT_NAMES = ["num_dets", "det_boxes", "det_scores", "det_classes"]
# sys.path.append()
def get_ocr_results(data):
    try:
        # logger.debug("Processing OCR results")
        output = ""
        coordinates = []
        for i in data:
            poly = i["poly"]
            x1, y1, x2, y2, x3, y3, x4, y4 = poly
            centroid_x = (x1 + x2 + x3 + x4) / 4
            centroid_y = (y1 + y2 + y3 + y4) / 4
            coordinates.append((i["text"], centroid_x, centroid_y))
        if len(coordinates) > 0:
            sorted_boxes = group_bounding_boxes_by_line(coordinates)
            for line in sorted_boxes:
                new_line = sort_coordinates(line)
                output += concatenate_first_elements(new_line)
            # validated_plate = self.parsing(output)
            validated_plate = output
            # logger.debug(f"OCR text extracted: {validated_plate}")
        else:
            validated_plate = output
            pass
            # logger.warning("No text coordinates found in OCR results")
            # return None
        return validated_plate
    except Exception as e:
        # logger.error("Error processing OCR results", exc_info=True)
        print(sys.exc_info()[0])
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        # logging.error("Error processing OCR results", exc_info=True)
        return None
    

def sort_coordinates(coordinates):
    # Sort coordinates based on y-coordinate (second element) and then x-coordinate (first element)
    sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[1]))
    # sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[2], coord[1]))
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
    y_centroids = self.calculate_y_centroids(bounding_boxes)
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
        if (box[2]) - (current_line[-1][2]) <= line_height_threshold:
            current_line.append(box)
        else:
            lines.append(current_line)
            current_line = [box]
    lines.append(current_line)  # Add the last line
    return lines

def concatenate_first_elements( array):
    return "".join([element[0] for element in array])

def pad_and_resize_image(image, x1, y1, x2, y2):
    """
    Resize the original image to fit within a 1024x768 black canvas,
    adjust the coordinates proportionally, crop the region, and place it back.
    """
    # target_size = (1024, 768)  # (width, height)
    # x1_new, y1_new, x2_new, y2_new = self.rescale_coords(x1, y1, x2, y2, old_width=2560, old_height=1440, new_width=1024, new_height=768)
    target_size = (image.shape[0],image.shape[1])
    # # Resize the image
    # resized_image = cv2.resize(image, (target_size[0], target_size[1]), interpolation=cv2.INTER_AREA)
    print(f"Base IMage shape : {image.shape}")
    # # Create a black canvas
    black_image = np.zeros((target_size[0], target_size[1], 3), dtype=np.uint8)
    print(black_image.shape)
    x1, y1, x2, y2 =  int(x1), int(y1), int(x2), int(y2)
    black_image[y1:y2, x1:x2,:] = image[y1:y2, x1:x2,:]
    #data_img = image[y1:y2, x1:x2,:]
    #cv2.imwrite()
    new_target_size = (1024, 768)
    resized_image = cv2.resize(black_image, (new_target_size[0], new_target_size[1]), interpolation=cv2.INTER_AREA)

    # black_image[y1_new:y2_new, x1_new:x2_new,:] = resized_image[y1_new:y2_new, x1_new:x2_new,:]
    return resized_image

 
def run_triton_inference(frame) -> list:
    # Initialize Triton client
    try:
        # logger.debug("Running Triton inference")
        model_name = "nvOCDR"
        triton_client = grpcclient.InferenceServerClient(url="localhost:8001")
        # Prepare image
        # if frame.shape[0] == 768 and frame.shape[1] == 1024:
        #     data = self.pad_and_resize_image(frame)
        data = frame.copy()
        
        # Prepare input and output for Triton inference
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

        # Perform inference
        results = triton_client.infer(
            model_name=model_name, inputs=inputs, outputs=outputs
        )
        predict_text_box = results.as_numpy(output_predicts)
        predict_text_box = list(
            map(lambda x: x[0].decode("utf-8"), predict_text_box)
        )
        predict_text_box_decode = [
            json.loads(predict) for predict in predict_text_box
        ]
        # logger.debug(f"Raw OCR result: {predict_text_box_decode[0]}")
        print("RAW OCR: ", predict_text_box_decode[0])
        return predict_text_box_decode[0]

    except InferenceServerException as e:
        # logger.error(f"Triton inference server error: {e}", exc_info=True)
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        return None
    
def rerun_ocr( data:np.ndarray, msg_coordinates) -> str:
        try:

            x_min, y_min, x_max, y_max = msg_coordinates
            # logger.debug(f"OCR coords: {msg_coordinates}")
            print(f"OCR coords: {msg_coordinates}")
            x_min, y_min, x_max, y_max = float(x_min), float(y_min), float(x_max), float(y_max)
            # base_path = os.path.basename(filepath)
            base_image = data.copy()
            # logger.debug(f"Base image shape: {base_image.shape}")
            print(base_image.shape)
            
            if base_image is not None:
                print(x_min, y_min, x_max, y_max)
                cropped_image = base_image[int(y_min) : int(y_max), int(x_min) : int(x_max),]
                # logger.debug(f"Cropped image shape: {cropped_image.shape}")
                print("Cropped size ", cropped_image.shape)
                
                # file = os.path.basename(filepath)
                # os.makedirs("OG_images", exist_ok=True)
                # cv2.imwrite(f"OG_images/cropped_{file}", cropped_image)
                
                # padded_image = self.pad_and_resize_image(cropped_image,x_min, y_min, x_max, y_max)
                # padded_image = pad_and_resize_image(base_image,x_min, y_min, x_max, y_max)
                output_folder = "Triton_input_image"
                os.makedirs(output_folder, exist_ok=True)
                # output_filename = (f"{os.path.splitext(base_path)[0]}_cropped.jpg")
                # output_path = os.path.join(output_folder, output_filename)
                # cv2.imwrite(output_path, padded_image)
                
                inference_result = run_triton_inference(padded_image)
                if inference_result is None:
                    ocr_results = ""
                    # logger.warning("Inference result is None. OCR Skipped")
                else:
                    ocr_results = get_ocr_results(inference_result)
                    # logger.info(f"OCR Results: {ocr_results}")
                    return ocr_results
        except Exception as e:
            # logger.error(f"Error in OCR processing", exc_info=True)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

def YOLO(data):
    try:
        triton_client = grpcclient.InferenceServerClient(url='localhost:8001')
    except Exception as e:
        print(f"Context creation failed: {e}")
        sys.exit(1)

    # Define input-output buffers
    inputs = [grpcclient.InferInput(INPUT_NAMES[0], [1, 3, 640, 640], "FP32")]
    outputs = [grpcclient.InferRequestedOutput(name) for name in OUTPUT_NAMES]


    input_image = data.copy()
    del data

    if input_image is None:
        print(f"FAILED: could not load  image ")
        # continue
        pass

    input_image_buffer = preprocess(input_image, [640, 640])
    input_image_buffer = np.expand_dims(input_image_buffer, axis=0)
    inputs[0].set_data_from_numpy(input_image_buffer)

    results = triton_client.infer(model_name='yolov7', inputs=inputs, outputs=outputs)

    num_dets, det_boxes, det_scores, det_classes = [
        results.as_numpy(name) for name in OUTPUT_NAMES
    ]
    
    detected_objects = postprocess(num_dets, det_boxes, det_scores, det_classes,
                                    input_image.shape[1], input_image.shape[0], [640, 640])
    print(f"Detected objects: {len(detected_objects)}")
    try:
        for box in detected_objects:
            label = COCOLabels(box.classID).name
            confidence = box.confidence
            print(f"{label}: {confidence:.2f}")
            width,height,_ = input_image.shape
            black_image = np.zeros((width, height, 3), dtype=np.uint8)
            try:
                if label in ["number_plate"]:
                    print("Found You !  NUmber plate !!!")
                    # Ensure bounding box is within image dimensions
                    x1, y1, x2, y2 = map(int, [box.x1, box.y1, box.x2, box.y2])
                    black_image_data = black_image.copy()
                        # width,height,_ = input_image.shape
                        # black_image = np.zeros((width, height, 3), dtype=np.uint8)
                    black_image_data[int(y1-20):int(y2+20), int(x1-20):int(x2+20),:] = input_image[y1-20:y2+20, x1-20:x2+20,:]
                    return black_image_data
                        # padded_data = pad_and_resize_image(input_image, x1, y1, x2, y2)
            except Exception as e:
                print(f"Error resizing: {e}")
                return None
                # continue
                
    except Exception as e:
        print(f"Error in processing detected objects: {e}")
        return None
        
def crop_relative_to_detection(image, x1, y1, x2, y2):
        # Convert to int
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))

        # Desired crop size
        crop_width, crop_height = 1280, 736

        # Get center of detection box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2 + 100  # shift down (adjust this value as needed)

        # Calculate crop box around center
        crop_x1 = cx - crop_width // 2
        crop_y1 = cy - crop_height // 2
        crop_x2 = crop_x1 + crop_width
        crop_y2 = crop_y1 + crop_height

        # Clamp to image boundaries
        image_height, image_width = image.shape[:2]
        crop_x1 = max(0, crop_x1)
        crop_y1 = max(0, crop_y1)
        crop_x2 = min(image_width, crop_x2)
        crop_y2 = min(image_height, crop_y2)

        # Adjust if crop goes out of bounds (preserve size)
        if crop_x2 - crop_x1 < crop_width:
            crop_x1 = max(0, crop_x2 - crop_width)
        if crop_y2 - crop_y1 < crop_height:
            crop_y1 = max(0, crop_y2 - crop_height)

        return image[crop_y1:crop_y2, crop_x1:crop_x2]
    

def crop_and_resize_image(image, x1, y1, x2, y2,sensorid):
    """
    Resize the original image to fit within a 1024x768 black canvas,
    adjust the coordinates proportionally, crop the region, and place it back.
    """
    target_size = (1440, 2560)
    # # Resize the image
    # resized_image = cv2.resize(image, (target_size[0], target_size[1]), interpolation=cv2.INTER_AREA)
    # print(f"Base IMage shape : {image.shape}")
    # # Create a black canvas
    black_image = np.zeros((target_size[0], target_size[1], 3), dtype=np.uint8)
    # print(black_image.shape)
    x1, y1, x2, y2 =  int(x1), int(y1), int(x2), int(y2)
    # Compute centroid
    x_centroid = (x1 + x2) // 2
    y_centroid = (y1 + y2) // 2

    # Adjust cropping based on sensorid
    if sensorid == "gate_in":
        x2 = x_centroid  # Crop left half
        y1 = y_centroid  # Start from centroid in height
        y_centroid = (y1 + y2) // 2
        y1 , y2 = y_centroid - 10, y2 + 10
        check = image[y1:y2, x1:x2, :]
        print(f"Gate IN : {check.shape}")
        del check
    elif sensorid == "gate_out":
        x1 = x_centroid  # Crop right half
        y1 = y_centroid  # Start from centroid in height
        check = image[y1:y2, x1:x2, :]
        print(f"Gate OUT : {check.shape}")
        del check
        

    # Ensure cropping is within bounds
    x1, x2 = max(0, x1), min(target_size[1], x2)
    y1, y2 = max(0, y1), min(target_size[0], y2)

    black_image[y1:y2, x1:x2,:] = image[y1:y2, x1:x2,:]
    new_target_size = (1280, 736)
    resized_image = crop_relative_to_detection(black_image, x1, y1, x2, y2)
    #cv2.resize(black_image, (new_target_size[0], new_target_size[1]), interpolation=cv2.INTER_AREA)

    # black_image[y1_new:y2_new, x1_new:x2_new,:] = resized_image[y1_new:y2_new, x1_new:x2_new,:]
    return resized_image
