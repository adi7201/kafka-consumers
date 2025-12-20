#!/bin/bash
SERVICE="truck_image_upload_s3.py"

if pgrep -f "$SERVICE"
then
    echo "$(date): $SERVICE is running"
else
    echo "$(date): $SERVICE stopped" 
    sleep 1s
    cd /home/nvidia/rhenus_backend_Script
    python3 truck_image_upload_s3.py >> /dev/null 2>&1 &
    echo "$(date): $SERVICE restarted" 
fi
