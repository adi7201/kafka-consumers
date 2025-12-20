#!/bin/bash
SERVICE="ffmpeg_camera_capture.py"


if pgrep -f "$SERVICE"
then
    echo "$(date): $SERVICE is running"
else
    echo "$(date): $SERVICE stopped" 
    sleep 1s
    cd /home/nvidia/rhenus_backend_Script
    python3 ffmpeg_camera_capture.py >> /dev/null 2>&1 &
    echo "$(date): $SERVICE restarted" 
fi
