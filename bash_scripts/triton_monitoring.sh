#!/bin/bash

# Variables
TRITON_DIR="/home/nvidia/develop/nvocdr/ocdr/triton"
TRITON_CMD="tritonserver --model-repository=$TRITON_DIR/models"
SESSION_NAME="triton"
ERROR_MSG="Non-graceful termination detected"

# Function to start Triton in the tmux session
start_triton() {
    echo "Starting Triton in directory: $TRITON_DIR"
    tmux send-keys -t "$SESSION_NAME" "cd $TRITON_DIR && $TRITON_CMD" C-m
}

# Check if the tmux session exists; if not, create it and start Triton
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux new-session -d -s "$SESSION_NAME" -c "$TRITON_DIR"
    start_triton
fi

# Periodically check if Triton is running and handle errors
while true; do
    # Check for the specific error message in the tmux session
    if tmux capture-pane -pt "$SESSION_NAME" | grep -q "$ERROR_MSG"; then
        echo "Error detected. Restarting Triton..."
        tmux send-keys -t "$SESSION_NAME" C-c  # Send Ctrl+C to stop Triton
        sleep 2  # Allow time for Triton to stop
        start_triton
    fi

    # Check if the Triton process is running
    if ! tmux list-panes -t "$SESSION_NAME" | grep -q "active"; then
        echo "Triton process stopped unexpectedly. Restarting..."
        start_triton
    fi

    # Wait for 2 seconds before checking again
    sleep 2  
done

