


def rerun_ocr(filepath, msg_coordinates) -> str:
        try:
            logger.debug(f"Running OCR on {filepath} with coordinates {msg_coordinates}")
            base_path = os.path.basename(filepath)
            x_min, y_min, x_max, y_max = msg_coordinates
            logger.debug(f"OCR coords: {msg_coordinates}")
            print(f"OCR coords: {msg_coordinates}")
            x_min, y_min, x_max, y_max = float(x_min), float(y_min), float(x_max), float(y_max)
            
            base_image = cv2.imread(filepath)
            logger.debug(f"Base image shape: {base_image.shape}")
            print(base_image.shape)
            
            if base_image is not None:
                print(x_min, y_min, x_max, y_max)
                cropped_image = base_image[int(y_min) : int(y_max), int(x_min) : int(x_max),]
                logger.debug(f"Cropped image shape: {cropped_image.shape}")
                print("Cropped size ", cropped_image.shape)
                
                file = os.path.basename(filepath)
                os.makedirs("OG_images", exist_ok=True)
                cv2.imwrite(f"OG_images/cropped_{file}", cropped_image)
                
                # padded_image = self.pad_and_resize_image(cropped_image,x_min, y_min, x_max, y_max)
                padded_image = self.pad_and_resize_image(base_image,x_min, y_min, x_max, y_max)
                output_folder = "Triton_input_image"
                os.makedirs(output_folder, exist_ok=True)
                output_filename = (f"{os.path.splitext(base_path)[0]}_cropped.jpg")
                output_path = os.path.join(output_folder, output_filename)
                cv2.imwrite(output_path, padded_image)
                
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