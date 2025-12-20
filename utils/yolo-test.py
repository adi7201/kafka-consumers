import os
import cv2
import numpy as np
import tritonclient.grpc as grpcclient

# Model inputs and outputs
INPUT_NAMES = ["images"]
OUTPUT_NAMES = ["num_dets", "det_boxes", "det_scores", "det_classes"]

# Define your class labels, map class id to name properly
COCOLABELS = {
    0: 'Truck',
    1: 'car',
    2: 'bike',
    3: 'number_plate',
    4: 'person',
    5: 'Autorickshaw'
}

def preprocess(image, target_size):
    """
    Resize and normalize image for YOLO model input.
    """
    image_resized = cv2.resize(image, (target_size[0], target_size))
    image_rgb = cv2.cvtColor(image_resized, cv2.COLOR_BGR2RGB)
    image_norm = image_rgb / 255.0
    image_transposed = np.transpose(image_norm, (2, 0, 1)).astype(np.float32)  # CHW
    return image_transposed

def postprocess(num_dets, det_boxes, det_scores, det_classes, orig_w, orig_h):
    """
    Transform model outputs into interpretable bounding boxes.
    """
    detections = []
    n = int(num_dets)
    for i in range(n):
        score = det_scores[i]
        if score < 0.3:
            continue
        bbox = det_boxes[i]  # [x1, y1, x2, y2] normalized coords
        class_id = int(det_classes[i])
        x1 = int(bbox * orig_w)
        y1 = int(bbox * orig_h)
        x2 = int(bbox * orig_w)
        y2 = int(bbox * orig_h)
        # Clamp to image dimensions
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(orig_w - 1, x2), min(orig_h - 1, y2)
        detections.append({
            'classID': class_id,
            'label': COCOLABELS.get(class_id, "unknown"),
            'bbox': (x1, y1, x2, y2),
            'score': score
        })
    return detections

def crop_plate_only(image, bbox, canvas_size=(1024, 768)):
    """
    Crop the number plate and place it on a black canvas.
    """
    x1, y1, x2, y2 = bbox
    cropped = image[y1:y2, x1:x2]
    canvas = np.zeros((canvas_size[1], canvas_size, 3), dtype=np.uint8)

    h, w = cropped.shape[:2]
    scale = min(canvas_size / w, canvas_size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_AREA)
    x_offset = (canvas_size - new_w) // 2
    y_offset = (canvas_size - new_h) // 2
    canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    return canvas

def run_yolo_on_image(image, client):
    """
    Run YOLO model inference and return cropped number plate image if any.
    """
    inputs = [grpcclient.InferInput(INPUT_NAMES, [1, 3, 640, 640], "FP32")]
    outputs = [grpcclient.InferRequestedOutput(name) for name in OUTPUT_NAMES]

    input_buffer = preprocess(image, [640, 640])
    input_buffer = np.expand_dims(input_buffer, axis=0)
    inputs.set_data_from_numpy(input_buffer)

    results = client.infer(model_name="yolov7", inputs=inputs, outputs=outputs)

    num_dets = results.as_numpy(OUTPUT_NAMES)
    det_boxes = results.as_numpy(OUTPUT_NAMES)
    det_scores = results.as_numpy(OUTPUT_NAMES)
    det_classes = results.as_numpy(OUTPUT_NAMES)

    detections = postprocess(num_dets, det_boxes, det_scores, det_classes,
                             image.shape, image.shape)

    for det in detections:
        if det['label'] == 'number_plate':
            return crop_plate_only(image, det['bbox'])

    return None

def process_folder(input_folder, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    client = grpcclient.InferenceServerClient(url='localhost:8001')
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    for filename in os.listdir(input_folder):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in valid_exts:
            continue
        img_path = os.path.join(input_folder, filename)
        image = cv2.imread(img_path)
        if image is None:
            print(f"Failed to read {filename}")
            continue
        plate_img = run_yolo_on_image(image, client)
        if plate_img is not None:
            out_path = os.path.join(output_folder, filename)
            cv2.imwrite(out_path, plate_img)
            print(f"Cropped number plate saved: {out_path}")
        else:
            print(f"No number plate found in {filename}")


if __name__ == "__main__":
    input_dir = "/home/ai4m/rhenus-ingate"  # Change to your input folder path
    output_dir = "output_plates"             # Change to your desired output folder
    process_folder(input_dir, output_dir)

