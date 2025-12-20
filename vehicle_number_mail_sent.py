import psycopg2
import boto3
from datetime import datetime
from boto3.dynamodb.conditions import Key
import pytz
import json
import time
import os
import logging
import smtplib
from email.mime.text import MIMEText

SENDER_EMAIL = "aman@ai4mtech.com"
PASSWORD = "mgreprmdmdfdlaqc"

ses_client = boto3.client('ses', region_name='ap-south-1')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class SendMail:
    def __init__(self):
        with open('config.json', 'r') as file:
            self.data = json.load(file)
        self.connection = psycopg2.connect(
            **self.data['postgres']
        )
        self.cursor = self.connection.cursor()

        self.partition_key = 'rhenus#transaction#id'
        self.dynamodb = boto3.resource('dynamodb', **self.data['dynomodb'])
        table_name = 'rhenus_transaction'
        self.table = self.dynamodb.Table(table_name)

        todays_date = datetime.now().strftime("%Y-%m-%d")
        log_directory = os.path.join("logs", todays_date)
        os.makedirs(log_directory, exist_ok=True)
        log_filename = os.path.join(log_directory, f"{todays_date}_mail_sent.log")

        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        self.logger = logging.getLogger(__name__)
        self.logger.info("mailsend initialized")
        print("mailsent initialized")
        self.processed_vehicles = {}

    def send_email(self, vehicle_number, gate_in_time, customer_name, cycle_type,
                   recipient_email, transporter_name, origin_destination, driver_name, driver_contact):
        subject = "Vehicle Number Notification"
        cycle_type_lower = cycle_type.lower() if cycle_type else ""
        if cycle_type_lower == "inbound":
            od_line = f"Origin: {origin_destination}\n"
        elif cycle_type_lower == "outbound":
            od_line = f"Destination: {origin_destination}\n"
        else:
            od_line = ""
        body = f"""Vehicle Number: {vehicle_number}
Gate In Time: {gate_in_time}
Customer Name: {customer_name}
Cycle Type: {cycle_type}
Transporter Name: {transporter_name}
Driver Name: {driver_name}
Driver Contact: {driver_contact}
{od_line}"""
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email

        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, PASSWORD)
                server.send_message(msg)
                self.logger.info(f"Email sent to {recipient_email} for vehicle number {vehicle_number}")
        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")

    def log_email_sent(self, vehicle_number, timestamp):
        try:
            self.cursor.execute(
                "INSERT INTO email_sent_log (vehicle_number, timestamp, email_sent) VALUES (%s, %s, %s) "
                "ON CONFLICT (vehicle_number, timestamp) DO UPDATE SET email_sent = TRUE",
                (vehicle_number, timestamp, True)
            )
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Failed to log email sent: {str(e)}")

    def send_gate_out_email(self, vehicle_number, gate_in_time, gate_out_time, customer_name, cycle_type,
                            recipient_email, transporter_name, origin_destination, driver_name, driver_contact):
        subject = "Vehicle Gate Out Notification"
        cycle_type_lower = cycle_type.lower() if cycle_type else ""
        if cycle_type_lower == "inbound":
            od_line = f"Origin: {origin_destination}\n"
        elif cycle_type_lower == "outbound":
            od_line = f"Destination: {origin_destination}\n"
        else:
            od_line = ""
        body = f"""Vehicle Number: {vehicle_number}
Gate In Time: {gate_in_time}
Gate Out Time: {gate_out_time}
Customer Name: {customer_name}
Cycle Type: {cycle_type}
Transporter Name: {transporter_name}
Driver Name: {driver_name}
Driver Contact: {driver_contact}
{od_line}"""
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email

        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, PASSWORD)
                server.send_message(msg)
                self.logger.info(f"Gate out email sent to {recipient_email} for vehicle number {vehicle_number}")
        except Exception as e:
            self.logger.error(f"Failed to send gate out email: {str(e)}")

    def log_gate_out_email_sent(self, vehicle_number, timestamp):
        try:
            self.cursor.execute(
                "INSERT INTO gate_out_email_sent_log (vehicle_number, timestamp, email_sent) VALUES (%s, %s, %s) "
                "ON CONFLICT (vehicle_number, timestamp) DO UPDATE SET email_sent = TRUE",
                (vehicle_number, timestamp, True)
            )
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Failed to log gate out email sent: {str(e)}")

    def send_vehicle_number(self):
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.combine(datetime.now().date(), datetime.min.time())
            end_date = datetime.combine(datetime.now().date(), datetime.max.time())
            items = []
            response = self.table.query(
                KeyConditionExpression=Key('transcation_id').eq(self.partition_key) &
                                      Key('timestamp').between(start_date.isoformat(), end_date.isoformat())
            )
            items.extend(response['Items'])

            for item in items:
                vehicle_number = item.get('vehicle_number')
                gate_in_time = item.get('gate_in_time')
                gate_out_time = item.get('gate_out_time')
                timestamp = item.get('timestamp')
                cycle_type = item.get('transaction_type')
                transporter_name = item.get('transporterName', 'N/A')
                origin_destination = item.get('origin_destination')
                driver_name = item.get('driverName', 'N/A')
                driver_contact = item.get('driverContact', 'N/A')

                # customerName may come as list
                customer_names = item.get('customerName', [])
                if isinstance(customer_names, str):
                    customer_names = [customer_names]

                vehicle_key = (vehicle_number, timestamp)

                # Check if gate in email was sent
                self.cursor.execute(
                    "SELECT email_sent FROM email_sent_log WHERE vehicle_number = %s AND timestamp = %s",
                    (vehicle_number, timestamp)
                )
                result = self.cursor.fetchone()

                if not result or not result[0]:
                    for customer_name in customer_names:
                        if customer_name in self.data['customer_emails']:
                            recipient_emails = self.data['customer_emails'][customer_name]
                            for recipient_email in recipient_emails:
                                self.send_email(
                                    vehicle_number, gate_in_time, customer_name, cycle_type,
                                    recipient_email, transporter_name, origin_destination,
                                    driver_name, driver_contact
                                )
                            self.log_email_sent(vehicle_number, timestamp)
                        else:
                            self.logger.warning(f"No email configuration found for customer: {customer_name}")

                # Check if gate out email was sent
                if gate_out_time:
                    self.cursor.execute(
                        "SELECT email_sent FROM gate_out_email_sent_log WHERE vehicle_number = %s AND timestamp = %s",
                        (vehicle_number, timestamp)
                    )
                    gate_out_result = self.cursor.fetchone()

                    if not gate_out_result or not gate_out_result[0]:
                        for customer_name in customer_names:
                            if customer_name in self.data['customer_emails']:
                                recipient_emails = self.data['customer_emails'][customer_name]
                                for recipient_email in recipient_emails:
                                    self.send_gate_out_email(
                                        vehicle_number, gate_in_time, gate_out_time, customer_name, cycle_type,
                                        recipient_email, transporter_name, origin_destination,
                                        driver_name, driver_contact
                                    )
                                self.log_gate_out_email_sent(vehicle_number, timestamp)
                            else:
                                self.logger.warning(f"No email configuration found for customer: {customer_name}")

        except Exception as e:
            self.logger.error(f"Error sending vehicle number: {str(e)}")


if __name__ == "__main__":
    sendmail = SendMail()
    while True:
        sendmail.send_vehicle_number()
        time.sleep(1)

