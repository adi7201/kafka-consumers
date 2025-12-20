import psycopg2
import boto3
import select
import logging
import os
# Configure logging
logging.basicConfig(
    filename='upload_log.txt', 
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'  # Log message format
)

def upload_file_to_s3(file_name, bucket, object_name=None, unique_id=None):
    if object_name is None:
        object_name = os.path.basename(file_name)
    
    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
        print(f'Successfully uploaded {file_name} to {bucket}/{object_name}')
        logging.info(f'Successfully uploaded {file_name} to {bucket}/{object_name}')
        
        # Update the upload_to_s3 status to True
        if unique_id:
            update_upload_status(unique_id, True)
        return True
    except FileNotFoundError:
        print(f'The file {file_name} was not found.')
        logging.error(f'The file {file_name} was not found.')
        return False
    except boto3.exceptions.S3UploadFailedError as e:
        print(f'S3 upload failed: {e}')
        logging.error(f'S3 upload failed: {e}')
        return False
    except Exception as e:
        print(f'Error uploading file {file_name} to {bucket}/{object_name}: {e}')
        logging.error(f'Error uploading file {file_name} to {bucket}/{object_name}: {e}')
        return False

def update_upload_status(unique_id, status):
    try:
        conn = psycopg2.connect("dbname=rhenus user=postgres password=ai4m2024 host=localhost port=5432")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rhenus_events SET upload_to_s3 = %s WHERE unique_id = %s",
            (status, unique_id)
        )
        conn.commit()
        print(f"Updated upload status to {status} for unique_id: {unique_id}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error updating upload status: {e}")
        logging.error(f"Error updating upload status: {e}")

def retry_failed_uploads():
    try:
        conn = psycopg2.connect("dbname=rhenus user=postgres password=ai4m2024 host=localhost port=5432")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, unique_id FROM rhenus_events WHERE upload_to_s3 = FALSE"
        )
        failed_uploads = cursor.fetchall()
        
        print(f"Found {len(failed_uploads)} failed uploads to retry")
        for file_to_upload, unique_id in failed_uploads:
            print(f'Retrying upload for file: {file_to_upload}')
            logging.info(f'Retrying upload for file: {file_to_upload}')
            upload_file_to_s3(file_to_upload, 'rhenus-truck-images', unique_id=unique_id)
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error in retry_failed_uploads: {e}")
        logging.error(f"Error in retry_failed_uploads: {e}")

def listen_for_uploads():
    # Connect to PostgreSQL
    conn = psycopg2.connect("dbname=rhenus user=postgres password=rhenus host=localhost port=5432")
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    
    # Create a cursor
    cursor = conn.cursor()
    
    # Listen for notifications on the upload_channel
    cursor.execute("LISTEN upload_channel;")
    print("Listening for notifications on 'upload_channel'...")
    logging.info("Listening for notifications on 'upload_channel'...")

    # First, retry any failed uploads
    retry_failed_uploads()

    while True:
        if select.select([conn], [], [], 5) == []:
            # Timeout after 5 seconds
            print("Waiting for notifications...")
            logging.info("Waiting for notifications...")
            # Periodically retry failed uploads
            retry_failed_uploads()
        else:
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                payload = notify.payload.split(',')
                file_to_upload = payload[0]
                unique_id = payload[1] if len(payload) > 1 else None
                print(f'Received notification to upload: {file_to_upload}')
                logging.info(f'Received notification to upload: {file_to_upload}')
                upload_file_to_s3(file_to_upload, 'rhenus-truck-images', unique_id=unique_id)

# Call the listener function
listen_for_uploads()
