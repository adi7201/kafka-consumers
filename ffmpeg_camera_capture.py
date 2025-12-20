import os
import subprocess
import time
import psycopg2
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# List of RTSP links
rtsp_links = [
    "rtsp://admin:Cebex%40123@192.168.2.43/media/video1",
    "rtsp://admin:admin%40123@192.168.2.44/media/video1",
    "rtsp://admin:admin%40123@192.168.2.45/media/video1",
    "rtsp://admin:admin%40123@192.168.2.46/media/video1",
    "rtsp://admin:admin%40123@192.168.2.47/media/video1",
    "rtsp://admin:admin%40123@192.168.2.48/media/video1",
    "rtsp://admin:admin%40123@192.168.2.49/media/video1",
    "rtsp://admin:admin%40123@192.168.2.50/media/video1",
    "rtsp://admin:admin%40123@192.168.2.51/media/video1",
    "rtsp://admin:admin%40123@192.168.2.52/media/video1",
    "rtsp://admin:admin%40123@192.168.2.53/media/video1",
    "rtsp://admin:admin%40123@192.168.2.54/media/video1",
    "rtsp://admin:admin%40123@192.168.2.55/media/video1",
    "rtsp://admin:admin%40123@192.168.2.56/media/video1",
    "rtsp://admin:admin%40123@192.168.2.57/media/video1",
    "rtsp://admin:admin%40123@192.168.2.58/media/video1",
    "rtsp://admin:admin%40123@192.168.2.59/media/video1",
    "rtsp://admin:admin%40123@192.168.2.60/media/video1",
    "rtsp://admin:admin%40123@192.168.2.61/media/video1",
    "rtsp://admin:admin%40123@192.168.2.62/media/video1"
    
]

# Base folder for storing images
base_folder = "dock_images"
os.makedirs(base_folder, exist_ok=True)

LOGO_PATH = "rhenuswatermark.png"
SITE_NAME = "(MUF-23)"  

# Database connection parameters
DB_PARAMS = {
    'database': 'rhenus',
    'user': 'postgres',
    'password': 'rhenus',
    'host': 'localhost'
}

# Establish database connection
try:
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()
    print("Connected to the database successfully!")
except Exception as e:
    print(f"Database connection failed: {e}")
    exit()


while True:
    for i, rtsp_link in enumerate(rtsp_links):
        dock_name = f"dock{i+1}"
        folder_name = os.path.join(base_folder, dock_name)
        os.makedirs(folder_name, exist_ok=True)  

   
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

       
        image_path = os.path.join(folder_name, f"{timestamp}.jpg")

        command = [
            "ffmpeg", "-y", "-loglevel", "fatal", "-rtsp_transport", "tcp", "-i", rtsp_link,
            "-frames:v", "1", image_path
        ]
        
        try:
            subprocess.run(command, check=True)
            print(f"Captured image from Dock {i+1} and saved to {image_path}")

          
            try:
               
                main_image = Image.open(image_path)
                
              
                logo = Image.open(LOGO_PATH)
                
                logo_width = int(main_image.width * 0.07)  
                logo_height = int(logo_width * logo.height / logo.width)
                logo = logo.resize((logo_width, logo_height))
                
               
                draw = ImageDraw.Draw(main_image)
                
                text_size = int(main_image.width * 0.03) 
                try:
                   
                    font = ImageFont.truetype("arialbd.ttf", text_size)
                except:
                    try:
                        font = ImageFont.truetype("arial.ttf", text_size)
                    except:
                        font = ImageFont.load_default()
                
               
                text_bbox = draw.textbbox((0, 0), SITE_NAME, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
               
                padding = 15  
                gap = 3 
                margin_bottom = -40
                
                # Position logo in bottom right
                logo_position = (
                    main_image.width - logo_width - padding,
                    main_image.height - logo_height - padding
                )
                
                # Position text below the logo with negative margin
                text_position = (
                    logo_position[0] + (logo_width - text_width) // 2, 
                    logo_position[1] + logo_height + gap + margin_bottom  
                )
                
                # Paste logo onto main image
                main_image.paste(logo, logo_position, logo if logo.mode == 'RGBA' else None)
                
               
                shadow_offset = 1
                draw.text((text_position[0] + shadow_offset, text_position[1] + shadow_offset), 
                         SITE_NAME, font=font, fill='black')
                
                # Add white text on top
                draw.text(text_position, SITE_NAME, font=font, fill='white')
                
               
                main_image.save(image_path)
                # print(f"Added logo and site name '{SITE_NAME}' to image from Dock {i+1}")
                
            except Exception as logo_err:
                print(f"Failed to add logo and site name to image: {logo_err}")

            # Insert into database
            try:
                cursor.execute(
                    "INSERT INTO dock_images(timestamp, dock, image) VALUES (NOW(), %s, %s)",
                    (dock_name, image_path)
                )
                conn.commit()
                print(f"Inserted image record for Dock {i+1} into database.")
            except Exception as db_err:
                print(f"Failed to insert image record into database: {db_err}")

        except subprocess.CalledProcessError as e:
            print(f"Failed to capture image from Dock {i+1}: {e}")

    print("Waiting for 30 seconds before next capture...")
    time.sleep(30)  

cursor.close()
conn.close()
