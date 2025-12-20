#!/bin/bash
SERVICE="gate_testing_consumer.py"


if pgrep -f "$SERVICE"
then
    echo "$(date): $SERVICE is running"
else
    echo "$(date): $SERVICE stopped" 
    sleep 1s
    cd /home/ai4m/develop/consumer/rhenus_backend_Script/Testing_Consumer/
    python3 gate_testing_consumer.py >> /dev/null 2>&1 &
    echo "$(date): $SERVICE restarted" 
fi

