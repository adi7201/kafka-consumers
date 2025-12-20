#!/usr/bin/env python3

import os
import subprocess
import time
from datetime import datetime, timedelta
import logging

# ---------------- CONFIG ---------------- #
SOURCE_DIR = "/home/ai4m/develop/consumer/rhenus_backend_Script/dock_images"
DEST_USER = "ai4m"
DEST_IP = "100.73.37.34"
DEST_BASE_DIR = "/volume1/ai4m/Rhenus/Dock-images"
DAYS_OLD = 15

LOG_FILE = "/home/ai4m/develop/consumer/rhenus_backend_Script/upload_cleanup.log"
# ---------------------------------------- #

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def get_date_range_folder():
    today = datetime.now()
    start_date = today - timedelta(days=DAYS_OLD)

    return f"{start_date.strftime('%d%b').lower()}-{today.strftime('%d%b').lower()}"

def list_old_files(directory, days_old):
    cutoff_time = time.time() - (days_old * 86400)
    old_files = []

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.getmtime(file_path) < cutoff_time:
                old_files.append(file_path)

    return old_files

def upload_and_cleanup():
    old_files = list_old_files(SOURCE_DIR, DAYS_OLD)

    if not old_files:
        logging.info(f"No files older than {DAYS_OLD} days found.")
        return

    date_folder = get_date_range_folder()
    dest_dir = f"{DEST_BASE_DIR}/{date_folder}"
    dest = f"{DEST_USER}@{DEST_IP}:{dest_dir}"

    # Create destination folder
    try:
        subprocess.run(
            ["ssh", f"{DEST_USER}@{DEST_IP}", f"mkdir -p {dest_dir}"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to create destination folder: {e}")
        return

    # Rsync ONLY old files
    rsync_cmd = [
        "rsync",
        "-av",
        "--files-from=-",
        SOURCE_DIR + "/",
        dest
    ]

    file_list = "\n".join(
        os.path.relpath(f, SOURCE_DIR) for f in old_files
    )

    logging.info(f"Uploading {len(old_files)} files older than {DAYS_OLD} days")

    result = subprocess.run(
        rsync_cmd,
        input=file_list,
        text=True
    )

    if result.returncode != 0:
        logging.error("Upload failed. No files deleted.")
        return

    # Delete ONLY uploaded files
    deleted = 0
    for file_path in old_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted += 1
        except Exception as e:
            logging.error(f"Failed to delete {file_path}: {e}")

    logging.info(f"Successfully uploaded and deleted {deleted} files older than {DAYS_OLD} days.")
    logging.info("Folders preserved.")

if __name__ == "__main__":
    upload_and_cleanup()

