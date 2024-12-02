import json
import time
from awsiot import mqtt_connection_builder
from awscrt.mqtt import QoS
import boto3
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to logging.INFO to reduce verbosity
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to console
    ]
)

# AWS IoT Configurations
ENDPOINT = "a160f6zy571fi7-ats.iot.us-east-1.amazonaws.com"  # Replace with your AWS IoT Core endpoint
CLIENT_ID = "IoT_Dummy_OTA"
PATH_TO_CERT = "IoT-Dummy-OTA-certificate.pem.crt"
PATH_TO_KEY = "IoT-Dummy-OTA-private.pem.key"
PATH_TO_ROOT = "IoT-Dummy-OTA-AmazonRootCA1.pem"
JOBS_TOPIC = "$aws/things/{}/jobs/notify-next".format(CLIENT_ID)

# Function to parse and download firmware from S3
def download_firmware(s3_url):
    logging.info(f"Attempting firmware download from {s3_url}")
    try:
        bucket_name, object_key = parse_s3_url(s3_url)
        logging.debug(f"Parsed S3 URL - Bucket: {bucket_name}, Key: {object_key}")
        s3_client = boto3.client("s3")
        local_filename = object_key.split("/")[-1]
        s3_client.download_file(bucket_name, object_key, local_filename)
        logging.info(f"Firmware successfully downloaded and saved as {local_filename}")
    except Exception as e:
        logging.error(f"Error during firmware download: {e}", exc_info=True)

def parse_s3_url(url):
    """Parses the S3 URL into bucket name and object key."""
    try:
        url_parts = url.replace("https://", "").split("/", 1)
        bucket_name = url_parts[0].split(".")[0]
        object_key = url_parts[1]
        return bucket_name, object_key
    except Exception as e:
        logging.error(f"Failed to parse S3 URL: {url}. Error: {e}", exc_info=True)
        raise

def on_message_received(topic, payload, **kwargs):
    """Callback function for incoming job notifications."""
    logging.info(f"Received message on topic {topic}: {payload}")
    try:
        message = json.loads(payload)
        logging.debug(f"Decoded message: {message}")

        # Check if the message contains the expected structure
        if "execution" in message and "jobDocument" in message["execution"]:
            job_document = message["execution"]["jobDocument"]
            if "operation" in job_document and job_document["operation"] == "download":
                logging.info("Detected download operation. Initiating firmware download.")
                download_firmware(job_document["s3Url"])
            else:
                logging.warning(f"Unexpected operation or missing operation field in jobDocument: {job_document}")
        else:
            logging.warning(f"Message does not contain expected structure: {message}")
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding message payload: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Unexpected error during message handling: {e}", exc_info=True)

# Build MQTT Connection
try:
    logging.info("Building MQTT connection...")
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=ENDPOINT,
        cert_filepath=PATH_TO_CERT,
        pri_key_filepath=PATH_TO_KEY,
        ca_filepath=PATH_TO_ROOT,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=6,
    )
    logging.info("MQTT connection built successfully.")
except Exception as e:
    logging.error(f"Failed to build MQTT connection: {e}", exc_info=True)
    raise

# Connect to AWS IoT Core
try:
    logging.info("Connecting to AWS IoT Core...")
    connect_future = mqtt_connection.connect()
    connect_future.result()
    logging.info("Successfully connected to AWS IoT Core.")
except Exception as e:
    logging.error(f"Failed to connect to AWS IoT Core: {e}", exc_info=True)
    raise

# Subscribe to IoT Job notifications
try:
    logging.info("Subscribing to job notifications...")
    subscribe_future, _ = mqtt_connection.subscribe(
        topic=JOBS_TOPIC,
        qos=QoS.AT_LEAST_ONCE,  # Use the QoS enum explicitly
        callback=on_message_received,
    )
    subscribe_future.result()
    logging.info(f"Successfully subscribed to topic: {JOBS_TOPIC}")
except Exception as e:
    logging.error(f"Failed to subscribe to topic: {JOBS_TOPIC}. Error: {e}", exc_info=True)
    raise

# Keep the script running to listen for OTA updates
try:
    logging.info("Listening for OTA updates...")
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    logging.info("Script interrupted by user. Exiting...")
except Exception as e:
    logging.error(f"Unexpected error in main loop: {e}", exc_info=True)
