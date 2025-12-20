#!/bin/bash
SERVICE="opencv_image_capture.py"
#LOGFILE="/home/nvidia/outside_deepstream.log"
TMUX_SESSION="opencv_image_capture"
if pgrep -f "$SERVICE"
then
    echo "$(date): $SERVICE is running"
else
    echo "$(date): $SERVICE stopped"  
    sleep 1s
    cd /home/nvidia/rhenus_script

    if ! tmux has-session -t $TMUX_SESSION 2>/dev/null; then
        tmux new-session -d -s $TMUX_SESSION
    fi

    tmux send-keys -t $TMUX_SESSION "python3 opencv_image_capture.py" C-m
    echo "$(date): $SERVICE restarted in tmux session $TMUX_SESSION"
fi

