#!/bin/bash
SERVICE="deepstream-test5-app"
if  pgrep -f "$SERVICE" 
then
    echo "$SERVICE is running"
else
    echo "$SERVICE stopped"
    /bin/bash /home/nvidia/rhenus_backend_Script/bash_scripts/inside_deepstream.sh  
fi
