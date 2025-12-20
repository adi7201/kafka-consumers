#!/bin/bash
cd /home/nvidia/rhenus_script/
/usr/local/bin/python3 truck_image_upload_s3.py >> /dev/null 2>&1 &
