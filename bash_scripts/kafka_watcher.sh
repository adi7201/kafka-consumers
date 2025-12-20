#!/bin/bash

#while true; do
    status=$(systemctl is-active kafka)
    if [ $status != "active" ]; then
        echo -e "nvidia" | sudo -S systemctl restart kafka
        echo "kafka service is restarted"
    else
        echo "kafka service is running"
    fi
#done

#python3 test_ram.py
