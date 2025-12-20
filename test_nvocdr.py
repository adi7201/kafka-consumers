#!/usr/bin/env python

import argparse
import numpy as np
import sys, os 
import cv2, json
import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException
from termcolor import colored
from pprint import pprint
def overlay_text_and_polygons( image, predictions,path)->None:
        
        """ Overlays OCR text and polygons on the image. 
            Args : 
            
               image  = (numpy.ndarrays) , 
            
               predictions = List [json data from model]

               path = Overlayed IMage getting saved in the folder 
            Returns : None 
        """
        text_color = (0, 0, 255)  # White
        poly_color = (0, 255, 0)      # Green
        for item in predictions:
            text = item["text"]
            poly = np.array(item["poly"]).reshape((-1, 2))
            cv2.polylines(image, [poly], isClosed=True, color=poly_color, thickness=2)
            cv2.putText(
                image,
                f"{text}",
                (poly[0][0], poly[0][1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                text_color,
                1,
            )
        cv2.imwrite(path,image)
        print(colored(f"Infered File saved path : {path}",'green'))
        # return image

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode',
                        choices=[ 'folder',"image"],
                        default='folder',
                        help='Run mode. \'image\' will send an image  to the server to test if inference works. \'folder\' will process thee folder images ')
    parser.add_argument('input',
                        type=str,
                        nargs='?',
                        help='Input file to load from in image or folder  mode')
    parser.add_argument('-m',
                        '--model',
                        type=str,
                        required=False,
                        default='nvOCDR',
                        help='Inference model name, default nvOCDR')
    parser.add_argument('--width',
                        type=int,
                        required=False,
                        default=1280,
                        help='Inference model input width, default 1280')
    parser.add_argument('--height',
                        type=int,
                        required=False,
                        default=736,
                        help='Inference model input height, default 736')
    parser.add_argument('-u',
                        '--url',
                        type=str,
                        required=False,
                        default='localhost:8001',
                        help='Inference server URL, default localhost:8001')
    
    FLAGS = parser.parse_args()

    # Create server context
    try:
        triton_client = grpcclient.InferenceServerClient(
            url=FLAGS.url)
    except Exception as e:
        print("context creation failed: " + str(e))
        sys.exit()

    # Health check
    if not triton_client.is_server_live():
        print("FAILED : is_server_live")
        sys.exit(1)

    if not triton_client.is_server_ready():
        print("FAILED : is_server_ready")
        sys.exit(1)

    if not triton_client.is_model_ready(FLAGS.model):
        print("FAILED : is_model_ready")
        sys.exit(1)

#    if FLAGS.model_info:
        # Model metadata
        try:
            metadata = triton_client.get_model_metadata(FLAGS.model)
            print(metadata)
        except InferenceServerException as ex:
            if "Request for unknown model" not in ex.message():
                print("FAILED : get_model_metadata")
                print("Got: {}".format(ex.message()))
                sys.exit(1)
            else:
                print("FAILED : get_model_metadata")
                sys.exit(1)

        # Model configuration
        try:
            config = triton_client.get_model_config(FLAGS.model)
            if not (config.config.name == FLAGS.model):
                print("FAILED: get_model_config")
                sys.exit(1)
            print(config)
        except InferenceServerException as ex:
            print("FAILED : get_model_config")
            print("Got: {}".format(ex.message()))
            sys.exit(1)

  

    # IMAGE MODE
    if FLAGS.mode == 'image':
        print("Running in 'image' mode")
        if not FLAGS.input:
            print("FAILED: no input image")
            sys.exit(1)
        input_image = cv2.imread(str(FLAGS.input))
        if input_image is None:
            print(f"FAILED: could not load input image {str(FLAGS.input)}")
            sys.exit(1)
        # if FLAGS.model_info:
        #     statistics = triton_client.get_inference_statistics(model_name=FLAGS.model)
        #     if len(statistics.model_stats) != 1:
        #         print("FAILED: get_inference_statistics")
        #         sys.exit(1)
        #     print(statistics)
        print("Done")


        inputs = [grpcclient.InferInput("INPUT_DATA", (input_image.shape[0], input_image.shape[1], 3), "UINT8")]
        outputs = [grpcclient.InferRequestedOutput("OUTPUT_TEXT_AND_BOX")]

        inputs[0].set_data_from_numpy(input_image)
        results = triton_client.infer(model_name="nvOCDR", inputs=inputs, outputs=outputs)

        predict_text_box = results.as_numpy("OUTPUT_TEXT_AND_BOX")
        predict_text_box = list(map(lambda x: x[0].decode("utf-8"), predict_text_box))
        predict_text_box_decode = [json.loads(predict) for predict in predict_text_box]
        result = predict_text_box_decode[0]
        os.makedirs(os.path.join(os.path.dirname(__file__),"nvocdr_result"),exist_ok=True)
        # os.path.abspath("path")
        overlay_text_and_polygons(input_image,predictions=results,path=os.path.join("nvocdr_result",str(FLAGS.input)))


    if  FLAGS.mode == 'folder':
        print("Running in 'folder' mode")
        if not FLAGS.input:
            print("FAILED: no folder  input ")
            sys.exit(1)
        if os.path.exists(FLAGS.input):
            list_files = os.scandir(FLAGS.input)
        try :
            images_in_folder = [] 
            for file in list_files:
                if file.is_dir():
                    print(f"This is folder  :{file}\nPassing to another File")
                if file.is_file():
                    if file.path.endswith(".png") or file.path.endswith(".jpg") or file.path.endswith('.jpeg'):
                        print("Starting Inference over folder !!!!!!")
                        input_image = cv2.imread(file.path)
                        if input_image is None:
                            print(f"FAILED: could not load input image {str(FLAGS.input)}")
                            sys.exit(1)
                    #    if FLAGS.model_info:
                     #       statistics = triton_client.get_inference_statistics(model_name=FLAGS.model)
                      #      if len(statistics.model_stats) != 1:
                       #         print("FAILED: get_inference_statistics")
                       #         sys.exit(1)
                       #     print(statistics)
                        print("Done")


                        inputs = [grpcclient.InferInput("INPUT_DATA", (input_image.shape[0], input_image.shape[1], 3), "UINT8")]
                        outputs = [grpcclient.InferRequestedOutput("OUTPUT_TEXT_AND_BOX")]

                        inputs[0].set_data_from_numpy(input_image)
                        results = triton_client.infer(model_name="nvOCDR", inputs=inputs, outputs=outputs)
                        predict_text_box = results.as_numpy("OUTPUT_TEXT_AND_BOX")
                        predict_text_box = list(map(lambda x: x[0].decode("utf-8"), predict_text_box))
                        predict_text_box_decode = [json.loads(predict) for predict in predict_text_box]
                        results = predict_text_box_decode[0]
                        print(results)
                        for element in results:
                            print(colored(element['text'],'green'))
                        os.makedirs(os.path.join(os.path.dirname(file.path),"nvocdr_result"),exist_ok=True)
                        overlay_text_and_polygons(input_image,predictions=results,path=os.path.join(os.path.dirname(file.path),"nvocdr_result",file.name))

        except Exception as e :
            print(f"Error : {colored(e,'red')}")
