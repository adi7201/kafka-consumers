#!/bin/bash

restart_if_not_running() {
    SCRIPT_NAME=$1
    if ! pgrep -f "$SCRIPT_NAME" > /dev/null; then
        echo "Restarting $SCRIPT_NAME..."
        python3 /home/ai4m/develop/consumer/rhenus_backend_Script/$SCRIPT_NAME &
    fi
}

while true; do
   
        restart_if_not_running "dock_transaction_test.py"
        restart_if_not_running "dock_consumer.py"
        restart_if_not_running "dock_cycle.py"
        restart_if_not_running "ffmpeg_camera_capture.py"
        restart_if_not_running "upload_image_to_s3.py"
        restart_if_not_running "insert_dock_assign_cycle_log.py"
        restart_if_not_running "inbound_test.py"
        restart_if_not_running "outbound_test.py"
        restart_if_not_running "dock_bucketing.py"
        restart_if_not_running "vehicle_number_mail_sent.py"
        restart_if_not_running "system-monitoring.py"
   

    sleep 10
done

 

