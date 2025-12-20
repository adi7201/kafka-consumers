#!/bin/bash
SERVICE="ai4m-rhenus-app"
if  pgrep -f "$SERVICE" 
then
    echo "$SERVICE is running"
else
    echo "$SERVICE stopped"
    # uncomment to start nginx if stopped
    # systemctl start nginx
    # mail
    /bin/bash /home/nvidia/rhenus_backend_Script/bash_scripts/outside_deepstream.sh  
fi
