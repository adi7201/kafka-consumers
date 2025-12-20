import json,os,ast,sys
import psycopg2
import configparser
from kafka import KafkaConsumer,KafkaProducer
from datetime import datetime
import pytz, time 
from collections import deque
import traceback
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
import cv2, numpy as np
import logging
from logging.handlers import RotatingFileHandler
from centriod_clustering import *
from utils.yolo_triton import * 
from utils.yolo_triton import get_ocr_results as ocr_results_utils
from termcolor import colored
from shapely.geometry import Polygon
def setup_logging():
    """
    Set up logging with enhanced configuration including rotation and console output
    """
    todays_date = datetime.now().strftime("%Y-%m-%d")
    log_directory = os.path.join("logs", todays_date)
    os.makedirs(log_directory, exist_ok=True)
    log_filename = os.path.join(log_directory, f"{todays_date}_gate_consumer.log")
    
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplication
    if logger.handlers:
        logger.handlers.clear()
    
    # Create a formatter for detailed logging
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Create a file handler with rotation (10MB max size, keep 10 backup files)
    file_handler = RotatingFileHandler(
        log_filename, maxBytes=10*1024*1024, backupCount=10, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    # Create a console handler for terminal output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # Log startup message
    logging.info("Logging initialized")
    return logger

# Initialize logger
logger = setup_logging()

def load_config(config_file="config.ini"):
    """Load configuration from the specified file"""
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        logger.info(f"Configuration loaded from {config_file}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}", exc_info=True)
        traceback.print_exc()
        raise


class KafkaJsonConsumer:
    def __init__(
        self, topic, config_file="config.ini", bootstrap_servers="localhost:9092"
    ):
        logger.info(f"Initializing KafkaJsonConsumer for topic: {topic}")
        
        try:
            self.config = load_config(config_file)
            self.consumer = KafkaConsumer(
                topic,
                bootstrap_servers=bootstrap_servers,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            )
            self.recent_objects = deque(maxlen=10)
            self.triton_client = grpcclient.InferenceServerClient(url="localhost:8001")
            self.db_connection = self.connect_postgres()
            self.previous_timestamp = None
            self.recent_objects = deque(maxlen=5)
            self.tracking_data = []
            self.tracking_vehicle = deque(maxlen=5)
            self.tracking_number_plate = deque(maxlen=5)
            self.producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=lambda v: json.dumps(v).encode('utf-8'))
            logger.info(f"Consumer successfully initialized for topic: {topic}")
            print(f"Consumer initialized for topic: {topic}")
        except Exception as e:
            logger.critical(f"Failed to initialize consumer: {e}", exc_info=True)
            raise


    def connect_postgres(self):
        try:
            logger.info("Connecting to PostgreSQL database")
            connection = psycopg2.connect(
                host=self.config["postgres"]["host"],
                database=self.config["postgres"]["database"],
                user=self.config["postgres"]["user"],
                password=self.config["postgres"]["password"],
            )
            logger.info("PostgreSQL connection established successfully")
            print("PostgreSQL connection established")
            return connection
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}", exc_info=True)
            print(f"Error connecting to PostgreSQL: {e}")
            return None
        

    def consume_messages(self):
        logger.info("Starting to consume messages...")
        print("Starting to consume messages...")
        try:
            message_count = 0
            start_time = time.time()
            
            while True:
                msg_pack = self.consumer.poll(timeout_ms=1000)
                
                # Log statistics periodically
                current_time = time.time()
                if current_time - start_time > 60:  # Log every minute
                    # logger.info(f"Processed {message_count} messages in the last minute")
                    message_count = 0
                    start_time = current_time
                
                for tp, messages in msg_pack.items():
                    for message in messages:
                        try:
                            message_count += 1
                            self.process_message(message.value)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            traceback.print_exc()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down consumer")
        except Exception as e:
            logger.critical(f"Fatal error consuming messages: {e}", exc_info=True)
            traceback.print_exc()
            print(f"Error consuming messages: {e}")

    def Line_cross_and_Detect_check(self,vehicle_array:list,number_plate_array:list,base_msg,sensor_id:str):
        try:
            try:
                line_coords = ast.literal_eval(self.config[sensor_id]["line_coords"])
                # print(f'**********{line_coords=}')
            except Exception as e :
                print(e)
            Polygons,Final_list = [], []
            if (len(vehicle_array) > 1 )and (len(number_plate_array) > 1):
                for Vehicle in vehicle_array:
                    obj_v = Vehicle
                    bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                    poly_v = create_polygon_from_bbox(bbox)
                    Polygons.append((poly_v, obj_v))
                    for n_p in number_plate_array:
                        bbox = (n_p['left'], n_p['top'], n_p['right'], n_p['bottom'])
                        poly_np= create_polygon_from_bbox(bbox)
                        if poly_v.contains_properly(poly_np):
                            Final_list.append([obj_v,n_p])
                            del poly_v, poly_np
                return Final_list  
            elif(len(vehicle_array) == 1 ) and (len(number_plate_array) == 1 ):
                for element in vehicle_array:
                    obj_v = element
                    bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                    poly_v = create_polygon_from_bbox(bbox)
                    for i in number_plate_array:
                        obj_np = i
                        bbox = (obj_np['left'], obj_np['top'], obj_np['right'], obj_np['bottom'])
                        poly_np = create_polygon_from_bbox(bbox)
                        if poly_v.contains_properly(poly_np):
                            Final_list.append([obj_v,obj_np])
                            if check_line_polygon_intersection(poly_v,line_coords=line_coords) or check_line_polygon_intersection(poly_v,line_coords=line_coords) :
                                return Final_list
                            
                                # del poly_v, poly_np
            elif(len(vehicle_array) >= 1 ) and (len(number_plate_array) == 0 ):
                for element in vehicle_array:
                    obj_v = element
                    bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                    poly_v = create_polygon_from_bbox(bbox)
                    if check_line_polygon_intersection(poly_v,line_coords=line_coords):
                        return [element]
            elif(len(vehicle_array) >= 1 ) and (len(number_plate_array) == 1 ):
                Final_list = []
                for element in vehicle_array:
                    obj_v = element
                    bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                    poly_v = create_polygon_from_bbox(bbox)
                    for i in number_plate_array:
                        obj_np = i
                        bbox = (obj_np['left'], obj_np['top'], obj_np['right'], obj_np['bottom'])
                        poly_np = create_polygon_from_bbox(bbox)
                        if poly_v.contains_properly(poly_np):
                            # Final_list.append([obj_v,obj_np])
                            if check_line_polygon_intersection(poly_v,line_coords=line_coords):
                                Final_list.append([obj_v,obj_np])
                                # return [element]
                        if check_line_polygon_intersection(poly_v,line_coords=line_coords):
                            Final_list.append(obj_v)
                return Final_list 
            elif(len(vehicle_array) == 0 ) and (len(number_plate_array) == 1 ):
                Final_list = [] 
                base_msg_copy = [ i for i in base_msg if not i in number_plate_array]
                # print(f"Base msg copy : {base_msg_copy}")
                for element in number_plate_array :
                    obj_np = element
                    bbox = (obj_np['left'], obj_np['top'], obj_np['right'], obj_np['bottom'])
                    poly_np = create_polygon_from_bbox(bbox)
                    for i in base_msg_copy :
                        obj_v = i
                        bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                        poly_v = create_polygon_from_bbox(bbox)
                        if poly_v.contains_properly(poly_np):
                            # Final_list.append([obj_v,obj_np])
                            if check_line_polygon_intersection(poly_v,line_coords=line_coords):
                                Final_list.append([obj_v,obj_np])
                                # return [element]
                        # if check_line_polygon_intersection(poly_v):
                        #     Final_list.append(obj_v)
                return Final_list 
            if(len(vehicle_array) == 1 ) and (len(number_plate_array) == 0 ):
                for element in vehicle_array:
                    obj_v = element
                    bbox = (obj_v['left'], obj_v['top'], obj_v['right'], obj_v['bottom'])
                    poly_v = create_polygon_from_bbox(bbox)
                    if check_line_polygon_intersection(poly_v,line_coords=line_coords):
                        return [element]
            else:
                return []
        except:
            return []     

    def get_ocr_results(self, data):
        try:
            logger.debug("Processing OCR results")
            output = ""
            coordinates = []
            for i in data:
                poly = i["poly"]
                x1, y1, x2, y2, x3, y3, x4, y4 = poly
                centroid_x = (x1 + x2 + x3 + x4) / 4
                centroid_y = (y1 + y2 + y3 + y4) / 4
                coordinates.append((i["text"], centroid_x, centroid_y))
            if len(coordinates) > 0:
                sorted_boxes = self.group_bounding_boxes_by_line(coordinates)
                for line in sorted_boxes:
                    new_line = self.sort_coordinates(line)
                    output += self.concatenate_first_elements(new_line)
                # validated_plate = self.parsing(output)
                validated_plate = output
                logger.debug(f"OCR text extracted: {validated_plate}")
            else:
                logger.warning("No text coordinates found in OCR results")
                return None
            return validated_plate
        except Exception as e:
            logger.error("Error processing OCR results", exc_info=True)
            print(sys.exc_info()[0])
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
            logging.error("Error processing OCR results", exc_info=True)
            return None
        

    def sort_coordinates(self, coordinates):
        # Sort coordinates based on y-coordinate (second element) and then x-coordinate (first element)
        sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[1]))
        # sorted_coordinates = sorted(coordinates, key=lambda coord: (coord[2], coord[1]))
        return sorted_coordinates

    def calculate_y_centroids(self, bounding_boxes):
        """Calculate the y centroids of bounding boxes."""
        y_centroids = []
        for box in bounding_boxes:
            # Assuming box format is [x_min, y_min, x_max, y_max]
            y_centroids.append([box[2]])
        return np.array(y_centroids)

    def cluster_bounding_boxes(self, bounding_boxes, n_clusters=3):
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

    def group_bounding_boxes_by_line(self, bounding_boxes, line_height_threshold=12):
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

    def concatenate_first_elements(self, array):
        return "".join([element[0] for element in array])

    def insert_to_postgres(self, message):
        try:
            logger.info(f"Inserting data to PostgreSQL for tracking_id: {message.get('tracking_id', 'unknown')}")
            
            with self.db_connection.cursor() as cursor:
                utc_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
                ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
                arrival_time = ist_time.strftime(
                    "%Y-%m-%dT%H:%M:%S%z"
                )  # Use %z for UTC offset
                
                vehicle_type = message["class_name"] 
                filename = message["filename"]
                vehicle_number = message["plate_number"]
                active = True
                gate_id = message["sensorId"]
                unique_id = message["tracking_id"]
                event_json = message["event_json"]
                
                # Log key data being inserted
                logger.debug(
                    f"DB Insert: time={arrival_time}, vehicle={vehicle_type}, "
                    f"plate={vehicle_number}, gate={gate_id}, id={unique_id}"
                )
                
                # SQL insert query
                insert_query = """
                INSERT INTO gate_events (timestamp, vehicle_number, event_source, active, filename, vehicle_type, gate_id, unique_id, event_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """
                
                # Execute the SQL command with the actual data
                cursor.execute(
                    insert_query,
                    (
                        arrival_time,
                        vehicle_number,
                        gate_id,
                        active,
                        filename,
                        vehicle_type,
                        gate_id,
                        unique_id,
                        event_json
                    ),
                )

                # Commit the transaction
                self.db_connection.commit()
                logger.info(f"Data successfully inserted for tracking_id: {unique_id}")
                # print("Data inserted successfully into the database")

        except Exception as e:
            logger.error(f"Failed to insert data into database", exc_info=True)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.error(
                f"Failed to insert data into database: {exc_type}, File: {fname}, Line: {exc_tb.tb_lineno}",
                exc_info=True,
            )
            print(exc_type, fname, exc_tb.tb_lineno)
            
            # Check database connection and attempt to reconnect if needed
            if self.db_connection is None or self.db_connection.closed:
                logger.warning("Database connection lost, attempting to reconnect")
                self.db_connection = self.connect_postgres()

    def rescale_coords(self,x1, y1, x2, y2, old_width, old_height, new_width, new_height):
        """
        Rescales coordinates from the original image size to a new resized image size.
        """
        x1_new = int(x1 * new_width / old_width)
        y1_new = int(y1 * new_height / old_height)
        x2_new = int(x2 * new_width / old_width)
        y2_new = int(y2 * new_height / old_height)

        return x1_new, y1_new, x2_new, y2_new
    
    def pad_and_resize_image(self, image, x1, y1, x2, y2):
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
        black_image[y1:y2, x1:x2,:] = image[y1:y2, x1:x2,:]
        # new_target_size = (1280, 736)
        width, height = 1280, 736
        resized_image = self.crop_relative_to_detection(black_image, x1, y1, x2, y2)

        
        return resized_image
        # return black_image

    def crop_relative_to_detection(self,image, x1, y1, x2, y2):
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
    
    def run_ocr(self, filepath, msg_coordinates) -> str:
        try:
            logger.debug(f"Running OCR on {filepath} with coordinates {msg_coordinates}")
            base_path = os.path.basename(filepath)
            x_min, y_min, x_max, y_max = msg_coordinates
            logger.debug(f"OCR coords: {msg_coordinates}")
            # print(f"OCR coords: {msg_coordinates}")
            x_min, y_min, x_max, y_max = float(x_min), float(y_min), float(x_max), float(y_max)
            
            base_image = cv2.imread(filepath)
            # logger.debug(f"Base image shape: {base_image.shape}")
            # print(base_image.shape)
            
            if base_image is not None:
                # print(x_min, y_min, x_max, y_max)
                cropped_image = base_image[int(y_min) : int(y_max), int(x_min) : int(x_max),]
                logger.debug(f"Cropped image shape: {cropped_image.shape}")
                # print("Cropped size ", cropped_image.shape)
                
                file = os.path.basename(filepath)
                os.makedirs("OG_images", exist_ok=True)
                try:
                    cv2.imwrite(f"OG_images/cropped_{file}", cropped_image)
                except Exception as e :
                    print(e)
                    pass
                # padded_image = self.pad_and_resize_image(cropped_image,x_min, y_min, x_max, y_max)
                padded_image = self.pad_and_resize_image(base_image,x_min, y_min, x_max, y_max)
                output_folder = "Triton_input_image"
                os.makedirs(output_folder, exist_ok=True)
                try:
                    output_filename = (f"{os.path.splitext(base_path)[0]}_cropped.jpg")
                    output_path = os.path.join(output_folder, output_filename)
                    cv2.imwrite(output_path, padded_image)
                except Exception as e :
                    print(e)
                inference_result = self.run_triton_inference(padded_image)
                if inference_result is None:
                    ocr_results = ""
                    logger.warning("Inference result is None. OCR Skipped")
                else:
                    ocr_results = self.get_ocr_results(inference_result)
                    logger.info(f"OCR Results: {ocr_results}")
                    return ocr_results
        except Exception as e:
            logger.error(f"Error in OCR processing", exc_info=True)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

 
    def run_triton_inference(self, frame) -> list:
        # Initialize Triton client
        try:
            logger.debug("Running Triton inference")
            model_name = "nvOCDR"
            
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
            results = self.triton_client.infer(
                model_name=model_name, inputs=inputs, outputs=outputs
            )
            predict_text_box = results.as_numpy(output_predicts)
            predict_text_box = list(
                map(lambda x: x[0].decode("utf-8"), predict_text_box)
            )
            predict_text_box_decode = [
                json.loads(predict) for predict in predict_text_box
            ]
            logger.debug(f"Raw OCR result: {predict_text_box_decode[0]}")
            print("RAW OCR: ", predict_text_box_decode[0])
            return predict_text_box_decode[0]

        except InferenceServerException as e:
            logger.error(f"Triton inference server error: {e}", exc_info=True)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
            return None
    def send_recording_command(self,data):
        """Send recording command to Kafka."""
        try:
            self.producer.send('record', value=data)
            self.producer.flush()
            logging.info(f"Recording command sent for stream {data}")
        except Exception as e:
            logging.error(f"Failed to send recording command for stream  {e}")

    def process_message(self, message):
        try:
            message_id = message.get("id", "unknown")
            logger.debug(f"Processing message ID: {message_id}")
            
            if message['linecross']['gate_entry'] > 0:
                logger.info("Gate entry detected")
                duration = 137 
                data = {
                    "command": "start-recording",
                    "start": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "stop": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "sensor": {"id": message["sensorId"]},
                    "filepath": f"/home/ai4m/data/smart-record-gate/{message['sensorId']}_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{duration}.mp4"
                }
                self.send_recording_command(data)
                
                if "objects" in message:
                    self.classifier = {"vehicle":[], "number_plate":[], "person":[]}
                    for obj in message["objects"]:
                        fields = obj.split("|")
                        if len(fields) > 9:
                            # print(message)
                            sensorId_init = message["sensorId"]
                            fields_object = parse_entry(obj)
                            logger.debug(f"Parsed field object: {fields_object['class']}, ID: {fields_object['id']}")
                            self.classifier = {"vehicle":[], "number_plate":[], "person":[]}
                            base_msg = [parse_entry(data) for data in message['objects']] #  message['objects']
                            for element in base_msg:
                                if element['class'] in ["Truck", "car", "bike"] and element['id'] not in self.tracking_vehicle:
                                    logger.debug(f"New vehicle detected: {element['class']}, ID: {element['id']}")
                                    self.classifier['vehicle'].append(element)
                                    self.tracking_vehicle.append(element['id'])

                                if element['class'] == "number_plate" and element['id'] not in self.tracking_number_plate:
                                    logger.debug(f"New number plate detected: ID: {element['id']}")
                                    self.classifier["number_plate"].append(element)
                                    self.tracking_number_plate.append(element['id'])
                            print("Classifier : ",self.classifier)
                            if (fields_object['class'] in ['Truck', 'bike', 'car']) and not (fields_object in self.classifier['vehicle']):
                                # print("Final check if vehicle entered")
                                logger.debug(f"Adding vehicle in final check: {fields_object['class']}, ID: {fields_object['id']}")
                                self.classifier['vehicle'].append(fields_object)
                                # print(f"Final Check Vehicle : {self.classifier['vehicle']}")
                            elif (fields_object['class'] in ['number_plate']) and (not (fields_object in self.classifier['number_plate'])):
                                logger.debug(f"Adding number plate in final check: ID: {fields_object['id']}")
                                self.classifier['number_plate'].append(fields_object)
#######################################################    Line_cross_and_Detect_check Funct for Vehicle and  Number plate   ###########################################################
                            result = self.Line_cross_and_Detect_check(self.classifier["vehicle"], self.classifier['number_plate'],base_msg=base_msg,sensor_id=sensorId_init)
                            logger.debug(f"Line cross check result: {result}")
                            print(f"\nLine Cross Result : {result}")
                            print(f"{self.recent_objects=}")
 ################################################################################################################################################################################
 ########################################################################  Insertion Check Cases ################################################################################                         
                            try:
                                if (not result):
                                    print("Got Empty results, Pass on!  ")
                                    pass
                                elif len(result) == 1 or (result!=None):
                                    try:
                                        try: 
                                            try:
                                                if isinstance(result[0],list):
                                                    element = result[0]
                                                    result_id = [element1['id'] for element1 in element]
                                                    # logger.debug(f"Result IDs: {result_id}")
                                                if  isinstance(result[0],dict):
                                                    element = result[0]
                                                    result_id = [element['id']]
                                                    # logger.debug(f"Result IDs: {result_id}")
                                            except Exception as e:
                                                logger.error(f"Error extracting result IDs: {e}", exc_info=True)
                                                print(e)
                                                pass
                                            if all(id not  in self.recent_objects  for id in result_id): #### Major Problem line 
                                                # print("OCR:",element)
                                                OCR_data = self.run_ocr(element[0]['filename'],(int(element[1]['left']-40),int(element[1]['top']-20),int(element[1]['right']+40),int(element[1]['bottom']+20)))
                                                sensorid = message["sensorId"]
                                                event_data = {
                                                        "tracking_id":element[0]['id'],
                                                        "sensorId":sensorid ,
                                                        "class_name": element[0]['class'] ,
                                                        "filename": element[0]['filename'],
                                                        "plate_number": OCR_data if OCR_data else "",   
                                                        "event_json": json.dumps(message)
                                                    }
                                                self.insert_to_postgres(event_data)
                                                logger.info(f"Event inserted: {event_data}")
                                                print(colored("Inserted to database Postgres!!!! ", 'red'),"\n",colored("Test Passed !!!", 'green'))
                                                for result_element in result[0]:
                                                    self.recent_objects.append(result_element['id'])
                                                # print("Nested try OCR_data :",OCR_data)
                                                del result
                                            else:
                                                del result
                                        except:
                                            # print("nested except" )
                                            # print("In instance dict ",isinstance(result[0],dict))
                                            if isinstance(result[0],dict) and (result [0]['id'] not in self.recent_objects ):
                                                # print("CHecked isinstances!")
                                                if (result[0]['class'] == "Truck"):
                                                    print("Truck EVENT ")
                                                    try:
                                                        data = result[0]
                                                        # print(data)
                                                        try:
                                                            image = cv2.imread(result[0]['filename'])
                                                            try:
                                                                resize_data = crop_and_resize_image(image, int(result[0]['left']),int(result[0]['top']),int(result[0]['right']),int(result[0]['bottom']),sensorId_init)
                                                                print(f"resize_data : {resize_data.shape}")
                                                            except Exception as e :
                                                                print(e)
                                                                pass
                                                        except Exception as e :
                                                            print(e)
                                                            pass
                                                        os.makedirs('Triton_input_image',exist_ok=True)
                                                        print(f"Truck shape : {resize_data.shape}\n")
                                                        print(f"Path: {os.path.join('Triton_input_image',os.path.basename(result[0]['filename']))}\n")
                                                    except Exception as e :
                                                        print(e)

                                                    try:
                                                        try:
                                                            logger.info("\nTriton Yolo started")
                                                            data = YOLO(resize_data)
                                                            print(f'{data}')
                                                        except Exception as e :
                                                            print(e)
                                                        if data is not None:
                                                            try:
                                                                raw_data = run_triton_inference(data)
                                                                ocr_data = ocr_results_utils(raw_data)
                                                                print("OCR_DATA_UTILS:",ocr_data)
                                                                try:
                                                                    #file_path = os.path.join("Triton_input_image",os.path.basename(result[0]['filename'])+'_triton.png'
                                                                    cv2.imwrite(os.path.join("Triton_input_image",os.path.basename(result[0]['filename'])+'_triton.png'),data)
                                                                except Exception as e :
                                                                    print(e)
                                                                    pass
                                                                del raw_data,data
                                                            except Exception as e :
                                                                print(e)
                                                        else:
                                                            try:
                                                                logger.info("[YOLO] @Number Plate not found !")
                                                                print(f"Input data size {resize_data.shape}")
                                                                raw_data = run_triton_inference(resize_data)
                                                                ocr_data = ocr_results_utils(raw_data)
                                                                print("Else OCR_DATA_UTILS:",ocr_data)
                                                                try:
                                                                    cv2.imwrite(os.path.join("Triton_input_image",os.path.basename(result[0]['filename'])+'no_np.png'),resize_data)
                                                                except Exception as e :
                                                                    print(f"Error in writing image : {e}")
                                                                    # pass
                                                                del raw_data,data
                                                            except Exception as e :
                                                                print(e)
                                                            # ocr_data= ''
                                                    except Exception as e :
                                                        ocr_data= ''
                                                        traceback.print_exc()
                                                        print(f"Error in writing image : {e}")

                                                    # OCR_data = self.run_ocr(result[0]['filename'],(int(result[0]['left']),int(result[0]['top']),int(result[0]['right']),int(result[0]['bottom'])))
                                                    sensorid = message["sensorId"]
                                                    event_data = {
                                                        "tracking_id": result[0]['id'],
                                                        "sensorId":sensorid ,
                                                        "class_name": result[0]['class'] ,
                                                        "filename": result[0]['filename'],
                                                        "plate_number": ocr_data if ocr_data else "",   
                                                        "event_json": json.dumps(message)
                                                    }
                                                    # print(f"\nEvent data : {event_data}")
                                                    self.insert_to_postgres(event_data)
                                                    logger.info(f"Truck Event inserted: {event_data}")
                                                    self.recent_objects.append(result[0]['id'])
                                                    print(colored("Inserted to database Postgres!!!! ", 'red'),colored("Test Passed !!!", 'green'))
                                                    # print("Nested  Except OCR_data :",ocr_data) 
                                                elif(result[0]['class'] == "number_plate"):
                                                    print("\nNumber_plate")
                                                    #int(y_min -10 ) : int(y_max +20 ), int(x_min - 40 ) : int(x_max + 40 )
                                                    OCR_data = self.run_ocr(result[0]['filename'],(int(result[0]['left']-40),int(result[0]['top']-10),int(result[0]['right']+40),int(result[0]['bottom']+20)))
                                                    sensorid = message["sensorId"]
                                                    event_data = {
                                                        "tracking_id": result[0]['id'],
                                                        "sensorId":sensorid ,
                                                        "class_name": result[0]['class'] ,
                                                        "filename": result[0]['filename'],
                                                        "plate_number": OCR_data if OCR_data else "",   
                                                        "event_json": json.dumps(message)
                                                    }
                                                    logger.info(f"NP Event inserted: {event_data}")
                                                    self.insert_to_postgres(event_data)
                                                    print(colored("Inserted to database Postgres!!!! ", 'red'),colored("Test Passed !!!", 'green'))
                                                    self.recent_objects.append(result[0]['id'])
                                                    # print("Nested  Except OCR_data :",OCR_data)
                                                else:
                                                    #int(y_min -10 ) : int(y_max +20 ), int(x_min - 40 ) : int(x_max + 40 )
                                                    OCR_data = self.run_ocr(result[0]['filename'],(int(result[0]['left']),int(result[0]['top']),int(result[0]['right']),int(result[0]['bottom'])))
                                                    sensorid = message["sensorId"]
                                                    event_data = {
                                                        "tracking_id": result[0]['id'],
                                                        "sensorId":sensorid ,
                                                        "class_name": result[0]['class'] ,
                                                        "filename": result[0]['filename'],
                                                        "plate_number": OCR_data if OCR_data else "",   
                                                        "event_json": json.dumps(message)
                                                    }
                                                    self.insert_to_postgres(event_data)
                                                    logger.info(f"Event inserted: {event_data}")
                                                    self.recent_objects.append(result[0]['id'])
                                            else:
                                                print(f"Presence in {colored(result[0]['id'],'red')} in {self.recent_objects}")
                                    except:
                                        pass
####################################################################################################################################33
                                del self.classifier
                            except Exception as e:
                                traceback.print_exc()
                                print(f"Error  in insertion message : {e}")
                                logger.error(f"An error message in inserting to postgres  : {e}")
        except Exception as e:
            traceback.print_exc()
            print(f"Error consuming messages: {e}")
            logger.error(f"This is an error message : {e}")

if __name__ == "__main__":
    topic = "dsbay"
    consumer = KafkaJsonConsumer(
        topic, config_file="config.ini", bootstrap_servers="localhost:9092"
    )
    consumer.consume_messages()
