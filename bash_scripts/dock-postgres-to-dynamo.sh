
#!/bin/bash
SERVICE="dock_postgres_to_dynomodb.py"


if pgrep -f "$SERVICE"
then
    echo "$(date): $SERVICE is running"
else
    echo "$(date): $SERVICE stopped" 
    sleep 1s
    cd /home/nvidia/rhenus_backend_Script
    python3 dock_postgres_to_dynomodb.py >> /dev/null 2>&1 &
    echo "$(date): $SERVICE restarted" 
fi
