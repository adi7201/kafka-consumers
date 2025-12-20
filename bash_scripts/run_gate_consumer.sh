#!/bin/bash

restart_if_not_running() {
    SCRIPT_NAME=$1
    if ! pgrep -f "$SCRIPT_NAME" > /dev/null; then
        echo "Restarting $SCRIPT_NAME..."
        python3 /home/ai4m/develop/consumer/rhenus_backend_Script/$SCRIPT_NAME &
    fi
}

while true; do
	restart_if_not_running "gate_testing_consumer.py"
    	restart_if_not_running "postgres_to_dynamodb.py"
    	restart_if_not_running "tab-image-ocr.py"
        restart_if_not_running "tab_ocr_to_dynamodb.py"
	restart_if_not_running "truck_image_upload_s3.py"

	sleep 10
done

### Script 1 - Gate  Consumer 
#python3 /home/ai4m/develop/consumer/rhenus_backend_Script/gate_testing_consumer.py & 
### Script 2 - Postgres 2 Dynamodb 
#python3 /home/ai4m/develop/consumer/rhenus_backend_Script/postgres_to_dynamodb.py & 
### Script 3 - Tab- OCR 
#python3 /home/ai4m/develop/consumer/rhenus_backend_Script/tab-image-ocr.py &
###### Script 4 - Tab OCR 2 Dynamo 
#python3 /home/ai4m/develop/consumer/rhenus_backend_Script/tab_ocr_to_dynamodb.py & 
####### Script 5 - IMage upload 2 s3 
#python3 /home/ai4m/develop/consumer/rhenus_backend_Script/truck_image_upload_s3.py &

#wait
