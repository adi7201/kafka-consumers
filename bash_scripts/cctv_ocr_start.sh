#!/bin/bash

# Path to your conda executable
CONDA_PATH="/home/nvidia/miniconda3/etc/profile.d/conda.sh"  # Adjust to your Conda installation path

# Name of the Conda environment to activate
CONDA_ENV="py310"

# Name of the process to check
PROCESS="trition_cctv_infer.py"

# Command to run the process if it's not running
COMMAND="python3 trition_cctv_infer.py >> /dev/null 2>&1 &"

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

# Check if the process is running
if pgrep -f "$PROCESS" > /dev/null; then
    echo "$PROCESS is already running."
else
    echo "$PROCESS is not running. Starting $PROCESS..."

    # Run the command to start the process
    eval $COMMAND
    echo "$PROCESS started."
fi

