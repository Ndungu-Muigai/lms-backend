import sib_api_v3_sdk
from api import app
from dotenv import load_dotenv
import os

load_dotenv()

configuration=sib_api_v3_sdk.Configuration()
configuration.api_key["api-key"] = os.environ["SENDINBLUE_API_KEY"]
api_instance=sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

def send_otp(email, otp, first_name, last_name):
    subject="One Time Password"
    sender={"name": app.app.config["SENDER_NAME"], "email": app.app.config["SENDER_EMAIL"]}

    content=f"""
    <p style="color: black;">Greetings {first_name} {last_name},</p>
    <p style="color: black;">Your One-Time Password (OTP) is: <b>{otp}</b></p>
    <b style="color: black;">This OTP expires after 15minutes. Kindly use it before then.</b>
    <p style="color: black;">Please use this OTP to reset your account password</p>
    <b style="color: black;">If this request was not initiated by you, please <a href='https://mobikey-lms.vercel.app/password-reset/new-request' target='_blank'>update your password</a> immediately to protect your account</b>
	"""
    to= [{"name": f"{first_name} {last_name}", "email": email}]
    send_email=sib_api_v3_sdk.SendSmtpEmail(to=to, html_content=content,sender=sender, subject=subject)

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