#!/bin/bash

# Read the PID of the python process and kill it
if [ -f /tmp/vehicle_validation.pid ]; then
  PID=$(cat /tmp/vehicle_validation.pid)
  kill $PID
  rm /tmp/vehicle_validation.pid
fi
