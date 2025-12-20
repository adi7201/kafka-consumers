
#!/bin/bash 

# Start Triton Inference Server
#tritonserver --model-repository=/home/nvidia/develop/nvocdr/ocdr/triton/models 
# Get the PID of the Triton server process
#TRITON_PID=$(ps -aux| pgrep 'tritonserver')
#echo $TRITON_PID
# Check if Triton is running
#while true; do
    # Wait for a few seconds before checking again

#sleep 1
# Check if the Triton server is still running
#if ps -p $TRITON_PID > /dev/null; then
 #  echo "Triton server is running..."

#else
#   echo "Triton server has stopped."        # Optionally, restart the server or take any other action here
#   tritonserver --model-repository=/home/nvidia/develop/nvocdr/ocdr/triton/models
#   break
#fi
#done
#!/bin/bash

if pgrep -f "tritonserver" > /dev/null; then
    echo "Triton server is already running."
    exit 0
fi

echo "Starting Triton server..."
tritonserver --model-repository=/home/nvidia/develop/nvocdr/ocdr/triton/models &

