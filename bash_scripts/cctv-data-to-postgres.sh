#!/bin/bash
cd /home/nvidia/rhenus_script/
/usr/local/bin/python3 postgres_to_dynmodb.py >> /dev/null 2>&1 &
