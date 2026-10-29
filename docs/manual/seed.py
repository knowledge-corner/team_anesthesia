import datetime, random
from decimal import Decimal
from django.utils import timezone
from accounts.models import User, Doctor
from cases.models import Case
from contacts.models import Contact, ContactAffiliation, Surgeon
from hospitals.models import Hospital
from payments.models import Payment, PaymentFollowUp

random.seed(7)
today = timezone.localdate()
u = User.objects.create_user("dr.anjali", password="Demo@12345", role=User.ROLE_DOCTOR, email="anjali@example.com",
                             first_name="Anjali", last_name="Mehta")
d = Doctor.objects.create(user=u, display_name="Dr. Anjali Mehta", phone="9822012345")
User.objects.create_user("admin", password="Admin@12345", role=User.ROLE_ADMIN, email="admin@example.com",
                         first_name="Admin")
u2 = User.objects.create_user("dr.rao", password="Demo@12345", role=User.ROLE_DOCTOR, email="rao@example.com")
d2 = Doctor.objects.create(user=u2, display_name="Dr. Vikram Rao", phone="9822054321")
u3 = User.objects.create_user("dr.bhide", password="Demo@12345", role=User.ROLE_DOCTOR, email="bhide@example.com")
Doctor.objects.create(user=u3, display_name="Dr. Kiran Bhide", phone="9822077777")

H = {k: Hospital.objects.get(name=n) for k, n in [
    ("ruby", "Ruby Hall Clinic"), ("jeh", "Jehangir Hospital"), ("sah", "Sahyadri Hospital Kothrud"),
    ("deen", "Deenanath Mangeshkar Hospital"), ("noble", "Noble Hospital")]}
H["ruby"].phone = "020-66455100"; H["ruby"].save()

def surgeon(name, phone, spec, *hs):
    s = Surgeon.objects.create(doctor=d, name=name, phone=phone, speciality=spec)
    for h in hs: s.link_hospital(H[h])
    return s
S = {
 "shah": surgeon("Dr. Amit Shah", "9890011111", "Orthopaedics", "ruby", "jeh"),
 "kul": surgeon("Dr. Neha Kulkarni", "9890022222", "Obstetrics & Gynaecology", "sah", "ruby"),
 "desh": surgeon("Dr. Rahul Deshpande", "9890033333", "General Surgery", "deen", "noble"),
 "joshi": surgeon("Dr. Sameer Joshi", "9890044444", "ENT", "noble"),
}
def contact(name, phone, role, h, primary=True):
    c = Contact.objects.create(doctor=d, name=name, phone=phone, role=role)
    ContactAffiliation.objects.create(contact=c, hospital=H[h], is_primary=primary,
                                      start_date=today - datetime.timedelta(days=200))
    return c
C = {"ruby": contact("Mr. Sunil Patil", "9850011111", "billing", "ruby"),
     "jeh": contact("Mrs. Kavita Shinde", "9850022222", "accounts", "jeh"),
     "sah": contact("Mr. Rohan Gokhale", "9850033333", "billing", "sah"),
     "deen": contact("Ms. Priya Pawar", "9850044444", "ot", "deen")}

patients = ["Sunita Patil", "Ramesh Kale", "Meena Joshi", "Arjun Deshmukh", "Kavya Nair", "Suresh Bhosale",
            "Pooja Kulkarni", "Anil Jadhav", "Rekha Shah", "Vijay More", "Asha Pawar", "Nikhil Gupta",
            "Lata Shinde", "Rahul Sawant", "Sneha Iyer", "Prakash Rane", "Geeta Mane", "Omkar Joshi",
            "Neelam Desai", "Sanjay Pillai", "Varsha Gaikwad", "Deepak Chavan", "Swati Kadam", "Manoj Thakur",
            "Harsha Patkar", "Kiran Salunkhe"]
plan = [  # days_ago, hospital, surgeon, procedure, fee, paid fraction
 (1,"ruby","shah","TKR - spinal",9000,0),(2,"sah","kul","LSCS - spinal",7000,0),(3,"jeh","shah","Arthroscopy - GA",6500,1),
 (5,"deen","desh","Lap chole - GA",8000,0.5),(8,"noble","joshi","Tonsillectomy - GA",5000,0),(10,"ruby","kul","Hysterectomy - spinal",8500,1),
 (14,"sah","kul","LSCS - spinal",7000,0),(18,"noble","desh","Hernia repair - spinal",6000,1),(22,"ruby","shah","THR - CSE",11000,0.5),
 (27,"jeh","shah","Fracture fixation - block",5500,0),(33,"deen","desh","Appendicectomy - GA",7000,0),(38,"sah","kul","LSCS - spinal",7000,1),
 (41,"ruby","shah","TKR - spinal",9000,0),(47,"noble","joshi","Septoplasty - GA",5500,0.4),(52,"deen","desh","Lap chole - GA",8000,1),
 (58,"ruby","kul","Labour analgesia",4000,1),(64,"jeh","shah","Arthroscopy - GA",6500,0),(71,"sah","kul","LSCS - spinal",7000,1),
 (79,"noble","desh","Hernia repair - spinal",6000,0),(86,"ruby","shah","TKR - spinal",9000,1),(95,"deen","desh","Lap chole - GA",8000,0.5),
 (104,"jeh","shah","Fracture fixation - block",5500,1),(112,"sah","kul","Hysterectomy - spinal",8500,1),(121,"ruby","shah","THR - CSE",11000,1),
 (130,"noble","joshi","Tonsillectomy - GA",5000,1),(140,"deen","desh","Appendicectomy - GA",7000,0),
]
modes = ["upi", "bank", "cheque", "upi", "cash"]
for i, (ago, h, s, proc, fee, frac) in enumerate(plan):
    cdate = today - datetime.timedelta(days=ago)
    case = Case.objects.create(doctor=d, hospital=H[h], surgeon=S[s], contact=C.get(h), case_date=cdate,
                               patient_name=patients[i], patient_reference=f"IP {45200 + i * 17}",
                               procedure_type=proc, fee=Decimal(fee), created_by=u)
    if frac:
        pdate = min(today, cdate + datetime.timedelta(days=random.randint(5, 25)))
        Payment.objects.create(case=case, amount=Decimal(int(fee * frac)), payment_date=pdate,
                               mode=modes[i % 5], reference_no=f"UTR{random.randint(10**8, 10**9)}", created_by=u,
                               received_by=["Dr. Anjali Mehta", "Clinic reception", "Bank account"][i % 3])
    if not frac and ago > 30 and i % 2:
        PaymentFollowUp.objects.create(case=case, followup_date=today - datetime.timedelta(days=ago - 20),
                                       method="call", contact=C.get(h), contact_person=C[h].name if h in C else "",
                                       notes="Said bill is with accounts, will release this month.")
# Dr. Rao: a few cases of a colleague (everyone in the practice sees them)
for i, name in enumerate(["Shobha Kamat", "Ravi Naik", "Uma Bapat", "Ganesh Lele"]):
    Case.objects.create(doctor=d2, hospital=H["jeh"], surgeon=S["shah"], case_date=today - datetime.timedelta(days=i * 9 + 2),
                        patient_name=name, procedure_type="Arthroscopy - GA", fee=Decimal(6000), created_by=u2)
# A hospital added twice under another spelling (for the "merge duplicates" screenshots)
Hospital.objects.create(name="Jehangir", city="Pune", source="doctor", created_by=u2)
print("cases", Case.objects.count())
