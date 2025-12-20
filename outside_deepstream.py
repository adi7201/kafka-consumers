import subprocess
                                                                                                                                                                                                                 # Path to your bash script
bash_script = './outside_deepstream.sh'                                                                                                                                                                           
# Run the bash script using subprocess
try:
    result = subprocess.run(['bash', bash_script], check=True, text=True, capture_output=True)
    print("Script output:\n", result.stdout)
except subprocess.CalledProcessError as e:
    print(f"Error occurred: {e.stderr}")                                                                                                                                                                                                                    
