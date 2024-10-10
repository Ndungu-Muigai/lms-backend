import sib_api_v3_sdk
from api import app
from dotenv import load_dotenv
import os

load_dotenv()

configuration=sib_api_v3_sdk.Configuration()
configuration.api_key["api-key"] = os.environ["SENDINBLUE_API_KEY"]
api_instance=sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

def send_approved_leave(employeeEmail, employeeName, startDate, endDate, duration):
    subject="Leave approval"
    sender={"name": app.app.config["SENDER_NAME"], "email": app.app.config["SENDER_EMAIL"]}
    email_content = f"""
        <p>Dear {employeeName}</p>

        <p>Kindly note that your leave application with the following details has been approved: </p>
        <ul>
            <li><b>Start Date: {startDate}</b></li>
            <li><b>End Date: {endDate}</b></li>
            <li><b>Leave Duration: {duration}</b></li>
        </ul>

        <p>Enjoy your break and we look forward to seeing you on {endDate + 1} &#128522;</p>
        <b>NB: This is a system generated email. Please DO NOT reply to this email thread.</b>
    """

    to = [{"name": employeeName, "email": employeeEmail}]
    send_email = sib_api_v3_sdk.SendSmtpEmail(to=to, html_content=email_content, sender=sender, subject=subject)

    try:
        # Attempt to send the email
        api_instance.send_transac_email(send_email)
        print(f"Email successfully sent to {employeeEmail}")

    except sib_api_v3_sdk.rest.ApiException as e:
        # Catch any API-related errors and print/log the error details
        print(f"Error sending email to {employeeEmail}: {e}")
        return {"error": "Failed to send email. Please try again later."}
    except Exception as e:
        # Catch any other errors that may occur
        print(f"Unexpected error: {e}")
        return {"error": "An unexpected error occurred while sending the email."}
