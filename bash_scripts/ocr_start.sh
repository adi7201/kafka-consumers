#!/bin/bash

# Path to your conda executable
CONDA_PATH="/home/nvidia/miniconda3/etc/profile.d/conda.sh"  # Adjust to your Conda installation path

# Name of the Conda environment to activate
CONDA_ENV="py310"

# First process to check and run
PROCESS1="trition_cctv_infer.py"
COMMAND1="python3 trition_cctv_infer.py >> /dev/null 2>&1 &"

# Second process to check and run
PROCESS2="s3_watcher.py"
COMMAND2="python3 s3_watcher.py >> /dev/null 2>&1 &"

# Initialize Conda
source $CONDA_PATH

# Check if Conda is initialized
if conda info &>/dev/null; then
    echo "Conda is initialized."
else
    echo "Conda is not initialized. Running 'conda init'..."
    conda init bash
    # Replace <your_shell> with your actual shell (e.g., bash, zsh)
    source ~/.bashrc  # Adjust accordingly if using a different shell
fi

# Activate the Conda environment
echo "Activating Conda environment: $CONDA_ENV"
conda activate $CONDA_ENV

# Function to check and run a process
check_and_run_process() {
    local PROCESS=$1
    local COMMAND=$2

    if pgrep -f "$PROCESS" > /dev/null; then
        echo "$PROCESS is already running."
    else
        echo "$PROCESS is not running. Starting $PROCESS..."

        # Run the command to start the process
        eval $COMMAND
        echo "$PROCESS started."
    fi
}

# Check and run the first process
check_and_run_process "$PROCESS1" "$COMMAND1"

# Check and run the second process
check_and_run_process "$PROCESS2" "$COMMAND2"

