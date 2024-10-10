import sib_api_v3_sdk
from api import app
from dotenv import load_dotenv
import os

load_dotenv()

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key["api-key"] = os.environ["SENDINBLUE_API_KEY"]
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

def send_submitted_application(fullName, email, employeeName, startDate, endDate, duration):
    subject = f"Leave application submission - {employeeName}"
    sender = {"name": app.app.config["SENDER_NAME"], "email": app.app.config["SENDER_EMAIL"]}
    email_content = f"""
        <p>Dear {fullName}</p>

        <p>Kindly note that {employeeName} has submitted a new leave application with the following details: </p>
        <ul>
            <li><b>Start Date: {startDate}</b></li>
            <li><b>End Date: {endDate}</b></li>
            <li><b>Leave Duration: {duration} day</b></li>
        </ul>

        <p>Kindly <a href="https://mobikey-lms.vercel.app/">log in</a> and review the application</p>

        <b>NB: This is a system generated email. Please DO NOT reply to this email thread.</b>
    """

    to = [{"name": fullName, "email": email}]
    send_email = sib_api_v3_sdk.SendSmtpEmail(to=to, html_content=email_content, sender=sender, subject=subject)

    try:
        # Attempt to send the email
        api_instance.send_transac_email(send_email)

    except sib_api_v3_sdk.rest.ApiException as e:
        # Catch any API-related errors and print/log the error details
        print(f"Error sending email to {email}: {e}")
        return {"error": "An unexpected error occurred. Please try again later!"}
    except Exception as e:
        # Catch any other errors that may occur
        print(f"Unexpected error: {e}")
        return {"error": "An unexpected error occurred. Please try again later!"}
