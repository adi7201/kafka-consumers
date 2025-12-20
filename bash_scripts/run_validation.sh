#!/bin/bash

# Absolute path to your Python
PYTHON=/usr/bin/python3

# Absolute path to your script
SCRIPT=/home/ai4m/develop/consumer/rhenus_backend_Script/vehicle_number_validation.py

# Run your python script in background and save its PID
$PYTHON $SCRIPT &
echo $! > /tmp/vehicle_validation.pid
