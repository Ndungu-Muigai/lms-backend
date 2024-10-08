from flask import Flask, make_response, request, jsonify, session, send_file, url_for
from flask_session import Session
from flask_migrate import Migrate
from flask_cors import CORS
from api.models import db, Employee, LeaveDays, LeaveApplication, OneTimePassword   
from flask_restful import Api, Resource
from schema import EmployeeSchema, LeaveDaysSchema, LeaveApplicationsSchema
import hashlib
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
import uuid
import os
from Mail.credentials import send_login_credentials
from Mail.reset import send_otp
from Mail.submitted import send_submitted_application
from Mail.approved import send_approved_leave
from Generations.password import random_password
from Generations.otp import get_otp
import redis
import boto3
import io
import json
from api.Update import update_leave_days

app = Flask(__name__)

# Configuring redis
r = redis.from_url("rediss://red-cs2f4956l47c73bgt4c0:vfHKfN8YalQnHnhGXV01tooGpCe8ugtf@oregon-redis.render.com:6379")
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["SESSION_TYPE"] = "redis"
app.config['SESSION_REDIS'] = r
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Configuring the database
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = False
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")

# Email sender configuration
app.config["SENDER_NAME"] = "Leave Management System"
app.config["SENDER_EMAIL"] = "lms@mobikey.co.ke"
app.static_folder = 'static'

# AWS S3 configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")

s3 = boto3.client("s3", region_name=S3_REGION, aws_access_key_id=S3_ACCESS_KEY, aws_secret_access_key=S3_SECRET_ACCESS_KEY)

# Initializing the migration
migrate = Migrate(app, db)
db.init_app(app)

CORS(app, origins=["http://localhost:3000", "https://mobikey-lms.vercel.app"])

Session(app)
# Wrapping the app as an API instance
api = Api(app)

#Function to extract session data
def get_session_data():
    session_id=request.headers.get("X-Session-ID")

    session_data=r.get(f"session:{session_id}")

    if not session_data:
        return make_response(jsonify({"error": "Kindly login to continue"}))

    return json.loads(session_data) 

# Index resource
class Index(Resource):
    def get(self):
        return make_response(jsonify({"message": "Welcome to the Mobikey LMS backend"}))

api.add_resource(Index, "/")

# Login resource
class Login(Resource):
    def post(self):
        # Getting the information from the form
        username = request.json["username"].lower()  # Converting username to lower case
        password = request.json["password"]

        # Querying the database to check if the employee exists based on the username
        employee = Employee.query.filter_by(username=username).first()

        # If the username doesn't exist, return an error
        if not employee:
            return make_response(jsonify({"error": "Incorrect username!"}), 409)

        # If the password is incorrect, return an error
        elif employee.password != hashlib.md5(password.encode("utf-8")).hexdigest():
            return make_response(jsonify({"error": "Incorrect password!"}), 409)

        # Create a unique session identifier
        session_id = str(uuid.uuid4())

        # Storing session information in Redis with a unique key
        session_data = {
            "employee_id": employee.id,
            "employee_role": employee.role,
            "employee_department": employee.department,
            "employee_country": employee.country,
            "timestamp": datetime.now().isoformat()  # You can store additional info if needed
        }
        
        # Set the session data in Redis with the unique session ID
        r.set(f"session:{session_id}", json.dumps(session_data))

        # Returning a success message once a user is successfully authenticated
        return make_response(jsonify(
            {
                "success": "Login successful!",
                "first_login": employee.first_login,
                "session_id": session_id  # Return the session ID to the client
            }
        ))

api.add_resource(Login, "/login")

#Resource to update password
class UpdatePassword(Resource):
    def post(self):

        #Getting the session data
        session_data=get_session_data()

        #Getting the ID of the employee
        employee_id = session_data["employee_id"]

        #Getting the form data
        password=request.json["new_password"]
        confirm_password=request.json["confirm_password"]

        #Checking if both passwords match
        if password != confirm_password:
            return make_response(jsonify({"error": "Passwords do not match"}), 409)

        #Getting the employee details
        employee=Employee.query.filter(Employee.id == employee_id).first()

        #Hashing the password
        hashed_password=hashlib.md5(password.encode("utf-8")).hexdigest()

        #Checking if the new password is equal to the password in the databse
        if employee.password == hashed_password:
            return make_response(jsonify({"error": "New password cannot be the same as the current password"}), 409)

        #Updating the employee's password
        employee.password=hashed_password

        #Checking the employee's first_login status and updating it to false if it is true
        if employee.first_login:
            employee.first_login=False

        #AAdding and committing the changes to the database
        db.session.add(employee)
        db.session.commit()

        #Returning a success response
        return make_response(jsonify({"success": "Password updated successfully!"}),201)

api.add_resource(UpdatePassword, "/update-password")

#OTP Generation Resource
class GenerateOTP(Resource):
    def post(self):

        #Getting the email from the front end
        email=request.json["email"]

        #Checking if the email exists in the database. If it doesn't exist, return an error
        employee_record=Employee.query.filter_by(email=email).first()

        if not employee_record:
            return make_response(jsonify({"error": "No account with the given email exists!"}), 404)

        #If email exists, generate a OTP
        otp=get_otp()

        #Querying the OTP database to check if an OTP exists. If it exists, replace it with a new one
        existing_otp = OneTimePassword.query.filter_by(email=email).first()

        if existing_otp:
            existing_otp.otp=otp
            existing_otp.timestamp=datetime.now()

        else:
            #Adding the OTP to the database
            new_otp=OneTimePassword(email=email, otp=otp)
            db.session.add(new_otp)

        db.session.commit()
            
        #Sending the OTP to the user's email
        send_otp(email=email, otp=otp, last_name=employee_record.last_name, first_name=employee_record.first_name)

        #Returning a success message
        return make_response(jsonify({"success": "OTP generated successfully! Kindly check your email"}))

api.add_resource(GenerateOTP, "/generate-otp")

#Resource to validate the OTP
class ValidateOTP(Resource):
    def post(self):
        otp=request.json["otp"]

        #Checking if the OTP exists in the database
        existing_otp=OneTimePassword.query.filter_by(otp=otp).first()

        if not existing_otp:
            return make_response(jsonify({"error": "The entered OTP does not exist!"}), 404)
        
        #Checking if the timestamp is greater than 15 minutes. If it exceeds, delete the OTP and return an error
        if datetime.now() - existing_otp.timestamp > timedelta(minutes=15):
            db.session.delete(existing_otp)
            db.session.commit()
            return make_response(jsonify({"error": "OTP has already expired"}), 409)
        
        r.set("otp_email", existing_otp.email)
        db.session.delete(existing_otp)
        return make_response(jsonify({"success": "OTP validated successfully!"}), 200)
    
api.add_resource(ValidateOTP, "/validate-otp")

#Resource to update the password after OTP generation
class UpdatePasswordOTP(Resource):
    def post(self):

        #Getting the data from the front end
        otp_email=r.get("otp_email").decode("utf-8")
        new_password=request.json['new_password']
        confirm_password=request.json['confirm_password']

        # Checking if the two passwords match. If not, return an error
        if new_password != confirm_password:
            return make_response(jsonify({"error": "Passwords do not match!"}), 400)


        #Checking if the newly entered passwords is equal to the current password
        employee=Employee.query.filter_by(email=otp_email).first()
        
        hashed_password=hashlib.md5(new_password.encode("utf-8")).hexdigest()

        if employee.password == hashed_password:
            return make_response(jsonify({"error": "The new password cannot be equal to the current password"}), 409)
        
        else:
            #If not, update the password and delete the otp
            employee.password=hashed_password
            db.session.add(employee)
            db.session.commit()

            #Delete the OTP email session
            r.delete("otp_email")

            #Returning a success message
            return make_response(jsonify({"success": "Password updated successfully!"}))

api.add_resource(UpdatePasswordOTP, "/update-password-with-otp")

#Resource to update the leave days
class UpdateLeaveDays(Resource):
    def get(self):
        update_leave_days()
        return(make_response(jsonify({"success": "Leave days updated successfuly"})))

api.add_resource(UpdateLeaveDays, "/update-leave-days")

#Dashboard resource
class Dashboard(Resource):
    def get(self):

        #Getting the session data
        session_data=get_session_data()

        #Getting the ID of the employee
        employee_id = session_data["employee_id"]

        #If a user is logged in, fetch his/her data
        #Counting the leave applications and returning the response to the front end
        total_requests = LeaveApplication.query.filter(LeaveApplication.employee_id == employee_id).count()
        approved_requests = LeaveApplication.query.filter(
            LeaveApplication.employee_id == employee_id,
            LeaveApplication.hod_status == "Approved",
            LeaveApplication.hr_status == "Approved",
            LeaveApplication.gm_status == "Approved"
        ).count()
        rejected_requests = LeaveApplication.query.filter(
            LeaveApplication.employee_id == employee_id,
            (LeaveApplication.hod_status == "Rejected") |
            (LeaveApplication.hr_status == "Rejected") |
            (LeaveApplication.gm_status == "Rejected")
        ).count()
        pending_requests = LeaveApplication.query.filter(
        LeaveApplication.employee_id == employee_id,
        (
            (LeaveApplication.hod_status == "Pending") |
            (LeaveApplication.hr_status == "Pending") |
            (LeaveApplication.gm_status == "Pending")
        )
        ).count()

        #Getting the currently logged in employee so that we can return his.her full name
        employee=Employee.query.filter_by(id=employee_id).first()

        # Getting today's date
        today_date = date.today()

        # Getting leave applications where today's date is between start_date and end_date
        upcoming = LeaveApplication.query.join(Employee).filter(
            Employee.department == employee.department,
            LeaveApplication.start_date <= today_date,
            LeaveApplication.end_date >= today_date,
            LeaveApplication.hod_status == "Approved",
            LeaveApplication.gm_status == "Approved",
            LeaveApplication.hr_status == "Approved"
        ).all()

        upcoming_schema = LeaveApplicationsSchema(only=("id", "employee", "start_date", "end_date", "total_days")).dump(upcoming, many=True)
        
        # Initializing pending_requests_count with a default value
        pending_requests_count = 0
        
        #Getting the pending leave requests count
        role = session_data["employee_role"]
        department=session_data["employee_department"]
        country=session_data["employee_country"]

        #Getting the requests based on the user's role
        if role == "HOD":
            pending_requests_count = LeaveApplication.query.join(Employee).filter(
                LeaveApplication.hod_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.department == department,
                Employee.country == country
            ).count()

        elif role == "GM":
            pending_requests_count = LeaveApplication.query.join(Employee).filter(
                LeaveApplication.hod_status == "Approved",
                LeaveApplication.gm_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.country == country
            ).count()

        elif role == "HR":
            pending_requests_count = LeaveApplication.query.filter(
                LeaveApplication.hod_status == "Approved",
                LeaveApplication.gm_status == "Approved",
                LeaveApplication.hr_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.country == country

            ).count()
        
        #Creating the response to the front end
        return make_response(jsonify(
            {
                "success": "Logged in successfully",
                "full_name": employee.full_name(),
                "username": employee.username,
                "role": session_data["employee_role"],
                "leave_days":
                {
                    "total_requests": total_requests,
                    "approved_requests": approved_requests,
                    "rejected_requests":  rejected_requests,
                    "pending_requests": pending_requests
                },
                "upcoming_leave": upcoming_schema,
                "pending_requests_count": pending_requests_count
            }
        ))

api.add_resource(Dashboard, "/dashboard")

#Leave applications resource
class LeaveApplications(Resource):
    def get(self):

        #Getting the session data
        session_data=get_session_data()

        #Get the currently logged in user
        employee_id = session_data["employee_id"]

        #Get the user's leave applications and create a dict of it
        leave_applications=LeaveApplication.query.filter_by(employee_id=employee_id).all()
        leave_applications_dict=LeaveApplicationsSchema(only=("id",'leave_type',"leave_duration","start_date", "end_date")).dump(leave_applications,many=True)

        #Get the user's leave days from the database and create a dict
        leave_days=LeaveDays.query.filter_by(employee_id=employee_id).first()
        leave_days_dict=LeaveDaysSchema().dump(leave_days, many=False)

        #Getting the current logged in employee in order to get their gender
        employee=Employee.query.filter_by(id=employee_id).first()

        #Create a response
        return make_response(jsonify(
            {
                "leave_days": leave_days_dict,
                "leave_applications": leave_applications_dict,
                "gender": employee.gender,
                "country": employee.country
            }
        ),200)
    
    def post(self):
        
        #Getting the session data
        session_data=get_session_data()

        # Get the employee ID from the session
        employee_id = session_data["employee_id"]

        # Getting the values from the form
        leave_type = request.form.get("leave_type")
        leave_duration = request.form.get("leave_duration")
        start_date = datetime.strptime(request.form.get("start_date"), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get("end_date"), '%Y-%m-%d').date()
        total_days = request.form.get("total_days")
        reason = request.form.get("reason")
        file_attachment=request.files.get("file_attachment")

        #Querying the database to check if the leave application exists
        leaveapplication=LeaveApplication.query.filter_by(
            employee_id=employee_id, 
            start_date=start_date,
            end_date=end_date,
            leave_type=leave_type,
            leave_duration=leave_duration
            ).first()
        
        #If application exists, return an error
        if leaveapplication:
            return make_response(jsonify({"error": "An application with the given details already exists"}), 409)
        
        #Checking if the leave days being requested are greater than the number of leave days the employee has
        leave_days=LeaveDays.query.filter_by(employee_id=employee_id).first()

        if leave_type == "Normal":
            days_balance= float(leave_days.normal_leave) - float(total_days)

            #If leave balance is less than or equal to 0, return error. Else, update the leave days table
            if days_balance < 0:
                return make_response(jsonify({"error": "You do not have enough leave days"}), 409)

            leave_days.normal_leave=days_balance

        elif leave_type == "Sick":
            days_balance= float(leave_days.sick_leave) - float(total_days)

            if days_balance < 0:
                return make_response(jsonify({"error": "You do not have enough leave days"}), 409)
            
            leave_days.sick_leave=days_balance

        elif leave_type == "Paternity":
            days_balance= float(leave_days.paternity_leave) - float(total_days)

            if days_balance < 0:
                return make_response(jsonify({"error": "You do not have enough leave days"}), 409)
            
            leave_days.paternity_leave=days_balance

        elif leave_type == "Maternity":
            days_balance= float(leave_days.maternity_leave) - float(total_days)

            if days_balance < 0:
                return make_response(jsonify({"error": "You do not have enough leave days"}), 409)
            
            leave_days.maternity_leave=days_balance

        #If there is a file attachment, generate a unique file name and save it to the Uploads folder
        if file_attachment:
            # Getting the secure filename
            file_name = secure_filename(file_attachment.filename)

            # Generating a unique ID for each file name
            unique_file_name = str(uuid.uuid1()) + "_" + file_name

            # Path in the S3 bucket
            s3_path = f'uploads/{unique_file_name}'

            # Saving the file to S3 bucket
            try:
                # Upload the file to S3 and get the URL
                s3.upload_fileobj(file_attachment,S3_BUCKET_NAME,s3_path)

            except Exception as e:
                return make_response(jsonify({"error": "Error uploading file. Please try again later!"}), 500)

            # Store the file URL in the database instead of the FileStorage object
            file_attachment = unique_file_name
        else:
            file_attachment = None

        #Checking if the employee is either a HOD, HR or GM and updating those fields accordingly
        employee_role = session_data["employee_role"]
        if employee_role == "HOD":
            new_application=LeaveApplication(leave_type=leave_type, leave_duration=leave_duration, start_date=start_date, end_date=end_date, total_days=total_days, reason=reason, file_attachment=file_attachment, employee_id=employee_id, hod_status="Approved")

        elif employee_role== "HR":
            new_application=LeaveApplication(leave_type=leave_type, leave_duration=leave_duration, start_date=start_date, end_date=end_date, total_days=total_days, reason=reason, file_attachment=file_attachment, employee_id=employee_id, hod_status="Approved", hr_status="Approved")

        else:
            new_application=LeaveApplication(leave_type=leave_type, leave_duration=leave_duration, start_date=start_date, end_date=end_date, total_days=total_days, reason=reason, file_attachment=file_attachment, employee_id=employee_id)

        #Adding the changes made to the leave days and the newly created leave application
        db.session.add_all([new_application, leave_days])
        # db.session.commit()

        #Querying the database for the employee's superior
        employee_department=session_data["employee_department"]

        superior=""

        if employee_role == "User":
            superior=Employee.query.filter(Employee.role=="HOD", Employee.department==employee_department).first()
        
        elif employee_role == "HOD" or employee_role == "HR":
            superior=Employee.query.filter(Employee.role=="GM", Employee.department==employee_department).first()

        try:
            send_submitted_application(fullName=superior.full_name(), email=superior.email, employeeName=Employee.query.filter_by(id=employee_id).first().full_name(), startDate=start_date, endDate=end_date, total_days=total_days)

            #Commiting the changes made to the database
            db.session.commit()

            #Creating a response
            return make_response(jsonify(
                {
                    "success": "Application submitted successfully",
                    "application": LeaveApplicationsSchema().dump(new_application)
                }), 200)
        
        except Exception as e:
            print(e)
            return make_response(jsonify({"error": "Error submitting leave request. Please try again later"}))

api.add_resource(LeaveApplications, "/leave-applications")

#Individual leave application resource
class LeaveApplicationByID(Resource):
    def get(self, id):

        #Querying the database to get the specific application
        leave_application=LeaveApplication.query.filter_by(id=id).first()

        #If no application exists, return an error
        if not leave_application:
            return make_response(jsonify({"error": "Leave application could not be found"}), 404)
        
        #Creating a response dict for that specific application
        leave_application_dict=LeaveApplicationsSchema(only=("id", "leave_type","leave_duration", "start_date","end_date","total_days", "file_attachment","reason","hod_status","gm_status","hr_status")).dump(leave_application)
        
        #Creating a response
        return make_response(leave_application_dict, 200)

api.add_resource(LeaveApplicationByID, "/leave-applications/<int:id>")

#All employee leave requests
class ApprovedRequests(Resource):
    def get(self):
        #Querying the database to get all approved leave requests based on the country
        #Getting the session data
        session_data=get_session_data()

        # Get the employee ID from the session
        employee_role = session_data["employee_role"]
        employee_country = session_data["employee_country"]

        leave_requests_dict=""

        if employee_role == "HR":
            #Getting all the requests for the specific country
            leave_requests=LeaveApplication.query.filter(LeaveApplication.hod_status=="Approved",LeaveApplication.gm_status=="Approved",LeaveApplication.hr_status=="Approved",LeaveApplication.employee.has(Employee.country == employee_country)).all()

            #Creating a dict of the requests
            leave_requests_dict=LeaveApplicationsSchema(only=("id","employee", "leave_type", "leave_duration","start_date", "end_date", "total_days","file_attachment","status")).dump(leave_requests, many=True)

        elif employee_role == "HR-PT":
            #Getting all the requests
            leave_requests=LeaveApplication.query.filter(LeaveApplication.hod_status=="Approved",LeaveApplication.gm_status=="Approved",LeaveApplication.hr_status=="Approved").all()

            #Creating a dict of the requests
            leave_requests_dict=LeaveApplicationsSchema(only=("id","employee", "leave_type", "leave_duration","start_date", "end_date", "total_days","file_attachment","status")).dump(leave_requests, many=True)

        return make_response(jsonify({
            "success" : "Fetched successfully",
            "leave_data": leave_requests_dict
        }), 200)

api.add_resource(ApprovedRequests, "/approved-requests")

#All pending employee requests
class PendingEmployeeRequests(Resource):
    def get(self):

        #Getting the session data
        session_data=get_session_data()

        #Getting the session data which will be used to query the leave applications table
        employee_id = session_data["employee_id"]
        role = session_data["employee_role"]
        department=session_data["employee_department"]
        country=session_data["employee_country"]

        #Displaying the requests based on the user's role
        if role == "HOD":
            pending_requests = LeaveApplication.query.join(Employee).filter(
                LeaveApplication.hod_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.department == department,
                Employee.country == country
            ).all()

        elif role == "GM":
            pending_requests = LeaveApplication.query.join(Employee).filter(
                LeaveApplication.hod_status == "Approved",
                LeaveApplication.gm_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.country == country
            ).all()

        elif role == "HR":
            pending_requests = LeaveApplication.query.filter(
                LeaveApplication.hod_status == "Approved",
                LeaveApplication.gm_status == "Approved",
                LeaveApplication.hr_status == "Pending",
                LeaveApplication.employee_id != employee_id,
                Employee.country == country

            ).all()

        #Creating a response will the fetched requests
        return make_response({"pending_requests": LeaveApplicationsSchema().dump(pending_requests, many=True)}, 200)
    
api.add_resource(PendingEmployeeRequests, "/pending-employee-requests")

#Individual pending employee requests 
class PendingEmployeeRequestsByID(Resource):
    def get(self, id):
        #Querying the database to get the individual request and creating a dict of it
        request=LeaveApplication.query.filter_by(id=id).first()
        response=LeaveApplicationsSchema().dump(request)

        return make_response(response, 200)
    
    #Patch request to update the request
    def patch(self, id):

        #Getting the session data
        session_data=get_session_data()

        #Getting the approval status (Approved or Rejected) from the frontend
        status=request.json["status"]
        #Getting the role of the currently logged in employee
        role = session_data["employee_role"]
        
        #Getting the request from the database
        application=LeaveApplication.query.filter_by(id=id).first()

        #Updating the status based on the logged in user's role
        if role == "HOD":
            if status == "Rejected":
                application.hod_status=status
                application.hr_status=status
                application.gm_status=status

            application.hod_status=status
        
        elif role == "GM":
            if status == "Rejected":
                application.hr_status=status
                application.gm_status=status
            
            application.gm_status=status
        
        elif role == "HR":
            application.hr_status=status

            # #Sending an email to the employee once the leave has been fully approved
            # if status == "Approved":
            #     #Getting the employee's email and name
            #     employee_email=application.employee.email
            #     employee_name=application.employee.full_name()

            #     #Sending the email
            #     send_approved_leave(employeeEmail=employee_email, startDate=application.start_date, duration=application.total_days, employeeName=employee_name,endDate=application.end_date)

        db.session.add(application)
        db.session.commit()

        #Returning a success message for approved requests
        if status == "Approved":
            try:
                #Getting the employee's email and name
                employee_email=application.employee.email
                employee_name=application.employee.full_name()

                #Sending the email
                send_approved_leave(employeeEmail=employee_email, startDate=application.start_date, duration=application.total_days, employeeName=employee_name,endDate=application.end_date)
                return make_response(jsonify({"success": "Leave application approved successfully"}),200)
            except Exception as e:
                print(e)
                return make_response(jsonify({"error": "Error approving leave request. PLease try again later"}),500)

        #If the status is rejected, get the employee id from the leave application, query the leave days table and add back the number of leave days of that application
        elif status == "Rejected":
            employee_id=application.employee_id
            leave_days=LeaveDays.query.filter_by(employee_id=employee_id).first()

            if application.leave_type == "Normal":
                leave_days.normal_leave= float(leave_days.normal_leave) + float(application.total_days)

            elif application.leave_type == "Sick":
                leave_days.sick_leave= float(leave_days.sick_leave) + float(application.total_days)

            elif application.leave_type == "Paternity":
                leave_days.paternity_leave= float(leave_days.paternity_leave) + float(application.total_days)
            
            elif application.leave_type == "Maternity":
                leave_days.maternity_leave= float(leave_days.maternity_leave) + float(application.total_days)

            db.session.add(leave_days)
            db.session.commit()
            return make_response(jsonify({"success": "Leave application rejected successfully"}),200)

api.add_resource(PendingEmployeeRequestsByID, "/pending-employee-requests/<int:id>")

# File fetching resource
class GetFile(Resource):
    def get(self, filename):
        try:
            # Fetch the file from the S3 bucket
            file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=f"uploads/{filename}")
            # Use BytesIO to create a stream from the S3 file object
            file_stream = io.BytesIO(file_obj['Body'].read())
            return send_file(file_stream, as_attachment=True, attachment_filename=filename)
            
        except Exception as e:
            return(make_response(jsonify({"error": "File not found"})),404)

api.add_resource(GetFile, "/get-file/<path:filename>")

#All employees resource
class Employees(Resource):
    def get(self):
        
        #Getting the session data
        session_data=get_session_data()

        #Getting the employee id
        employee_id = session_data["employee_id"]

        #Getting the employee country
        employee_country=session_data["employee_country"]

        #Getting the role of the currently logged in user
        employee_role=session_data["employee_role"]
                
        employee_dict=""

        if employee_role == "HR-PT":
            employees=Employee.query.filter(Employee.id != employee_id).all()
            employee_dict=EmployeeSchema(only=("id","first_name", "last_name","email","branch")).dump(employees, many=True)
        else:
            #Getting all employees from the database and creating a dict 
            employees=Employee.query.filter(Employee.id != employee_id, Employee.country == employee_country).all()
            employee_dict=EmployeeSchema().dump(employees, many=True)

        return make_response(jsonify(
            {
                "success": "You have access rights",
                "employee_data": employee_dict,
                "country": employee_country
            }
        ), 200)
    
    def post(self):

        #Getting the data from the form
        first_name=request.json["first_name"]
        last_name=request.json["last_name"]
        email=request.json["email"]
        branch=request.json["branch"]
        country=request.json["country"]
        phone=request.json["phone"]
        gender=request.json["gender"]
        department=request.json["department"]
        position=request.json["position"]
        role=request.json["role"]

        #Creating a username and a random password
        username=(first_name[0]+last_name).lower()
        password=random_password()

        #Checking if the email exists in the database. If it does, return an error
        if Employee.query.filter_by(email=email).first():
            return make_response(jsonify({"error" : "Email already exists"}),409)
        
        #Checking if the phone number exists in the database. If it does, return an error
        if Employee.query.filter_by(phone=phone).first():
            return make_response(jsonify({"error" : "Phone number already exists"}),409)
        
        #Checking if the username exists in the database. If it does, return an error
        elif Employee.query.filter_by(username=username).first():
            return make_response(jsonify({"error" : "Username already exists"}),409)
        
        #Hashing the password
        hashed_password=hashlib.md5(password.encode("utf-8")).hexdigest()

        #Creating the employee's account
        new_employee=Employee(first_name=first_name, username=username, password=hashed_password, last_name=last_name, gender=gender, department=department, country=country, phone=phone, role=role, position=position, email=email, branch=branch)

        #Sending the email with the login credentials
        send_login_credentials(last_name=last_name, username=username, first_name=first_name, email=email, password=password)

        #Creating an employee's leave days once their account is created
        if new_employee.gender=="Male":
            leave_days=LeaveDays(employee=new_employee,normal_leave=21, sick_leave=14, paternity_leave=14, maternity_leave=0)

        elif new_employee.gender == "Female":
            leave_days=LeaveDays(employee=new_employee,normal_leave=21, sick_leave=14, paternity_leave=0, maternity_leave=90)

        #Committing the info to the database
        db.session.add_all([new_employee, leave_days])
        db.session.commit()

        #Creating a dict of the newly created account and including it in the response
        employee=EmployeeSchema().dump(new_employee)

        return make_response(jsonify(
            {
                "success": "Employee account created successfully",
                "employee_data": employee
            }
        ), 201)
    
api.add_resource(Employees, "/employees-data")

#Resource for fetching specific employee's data
class EmployeeByID(Resource):

    def get(self, id):
        #Getting the individual employee
        employee=Employee.query.filter_by(id=id).first()

        #Displaying an error message if the employee doesn't exist
        if not employee:
            return make_response(jsonify({"error": "Employee not found"}), 404)
        
        #Getting the employee's leave days from the leave days table
        employee_leave_days=LeaveDays.query.filter_by(employee_id=id).first()

        #Creating a dict for the employee's details
        employee_dict=EmployeeSchema().dump(employee)

        #Creating a dict for the employee's leave days
        leave_days_dict=LeaveDaysSchema().dump(employee_leave_days)

        #Creating a response dict that combines both the employee's details and his/her leave days
        response_dict={}
        response_dict.update(employee_dict)
        response_dict.update(leave_days_dict)

        return make_response(response_dict, 200)
    
    def patch(self, id):
        #Querying the database to check if the employee exists
        employee_to_update=Employee.query.filter_by(id=id).first()

        #If the employee doesn't exist, return an error
        if not employee_to_update:
            return make_response(jsonify({"error": "Employee not found"}), 404)
        
        #Getting the value from the form
        normal_leave=request.json["normal_leave"]

        #If the current leave days is equal to the value being passed, return an error
        if employee_to_update.leave_days.normal_leave == normal_leave :
            return make_response(jsonify({"error": "The current leave days count cannot be equal to the value provided"}), 409)
        
        #Updating the value of the employee's normal leave days
        employee_to_update.leave_days.normal_leave=normal_leave
        db.session.add(employee_to_update)
        db.session.commit()

        return make_response(jsonify({"success": "Leave days updated successfully!"}), 200)
    
    def delete(self, id):

        #Getting the employee from the database
        employee_to_delete=Employee.query.filter_by(id=id).first()
        
        #If employee doesn't exist, return an error
        if not employee_to_delete:
            return make_response(jsonify({"error": "Employee could not be found"}),404)

        #Deleting the employee's details
        db.session.delete(employee_to_delete.leave_days)

        #Looping over the leave applications and deleting them individually
        for leave_application in employee_to_delete.leave_applications:
            db.session.delete(leave_application)
            
        #Deleting the employee and committing the changes
        db.session.delete(employee_to_delete)
        db.session.commit()

        return make_response(jsonify(
            {
                "success": "Employee deleted successfully!"
            }),200)

api.add_resource(EmployeeByID, "/employees-data/<int:id>")

#Employee leave history resource
class EmployeeLeaveHistory(Resource):
    def get(self, id):
        #Getting the session data
        session_data=get_session_data()

        #Getting the role of the currently logged in user
        employee_role=session_data["employee_role"]

        if employee_role != "HR-PT":
            return make_response(jsonify({"error": "You don't have the rights"}),409)

        #Getting the employee's leave applications from the database
        employee_leaves=LeaveApplication.query.filter_by(employee_id=id).all()
        employee_leaves_dict=LeaveApplicationsSchema(only=("id", "leave_type","leave_duration", "start_date","end_date","total_days", "file_attachment","reason","hod_status","gm_status","hr_status")).dump(employee_leaves,many=True)

        print(employee_leaves_dict)

api.add_resource(EmployeeLeaveHistory, "/employee-leave-history")

#Profile resource
class Profile(Resource):
    def get(self):
        #Getting the session data
        session_data=get_session_data()

        #Getting the ID of the current logged in user
        employee_id = session_data["employee_id"]

        #If no one is logged in, return an error
        if not employee_id:
            return make_response(jsonify({"error": "Kindly login to continue"}), 404)

        #Get the employee's details from the database if they are logged in
        employee=Employee.query.filter(Employee.id==employee_id).first()
        employee_details=EmployeeSchema().dump(employee)
        return make_response(employee_details, 200)
    
    #Password update functionality in the profile page
    def post(self):

        #Getting the session data
        session_data=get_session_data()

        #Getting the attributes from the form
        current_password=request.json["current_password"]
        new_password=request.json["new_password"]
        confirm_password=request.json["confirm_password"]

        #Getting the current logged in employee
        employee=Employee.query.filter(Employee.id==session_data["employee_id"]).first()

        #Hashing the password 
        hashed_password=hashlib.md5(new_password.encode()).hexdigest()

        #Checking if the value of current password is not equal to the password in the database
        if employee.password != hashlib.md5(current_password.encode()).hexdigest():
            return make_response(jsonify({"error": "Incorrect current password. Please try again."}), 409)
        
        #Checking if the new and confirm passwords match
        if  new_password!=confirm_password:
            return make_response(jsonify({"error":"The new password and current passwords do not match!"}), 409)
        
        #Checking if the new hashed password is equal to the value of the password in the database
        if employee.password == hashed_password:
            return make_response(jsonify({"error": "The new password cannot be the same as the current password."}), 409)
        
        #Updating the password
        employee.password = hashed_password
        db.session.add(employee)
        db.session.commit()

        return make_response(jsonify({"success": "Password updated successfully"}))

    def patch(self):
        #Getting the session data
        session_data=get_session_data()

        # Get the new profile image
        profile_image = request.files.get("profile_image")

        # Getting the file name
        profile_image_filename = profile_image.filename

        # Generating a unique file name
        unique_profile_image_name = str(uuid.uuid1()) + "_" + profile_image_filename

        # Path to the folder in S3 bucket
        s3_path = f"images/{unique_profile_image_name}"

        # Get the employee ID from the session or request
        employee_id = session_data["employee_id"]
        employee = Employee.query.filter_by(id=employee_id).first()

        if not employee:
            return make_response(jsonify({"error": "Employee not found"}), 404)

        # Check if there's an existing profile image
        if employee.profile_picture:
            old_s3_path = f"images/{employee.profile_picture}"

            # Delete the old image from S3
            try:
                s3.delete_object(Bucket=S3_BUCKET_NAME, Key=old_s3_path)

            except Exception as e:
                return make_response(jsonify({"error": "Error deleting old profile image. Please try again later!"}), 500)

        # Upload the new file to S3
        try:
            s3.upload_fileobj(profile_image, S3_BUCKET_NAME, s3_path)

            # Update the profile picture in the database with the new unique file name
            employee.profile_picture = unique_profile_image_name
            db.session.add(employee)
            db.session.commit()

            return make_response(jsonify({"success": "Profile picture updated successfully!"}), 200)
        except Exception as e:
            return make_response(jsonify({"error": "Error uploading file. Please try again later!"}), 500)

api.add_resource(Profile, "/profile")

#Logout resource
class Logout(Resource):
    def post(self):
        session_id = request.headers.get('X-Session-ID')
        if session_id:
            r.delete(f"session:{session_id}")
        #Return a response
        return make_response(jsonify({"success": "Logged out successfully"}), 200)
    
api.add_resource(Logout, "/logout")

if __name__=="__main__":
    app.run(port=5555, debug=True)