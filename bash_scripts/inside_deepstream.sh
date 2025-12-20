#!/bin/bash
cd /home/nvidia/inside
sleep 30s
deepstream-test5-app -c inside_app_config_with_sgie.txt -t >> /dev/null 2>&1 &
