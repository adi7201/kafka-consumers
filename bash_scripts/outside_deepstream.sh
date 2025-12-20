#!/bin/bash
cd /home/nvidia/outside
sleep 30s
ai4m-rhenus-app -c deepstream_app_config.txt -t >> /dev/null 2>&1 &
