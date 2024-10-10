from api.app import app
from api.models import Employee, LeaveApplication, LeaveDays, db, OneTimePassword

if __name__ == "__main__":
    with app.app_context():
        print("Seed file")
        # Employee.query.delete()
        # LeaveApplication.query.delete()
        # LeaveDays.query.delete()
        # OneTimePassword.query.delete()
        # db.session.commit()

        samuel_muigai=Employee(first_name="Samuel",last_name="Muigai", gender="Male", email="muigaisam65@gmail.com", username="smuigai", country="KE", phone="+254707251073", department="Logistics", position="Logistics Assistant", role="HR", password="214aaf2c9a8510d948555ee25cb38397", branch="Mobikey Kenya")
        db.session.add(samuel_muigai)
        db.session.commit()

        muigai_leave_days=LeaveDays(employee_id=samuel_muigai.id, normal_leave=21, sick_leave=14, maternity_leave=0, paternity_leave=14)
        db.session.add(muigai_leave_days)
        db.session.commit()

        # lourdes_wairimu=Employee(first_name="Lourdes", last_name="Wairimu", gender="Female", email="lourdeswairimu@gmail.com", username="lwairimu", country="KE", phone="+254745416760", department="Administration", position="HR Manager", role="HR", password="cf63d8b585dd65eae31466ede6fe65c5", first_login=False, branch="Mobikey Kenya")
        # db.session.add(lourdes_wairimu)
        # db.session.commit()

        # wairimu_leave_days=LeaveDays(employee_id=lourdes_wairimu.id, normal_leave=21, sick_leave=14, maternity_leave=90, paternity_leave=0)
        # db.session.add(wairimu_leave_days)
        # db.session.commit()

        # david_tundo=Employee(first_name="David",last_name="Tundo", gender="Male", email="david.tundo@mobikey.co.ke", username="dtundo", country="KE", phone="+254793305103", department="Finance", position="Tax and Admin Manager", role="HOD", password="f30da452351da3baea61fa20ac419010", branch="Mobikey Kenya", first_login=False)
        # db.session.add(david_tundo)
        # db.session.commit()

        # tundo_leave_days=LeaveDays(employee_id=david_tundo.id, normal_leave=21, sick_leave=14, maternity_leave=0, paternity_leave=14)
        # db.session.add(tundo_leave_days)
        # db.session.commit()

        print("Information added successfully")