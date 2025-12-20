#!/bin/bash -x
cd /home/nvidia/rhenus_script
export PYTHONPATH=/home/nvidia/.local/lib/python3.10/site-packages

/usr/local/bin/python3.10 Vaenable_monitoring.py >> /dev/null 2>&1 &


