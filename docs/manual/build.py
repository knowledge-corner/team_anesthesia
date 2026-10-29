"""Builds manual.html (then printed to PDF by print.js). Content is written for doctors in plain language."""
import base64
import html
import os
import pathlib

# The practice's app address, printed in the manual (set MANUAL_APP_URL when rebuilding).
APP_URL = os.environ.get("MANUAL_APP_URL", "https://teamanaesthesia.co.in")

SECTIONS = []  # (id, title, blocks)


def sec(id_, title, intro=""):
    SECTIONS.append({"id": id_, "title": title, "intro": intro, "blocks": []})


def topic(title, steps, img=None, tip=None, note=None, img2=None, caption=None, caption2=None):
    SECTIONS[-1]["blocks"].append(dict(kind="topic", title=title, steps=steps, img=img, tip=tip, note=note,
                                       img2=img2, caption=caption, caption2=caption2))


def table(title, head, rows, after=None):
    SECTIONS[-1]["blocks"].append(dict(kind="table", title=title, head=head, rows=rows, after=after))


def para(text):
    SECTIONS[-1]["blocks"].append(dict(kind="para", text=text))


# ----------------------------------------------------------------------------- content
sec("welcome", "Welcome", "This app keeps track of the anaesthesia work done in your practice, how much each hospital owes, "
    "and who to call when a payment is late. Everyone signs in with their own login and sees all cases of the practice, "
    "so anyone can add, update or follow up a case. This manual walks you through every screen, one step at a time.")
para(f"<b>Your app address:</b> <span style='font-size:13pt'><b>{APP_URL}</b></span><br>"
     "Open it in <b>Chrome</b> (Android) or <b>Safari</b> (iPhone) and add it to your home screen (section 1).")
para("<b>Tip:</b> In the screenshots, the button or box you need to tap is marked with a <span style='color:#e11d48'><b>red outline</b></span>. "
     "All names, patients and amounts in this manual are sample data.")
table("What the app does for you", ["You want to...", "Go to"], [
    ["Write down a case you have finished", "<b>Add Case</b> (yellow + button at the bottom)"],
    ["See how much money is still to come", "<b>Dashboard</b>"],
    ["Note a payment you received", "Open the case → <b>Record payment</b>"],
    ["Know which hospital to call today", "Dashboard → <b>Follow-ups</b> card"],
    ["Get Excel sheets for your CA or records", "<b>Reports</b> → any report → <b>Download Excel</b>"],
])
table("Words used in this manual", ["Word", "Meaning"], [
    ["Case", "One piece of work you did (one patient, one surgery) that you will be paid for."],
    ["Fee", "The amount you charge for that case."],
    ["Received", "Money already paid to you for the case."],
    ["Outstanding", "Money still to come (Fee minus Received)."],
    ["Expected payment date", "The date by which you expect to be paid. If you leave it empty, the app assumes 30 days."],
    ["Overdue", "The expected payment date has passed and the case is not fully paid."],
    ["Follow-up", "A call or message to the hospital to ask about a pending payment."],
    ["Anaesthetist", "The anaesthetist who did the case. Empty on Add Case = yourself (Self). Every list can be filtered by it."],
    ["Surgeon", "The surgeon who called you for the case. The list is shared by the practice."],
    ["Contact", "A person at the hospital (billing, accounts, OT) whom you call about payments. Shared by the practice."],
])
table("Payment status colours", ["Label", "What it means"], [
    ["<span class='pill grey'>Pending</span>", "Nothing received yet, still within the expected date."],
    ["<span class='pill blue'>Partially Paid</span>", "Some money received, some still due."],
    ["<span class='pill green'>Paid</span>", "Fully paid. Nothing more to do."],
    ["<span class='pill red'>Overdue</span>", "Expected date has passed and money is still due. Time to follow up."],
])

# --------------------------------------------------------------------------- getting started
sec("start", "1. Getting started")
topic("Open the app and add it to your phone", [
    f"Open <b>{APP_URL}</b> in <b>Chrome</b> (Android) or <b>Safari</b> (iPhone). "
    "Link opened inside WhatsApp or Gmail? Use the menu → <b>Open in Chrome / Safari</b>.",
    "<b>Android:</b> tap <b>Install app</b> on the sign-in page, or Chrome menu <b>⋮</b> → <b>Install app</b>.",
    "<b>iPhone:</b> tap the <b>Share</b> button → <b>Add to Home Screen</b> → <b>Add</b>.",
    "An app icon appears on your home screen. From now on open the app from this icon - it works like a normal app.",
], tip="You need to do this only once on each phone.")
topic("Create your account (first time only)", [
    "On the sign-in page tap <b>Create an account</b>.",
    "Fill in your <b>full name</b>, <b>mobile number</b> and <b>email</b>.",
    "Choose a <b>Username</b> (your User ID, e.g. <i>dr.anjali</i>) and a <b>password</b>, then tap <b>Create account</b>.",
], img="02-signup", tip="Enter your mobile number correctly. It is used to recover your User ID and password later. "
   "Once you have signed up, your name appears in everyone's <b>Anaesthetist</b> list on Add Case.")
topic("Sign in", [
    "Type your <b>User ID</b> and <b>Password</b>.",
    "Tap <b>Sign in</b>. You land on the Dashboard.",
    "You stay signed in on your phone for <b>30 days</b>. After that the app signs you out automatically - just sign in again. "
    "This protects everyone's data if a phone is lost.",
    "Forgot something? Use the links marked in red: <b>Forgot user ID?</b> and <b>Forgot password?</b>",
], img="01-login")
topic("Forgot your User ID", [
    "On the sign-in page tap <b>Forgot user ID?</b>",
    "Enter the <b>mobile number</b> you registered with and tap <b>Find my user ID</b>.",
    "Your User ID is shown on the screen. Tap <b>Sign in</b> to continue.",
], img="03-forgot-id", img2="04-forgot-id-result", caption="Enter mobile number", caption2="Your User ID is shown")
topic("Forgot your password", [
    "On the sign-in page tap <b>Forgot password?</b>",
    "Enter your <b>User ID</b> and registered <b>mobile number</b>, then tap <b>Verify</b>.",
    "If they match, type a <b>new password</b> twice and tap <b>Save new password</b>.",
    "Sign in with the new password.",
], img="05-forgot-password", img2="06-set-new-password", caption="Verify", caption2="Set new password",
   note="After 5 wrong tries the form is locked for 15 minutes. Wait, or ask your admin.")
topic("Change your password", [
    "Profile menu (round icon, top right) → <b>Change password</b>.",
    "Type your <b>old password</b>, then the <b>new password</b> twice.",
    "Tap <b>Save new password</b>. You stay signed in.",
], img="14-change-password")

# --------------------------------------------------------------------------- layout
sec("layout", "2. Finding your way around")
topic("The bottom bar", [
    "<b>Dashboard</b> - your money summary and today's to-do list.",
    "<b>Cases</b> - every case you have entered, with search.",
    "<b>Add Case</b> (yellow + in the middle) - write down a new case.",
    "<b>Hospitals</b> - hospitals you work with, and search for any hospital.",
    "<b>Reports</b> - summaries and Excel downloads.",
], img="10-dashboard")
topic("The profile menu (round icon, top right)", [
    "Shows who is signed in.",
    "<b>Contacts &amp; surgeons</b> - the practice's hospital contacts and surgeons.",
    "<b>Notification settings</b> - payment reminders on your phone.",
    "<b>Change password</b> (marked in red).",
    "<b>Sign out</b> - log out of the app on this phone.",
], img="13-profile-menu")

# --------------------------------------------------------------------------- dashboard
sec("dashboard", "3. Dashboard")
topic("Your money at a glance", [
    "Choose <b>All anaesthetists</b> to see the whole practice, or pick one name to see only that anaesthetist's figures.",
    "At the top, choose the period: <b>This month</b>, <b>This FY</b> (April to March) or <b>All time</b>.",
    "<b>Total earnings</b> - total fees of cases in that period.",
    "<b>Received</b> - money received in that period.",
    "<b>Outstanding</b> - all money still to come.",
], img="10-dashboard")
topic("Tap a card to see the cases behind it", [
    "<b>Outstanding</b> - every case that is not fully paid.",
    "<b>Pending</b> - unpaid cases that are not yet overdue.",
    "<b>Overdue</b> - cases past their expected payment date.",
    "<b>Follow-ups</b> - cases where it is time to call the hospital.",
    "Use the <b>←</b> arrow at the top to come back.",
], img="11-dashboard-cards")
topic("Action required", [
    "Lower down, <b>Action required</b> lists cases that need a call today.",
    "Tap the green <b>phone icon</b> next to a hospital to call the right person straight away.",
    "Tap a row to open the case.",
], img="12-dashboard-action", tip="Check this list once a day - it is your payment to-do list.")

# --------------------------------------------------------------------------- add case
sec("addcase", "4. Adding a case", "Do this right after the case, or at the end of the day. It takes about 30 seconds.")
topic("Step 1 - Open Add Case", [
    "Tap the yellow <b>+ Add Case</b> button at the bottom.",
    "<b>Anaesthetist</b> shows <b>Self</b> - leave it for your own case.",
    "Fields with a red <b>*</b> are required: <b>Hospital</b>, <b>Case date</b> and <b>Fee</b>.",
    "Many cases to enter at once? Use <b>Bulk upload</b> (top right) - see section 5.",
], img="20-add-case")
topic("Adding a case for a colleague", [
    "Tap the <b>Anaesthetist</b> box and pick the colleague's name.",
    "Everyone who has signed up is listed - you never type a name.",
    "Colleague not in the list? Ask them to <b>Create an account</b> first.",
    "<b>Save &amp; add</b> keeps the same colleague for the next case.",
], img="20b-colleague")
topic("Step 2 - Choose the hospital", [
    "Tap the <b>Hospital</b> box and type a few letters of the name or area, e.g. <i>ruby</i> or <i>kothrud</i>.",
    "Pick the right hospital from the list. Hospitals the practice already works with show a green <b>Mine</b> tag.",
    "Spelling not sure? The app also shows close matches under <b>Did you mean?</b> - e.g. <i>seathurney</i> finds "
    "<i>Seatherney Hospital</i>. Words like <i>hospital</i> or <i>clinic</i> do not need to be typed.",
    "Not in the list? Tap <b>Add a hospital not in the list</b> (see next step).",
], img="21-hospital-search", img2="21b-did-you-mean", caption="Search", caption2="Did you mean?")
topic("Hospital not in the list? Add it", [
    "Type the <b>Name</b>, <b>Area</b> and <b>City</b>. Other details are optional.",
    "Tap <b>Save hospital</b>. You return to Add Case with the new hospital already chosen.",
    "If a hospital with a similar name already exists, the app asks <b>Is it one of these?</b> Tap <b>Use this one</b>, "
    "or <b>No, it's a different hospital - add it</b>.",
], img="29-add-hospital", img2="29b-is-it-one-of-these", caption="Add a hospital", caption2="Similar hospital found",
   tip="This stops the same hospital being added twice under different spellings.")
topic("Step 3 - Date, fee, patient and surgeon", [
    "<b>Case date</b> is today by default. Change it if the case was on another day.",
    "Type the <b>Fee</b> in rupees (numbers only, e.g. 9000).",
    "Type the <b>Patient name</b> (optional).",
    "<b>Surgeon</b>: tap the box and type a few letters (e.g. <i>kul</i> finds Dr. Neha Kulkarni). "
    "Surgeons who called you to this hospital before are listed first, and the last one is picked for you.",
], img="22-add-case-filled")
topic("New surgeon?", [
    "Tap <b>New surgeon</b> next to the Surgeon box.",
    "Type the surgeon's name and (optionally) mobile number.",
    "When you save the case, the surgeon is added to the practice list and linked to this hospital. "
    "Next time just pick them from the list.",
], img="23-new-surgeon", tip="The same surgeon can be linked to many hospitals - the app keeps one link for each hospital.")
topic("Step 4 - Contact person (who to call for payment)", [
    "Choose the <b>Contact person</b> (billing / accounts person). Contacts at this hospital are shown first.",
    "New person? Tap <b>New contact</b> and type the name and mobile number.",
    "<b>Android phones:</b> tap <b>Pick from phone contacts</b> to fill the name and number from your phone book in one tap.",
], img="24-new-contact", img2="25-contact-picked", caption="Tap New contact", caption2="Picked from phone contacts",
   note="'Pick from phone contacts' works in Chrome on Android. If it cannot work (iPhone, another browser, or Contacts permission "
        "switched off), a short note under the button says why and what to do - you can always type the name and number.")
topic("Step 5 - Procedure, reference, payment date", [
    "<b>Procedure / case type</b>, e.g. <i>TKR - spinal</i> (suggestions appear as you type).",
    "<b>Case / patient ref</b> - IP number or bill number (optional).",
    "<b>Expected payment date</b> - when you expect to be paid. Leave empty to use 30 days. "
    "<b>You get a payment reminder on this date</b> if the case is not fully paid.",
    "Already paid on the spot? Switch on <b>Payment already received</b> and enter the amount and mode.",
    "<b>Notes</b> - anything else (tap to open).",
], img="26-add-case-lower")
topic("Step 6 - Save", [
    "Tap <b>Save case</b>. Or tap <b>Save &amp; add</b> to save and start the next case for the same hospital.",
    "If you left the expected payment date empty, a small message says the app will assume <b>30 days</b>. "
    "Tap <b>OK, save</b>, or <b>Set a date</b> to choose one.",
    "A green message confirms the case is saved.",
], img="27-due-date-popup", img2="28-case-saved", caption="30-day message", caption2="Case saved",
   tip="You can change the expected payment date later by editing the case.")

# --------------------------------------------------------------------------- bulk upload
sec("bulk", "5. Bulk upload (many cases from Excel)")
topic("Download the template, fill it, upload it", [
    "Open <b>Add Case</b> → tap <b>Bulk upload</b> (top right).",
    "Tap <b>Download Excel template</b> and open it in Excel or Google Sheets.",
    "Enter one case per row. Required columns: <b>Case Date</b>, <b>Hospital</b>, <b>Fee</b>. "
    "<b>Anaesthetist</b>: leave empty for your own cases, or pick a colleague from the drop-down.",
    "Save the file, come back, tap <b>Choose File</b>, pick the file and tap <b>Upload</b>.",
    "If every row is correct, all cases are saved at once and you see a confirmation.",
], img="30-bulk-upload")
topic("If some rows have mistakes", [
    "<b>Nothing is saved</b> - so you never get half an upload.",
    "The rows with problems are shown in <b>pink</b>, and the wrong cell has a <b>red box</b>. "
    "The <b>Problem</b> column (scroll right) says what is wrong.",
    "Fix those cells in Excel, save, and upload the same file again.",
], img="31-bulk-errors", tip="Uploading the same file twice is safe: rows already in the app are skipped.")
table("Template columns", ["Column", "What to type", "Example"], [
    ["Case Date *", "Date of the case (DD/MM/YYYY)", "25/09/2026"],
    ["Hospital *", "Pick from the dropdown, or type a new name (it will be added)", "Ruby Hall Clinic"],
    ["Anaesthetist", "Empty = you. Or pick a colleague who has signed up (drop-down)", "Dr. Vikram Rao"],
    ["Fee *", "Amount in rupees, numbers only", "7500"],
    ["Patient Name", "Patient's name", "Sunita Patil"],
    ["Surgeon", "Surgeon's name (new names are added to the practice list)", "Dr. Amit Shah"],
    ["Procedure / Case Type", "Type of case", "LSCS - spinal"],
    ["Case / Patient Ref", "IP no. or bill no.", "IP 45821"],
    ["Notes", "Anything else", ""],
    ["Amount Received", "Only if already paid (fully or partly)", "7500"],
    ["Payment Date", "When it was paid (default: case date)", "30/09/2026"],
    ["Payment Mode", "UPI, Bank transfer, Cheque, Cash, Card or Other", "UPI"],
])

# --------------------------------------------------------------------------- cases
sec("cases", "6. Cases of the practice")
topic("Find any case", [
    "Tap <b>Cases</b> in the bottom bar.",
    "Type in the search box: <b>patient</b>, <b>surgeon</b>, <b>hospital</b> or <b>IP number</b>.",
    "At the top choose <b>All anaesthetists</b> or one name (marked in red) - e.g. your own name to see only your cases.",
    "Use the filters below it: <b>status</b>, <b>month</b>, <b>hospital</b>, <b>surgeon</b>.",
    "Each row shows the hospital, date, patient, surgeon, anaesthetist, fee and status. Tap a row to open it.",
], img="40-cases-list")
topic("Show only unpaid cases", [
    "In the status filter choose <b>Not fully paid</b>.",
    "Tap <b>clear filters</b> to see everything again.",
], img="41-cases-unpaid")
topic("Case details", [
    "Top: <b>Fee</b>, <b>Received</b> and <b>Outstanding</b>, with the status.",
    "Below: date, expected payment, procedure, patient, hospital, surgeon and contact person.",
    "Tap <b>Call ...</b> to phone the contact for this case.",
    "<b>Edit</b> and <b>Delete</b> buttons are at the top right.",
], img="42-case-detail")
topic("Payments and follow-ups of a case", [
    "Scroll down to see <b>Record payment</b> and <b>Log follow-up</b> buttons.",
    "Every payment received (with who received it) and every follow-up call is listed with its date.",
    "The box above the payments shows the <b>next reminder date</b>, or that a reminder is due now.",
], img="43-case-detail-lower")
topic("Edit a case", [
    "Open the case → tap <b>Edit</b> (top right).",
    "Change what you need and tap <b>Save case</b>.",
    "The edit page also has a red <b>Delete</b> button next to Save case.",
], img="46-edit-case")
topic("Delete a case", [
    "Open the case → tap the red <b>Delete</b> button (top right), or tap <b>Delete</b> on the edit page.",
    "A page asks <b>Delete this case?</b> and shows the hospital, date, patient and fee so you can check it is the right one.",
    "Tap <b>Yes, delete</b> to remove it, or <b>Cancel</b> to keep it.",
], img="46b-delete-confirm", note="Anyone in the practice can edit or delete a case. Deleting a case also deletes its payments and follow-ups. This cannot be undone.")

# --------------------------------------------------------------------------- payments
sec("payments", "7. Recording payments")
topic("Note a payment you received", [
    "Open the case → tap <b>Record payment</b>.",
    "The <b>Amount</b> is filled with what is still due - change it if you received less (a part payment).",
    "Check the <b>Payment date</b> and choose the <b>Mode</b> (UPI, bank transfer, cheque, cash...).",
    "<b>Received by</b> - who received the money, e.g. <i>Dr. Mehta</i> or <i>Clinic reception</i> (optional). "
    "Names you used before are suggested as you type.",
    "Optional: add the transaction / cheque number.",
    "Tap <b>Save payment</b>. The case status updates automatically.",
], img="44-record-payment",
   tip="Got paid in parts? Record each part separately. The case shows Partially Paid until the full fee is received.")

# --------------------------------------------------------------------------- follow-ups
sec("followups", "8. Outstanding money and follow-ups")
topic("Outstanding payments", [
    "Dashboard → tap the <b>Outstanding</b> card.",
    "Top: total outstanding, overdue amount and follow-ups due.",
    "<b>Age of outstanding</b> shows how old the unpaid money is (0-30 days, 31-60, 61-90, 90+).",
    "Use the tabs (<b>All</b>, <b>Follow-up due</b>, <b>Pending</b>, <b>Overdue</b>) and sort buttons to arrange the list.",
], img="47-outstanding")
topic("Overdue payments", [
    "Dashboard → tap the <b>Overdue</b> card.",
    "Each row shows how many days the payment is overdue.",
    "Tap the green phone icon to call the right contact.",
], img="48-overdue")
topic("Mark a follow-up quickly", [
    "Dashboard → tap <b>Follow-ups</b>.",
    "Tap the <b>⋯</b> button on a case.",
    "<b>Mark followed up today</b> - you have called; the reminder is cleared.",
    "<b>Remind me in 3 days / 1 week / 2 weeks</b> - the reminder disappears now and comes back on that day.",
], img="49-followup-menu")
topic("Write down what the hospital said", [
    "Open the case → <b>Log follow-up</b>.",
    "Choose the date, how you contacted them (call, WhatsApp...) and <b>who you spoke to</b>.",
    "Write what they said in <b>Notes</b>.",
    "If they promised a date, enter <b>Promised payment date</b>.",
    "Want another reminder? Choose a date in <b>Remind me again on</b>. You get a reminder on that date. "
    "(If you leave it empty but entered a promised date, you are reminded on the promised date.)",
], img="45-follow-up", tip="This is how you add extra reminders for a case - as many as you need, one follow-up at a time.")
table("How reminders work", ["You get a reminder...", "When"], [
    ["On the <b>expected payment date</b>", "The date you entered on the case. If you left it empty: 30 days after the case date."],
    ["On a date <b>you</b> choose", "<b>Log follow-up</b> → <b>Remind me again on</b>, or <b>⋯</b> → <b>Remind me in 3 days / 1 week / 2 weeks</b>."],
    ["Nothing else", "No automatic 7 / 14 / 21-day reminders. A fully paid case never reminds you."],
], after=None)
para("A reminder arrives on your phone at your <b>notification time</b> (9:00 AM unless you changed it) and the case "
     "shows under <b>Follow-ups</b>. Logging a follow-up clears it.")

# --------------------------------------------------------------------------- hospitals
sec("hospitals", "9. Hospitals")
topic("My hospitals", [
    "Tap <b>Hospitals</b> in the bottom bar.",
    "You see the hospitals you work with, with the amount outstanding at each.",
    "Use the search box to find <b>any</b> hospital in the list (about 90 Pune and Mumbai hospitals are included).",
    "Tap <b>+ Add hospital</b> if one is missing.",
], img="50-hospitals", img2="51-hospital-search", caption="My hospitals", caption2="Search all hospitals")
topic("Hospital page", [
    "Address, type and main phone of the hospital.",
    "<b>Contacts here</b> - the practice's contacts at this hospital, with a call button.",
    "Number of cases and outstanding amount there, and recent cases.",
    "<b>Add case here</b> and <b>Add contact here</b> buttons save typing.",
], img="52-hospital-detail")

# --------------------------------------------------------------------------- contacts & surgeons
sec("people", "10. Contacts and surgeons", "Both lists are shared by the whole practice: a contact or surgeon added by one person is available to everyone.")
topic("Your contacts", [
    "Profile menu → <b>Contacts &amp; surgeons</b>. Use the <b>Contacts</b> / <b>Surgeons</b> tabs at the top.",
    "Each contact shows their role and hospital. Tap the green phone icon to call.",
    "Tap <b>+ Add contact</b> to add someone. Contacts are also added automatically when you use "
    "<b>New contact</b> on Add Case.",
], img="60-contacts")
topic("Contact page - when someone changes hospital", [
    "Open a contact to see where they work and the cases linked to them.",
    "Moved to another hospital? Tap <b>Add a hospital / moved to another hospital</b>, pick the new hospital "
    "and tick <b>They moved here</b>. Old cases keep the history.",
    "<b>⋯</b> next to a hospital: make them the <b>main contact</b> there, or mark <b>no longer works here</b>.",
], img="61-contact-detail")
topic("Add a contact", [
    "Fill in <b>Name</b>, <b>Role</b> and <b>Mobile</b>.",
    "Android: <b>Pick from phone contacts</b> fills name and mobile for you.",
    "Optionally choose the hospital they work at, then tap <b>Save contact</b>.",
], img="62-add-contact")
topic("Your surgeons", [
    "Profile menu → <b>Contacts &amp; surgeons</b> → <b>Surgeons</b> tab.",
    "Each surgeon shows how many cases they called you for, and at which hospitals.",
    "Search box: every word counts - <i>shah ruby</i> finds Dr. Shah at Ruby Hall; <i>ortho</i> finds surgeons by speciality.",
    "Tap <b>+ Add surgeon</b> to add one (surgeons are also added from Add Case).",
], img="63-surgeons")
topic("Surgeon page", [
    "<b>Calls you to</b> - each hospital this surgeon calls you from, with cases and amount billed there.",
    "Add another hospital with the <b>Hospital</b> box and <b>+ Add hospital</b>; remove one with <b>×</b>.",
    "Recent cases with this surgeon are listed below. Tap <b>Edit</b> to change name, mobile or speciality.",
], img="64-surgeon-detail", img2="65-add-surgeon", caption="Surgeon page", caption2="Add surgeon")

# --------------------------------------------------------------------------- reports
sec("reports", "11. Reports and Excel downloads")
topic("Choose a report", [
    "Tap <b>Reports</b> in the bottom bar.",
    "Every report has filters at the top and a green <b>Download Excel</b> button.",
    "Choose a <b>Period</b>: this month, last month, last 3 months, this FY, last FY, last 12 months, all time "
    "or <b>Custom dates</b>.",
], img="70-reports")
topic("Cases report", [
    "All cases matching your filters: period, hospital, surgeon, payment status and search.",
    "Tap <b>Apply filters</b>, then <b>Download Excel</b> for the full list with patient, surgeon, contact, "
    "fee, received, outstanding and status.",
], img="71-cases-report")
topic("Monthly summary and month page", [
    "<b>Monthly summary</b> shows cases, billed, received and outstanding for each month.",
    "Tap a <b>month</b> to open its own page with only three filters: <b>Hospital</b>, <b>Surgeon</b>, "
    "<b>Payment status</b>.",
    "Use the <b>‹ ›</b> arrows to move to the previous or next month, and <b>Download Excel</b> for that month.",
], img="72-monthly", img2="73-month-page", caption="Tap a month", caption2="Month page")
topic("Hospital-wise billing", [
    "Billed, received, outstanding and overdue amount for each hospital.",
    "Sort by <b>Outstanding</b>, <b>Billed</b> or <b>Cases</b>. Tap a hospital to see its cases.",
], img="74-hospital-wise")
topic("Surgeon & hospital", [
    "How many cases each surgeon called you for <b>at each hospital</b>, with billed, received and outstanding.",
    "Filter by <b>Surgeon</b> and <b>Hospital</b> together to answer: "
    "<i>“How many cases did Dr. Shah call me for at Ruby Hall this year?”</i>",
], img="75-surgeon-hospital")
topic("Payment history", [
    "Every payment you received in the period, with total and a split by payment mode.",
    "Filter by hospital, surgeon or mode (e.g. only cheques). Search also finds <b>Received by</b> names.",
    "The Excel download has a <b>Received by</b> column.",
], img="76-payment-history", tip="Download the payment history at the end of each month for your CA.")

# --------------------------------------------------------------------------- notifications
sec("notify", "12. Reminders on your phone")
topic("Turn on notifications", [
    "Profile menu → <b>Notification settings</b> (or tap <b>Turn on</b> on the Dashboard).",
    "Allow notifications when your phone asks.",
    "Choose what you want: <b>Payment reminders</b> (expected date and your reminder dates), <b>Morning summary</b>, "
    "<b>Weekly report</b>, <b>Payment updates</b>.",
    "<b>Remind me about</b> (marked in red): <b>Only my cases</b> (default), a colleague's cases, or <b>All cases of the practice</b>.",
    "Set the <b>Notification time</b> (default 9:00 AM) and tap <b>Save notification settings</b>.",
    "Tap <b>Send a test</b> to check it works.",
    "Check the <b>Automatic reminders</b> box: it must say <b>Reminder sender is running</b>. "
    "It also shows your next reminder dates.",
], img="80-notifications",
   note="On iPhone, notifications work only when the app is added to the Home Screen (iOS 16.4 or later).")

# --------------------------------------------------------------------------- admin
sec("admin", "13. For the administrator", "This section is only for the person who manages the app for the practice. "
    "The administrator has a separate login (for example <i>admin</i>) and manages logins, settings and the hospital list. "
    "Anaesthetists never see these screens.")
topic("Sign in as administrator", [
    "On the sign-in page type the <b>administrator User ID</b> and <b>password</b> given to you.",
    "Tap <b>Sign in</b>.",
    "Keep this login private - it can manage every account.",
], img="90-admin-login", note="The administrator password cannot be recovered with 'Forgot password' (that needs a doctor's mobile number). "
   "If it is lost, ask your technical support person to reset it.")
topic("Administrator dashboard", [
    "Works like everyone's dashboard, with the <b>anaesthetist filter</b> at the top.",
    "The same filter appears on Cases, Outstanding and Reports.",
], img="91-admin-dashboard")
topic("Administrator menu", [
    "Tap the round profile icon (top right). Next to your name is an orange <b>Admin</b> label.",
    "<b>Anaesthetists</b> - everyone's login.",
    "<b>Settings</b> - default payment terms and sign-up rules for the whole app.",
    "<b>Hospital directory</b> - load the government hospital list.",
], img="92-admin-menu")
topic("Anaesthetists", [
    "Lists every anaesthetist with User ID and mobile number.",
    "Tap <b>+ Add anaesthetist</b> to create a login for someone (or let them sign up themselves).",
    "Tap a name to change it, the mobile number or email, set a <b>new password</b> for someone who is locked out, "
    "or switch the account <b>Active</b> off for someone who left (their old cases stay).",
], img="93-doctors", img2="94-doctor-edit", caption="Anaesthetists", caption2="Edit",
   tip="New sign-ups that need approval appear here. Switch on Active to let them sign in.")
topic("Add a case as administrator", [
    "The administrator login is not an anaesthetist, so there is no <b>Self</b>: choose the <b>Anaesthetist</b> first.",
    "The rest of the form is the same as in section 4.",
    "<b>Bulk upload</b> works too: choose the anaesthetist on the upload page, or fill the <b>Anaesthetist</b> column.",
], img="96-admin-add-case")
topic("Settings", [
    "<b>Practice name</b> - shown in the app.",
    "<b>Default payment terms</b> - days assumed when no expected payment date is entered (30). "
    "The payment reminder comes on that day.",
    "<b>Sign-ups</b> - allow doctors to create their own accounts, and whether new accounts need your approval.",
    "Tap <b>Save settings</b> at the bottom.",
], img="97-settings")
topic("Hospital directory", [
    "Shows how many hospitals are in the shared list and where they came from.",
    "To add many hospitals at once, upload an Excel/CSV sheet with the columns <b>Hospital Name</b> and <b>District</b> "
    "(optional: Location, Address, Pincode, Telephone). The data.gov.in hospital file works too. "
    "Only the districts you list (Pune, Mumbai by default) are added.",
], img="98-directory-import")
topic("Merge duplicate hospitals", [
    "Same hospital added twice (e.g. <i>Seatherney</i> and <i>Seatherney Hospital</i>)? Hospital directory → "
    "<b>Possible duplicates</b>, or <b>Merge</b> on a hospital's page.",
    "For each group choose the hospital to <b>Keep</b>, tick the ones to <b>Merge</b>, tap <b>Merge selected</b>.",
    "The next page shows exactly what moves (cases, contacts, surgeons). Tap <b>Yes, merge</b>.",
    "Cases with their payments and follow-ups, contacts and surgeons move to the kept hospital. The other "
    "spelling is saved as an <b>Other name</b>, so searching it still finds the hospital.",
    "Nothing is deleted. Made a mistake? <b>Merge history</b> → <b>Undo</b> puts everything back.",
], img="99-duplicates", img2="99b-merge-confirm", caption="Possible duplicates", caption2="Confirm merge",
   note="Only the administrator can merge. Tip: run <b>payments backup</b> on the server before a large clean-up.")

# --------------------------------------------------------------------------- FAQ
sec("faq", "14. Questions and quick help")
table("Common questions", ["Question", "Answer"], [
    ["I entered the wrong fee or date.", "Open the case → <b>Edit</b> → correct it → <b>Save case</b>."],
    ["I recorded a payment twice.", "Open the case, tap the wrong payment in the Payments list, then tap the <b>bin</b> button to delete it."],
    ["The hospital paid only part of the fee.", "Record what you received. The case stays <b>Partially Paid</b> until the rest comes in."],
    ["The hospital promised to pay on a date.", "<b>Log follow-up</b> and enter the <b>Promised payment date</b>. You are reminded on that date."],
    ["I did not get a notification.", "Reminders come only on the expected payment date (or a date you set), at your notification time. "
     "Open <b>Notification settings</b>: <b>Send a test</b> must arrive, and the <b>Automatic reminders</b> box must say "
     "<b>Reminder sender is running</b>. If it says it has not run, tell your administrator."],
    ["I can't find a hospital.", "Try fewer letters or the area name, and look under <b>Did you mean?</b>. Still missing? Tap <b>Add a hospital not in the list</b>."],
    ["The same hospital is in the list twice.", "Tell the administrator - they merge the two (all cases are kept, and it can be undone)."],
    ["The surgeon list is empty for a hospital.", "Use <b>New surgeon</b> once; next time they appear first for that hospital."],
    ["My bulk upload saved nothing.", "Some rows had mistakes. Fix the red cells and upload the same file again."],
    ["I see an old version of a screen.", "Close the app fully and open it again (or pull down to refresh)."],
    ["I changed my phone.", "Open the app link on the new phone, sign in, and add it to the home screen again. Your data is safe on the server."],
    ["Can my colleagues see my cases?", "Yes. The whole practice shares one list of cases, contacts and surgeons. Use the <b>anaesthetist</b> filter to see only your own."],
    ["I entered a case under the wrong anaesthetist.", "Open the case → <b>Edit</b> → change <b>Anaesthetist</b> → <b>Save case</b>."],
    ["A colleague's name is not in the Anaesthetist list.", "They must sign up first (<b>Create an account</b> on the sign-in page). Then their name appears for everyone."],
    ["The app asked me to sign in again.", "For safety everyone is signed out 30 days after signing in. Sign in again - nothing is lost."],
    ["The administrator forgot the password.", "Ask your technical support person to reset it (Forgot password works only for doctor accounts)."],
])
table("Quick reference", ["Task", "Steps"], [
    ["Add a case", "+ Add Case → (Anaesthetist: Self) → Hospital → Fee → Surgeon → Save case"],
    ["Case for a colleague", "+ Add Case → Anaesthetist → pick name → ..."],
    ["Record a payment", "Cases → open case → Record payment → Save payment"],
    ["Delete a case", "Cases → open case → Delete → Yes, delete"],
    ["Call about a payment", "Dashboard → Follow-ups → phone icon"],
    ["Mark as followed up", "Follow-ups → ⋯ → Mark followed up today"],
    ["Excel of a month", "Reports → Monthly summary → tap month → Download Excel"],
    ["Cases per surgeon", "Reports → Surgeon &amp; hospital"],
    ["Forgot User ID / password", "Sign-in page → Forgot user ID? / Forgot password? → mobile number"],
    ["Change password", "Profile menu → Change password"],
])


# ----------------------------------------------------------------------------- render
def img_tag(name, caption=None):
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f"<figure><img src='img/{name}.jpg'>{cap}</figure>"


out = []
toc = "".join(f"<li><a href='#{s['id']}'>{s['title']}</a></li>" for s in SECTIONS)
fig_no = 0
for s in SECTIONS:
    out.append(f"<section id='{s['id']}'><h1>{s['title']}</h1>")
    if s["intro"]:
        out.append(f"<p class='intro'>{s['intro']}</p>")
    for b in s["blocks"]:
        if b["kind"] == "para":
            out.append(f"<p class='para'>{b['text']}</p>")
        elif b["kind"] == "table":
            head = "".join(f"<th>{h}</th>" for h in b["head"])
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in b["rows"])
            out.append(f"<div class='tblock'><h2>{b['title']}</h2><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>")
        else:
            steps = "".join(f"<li>{x}</li>" for x in b["steps"])
            extra = ""
            if b["tip"]:
                extra += f"<div class='tip'><b>Tip</b> {b['tip']}</div>"
            if b["note"]:
                extra += f"<div class='note'><b>Note</b> {b['note']}</div>"
            imgs = ""
            if b["img"]:
                imgs = img_tag(b["img"], b["caption"]) + (img_tag(b["img2"], b["caption2"]) if b["img2"] else "")
            cls = "topic two" if b["img2"] else ("topic" if b["img"] else "topic noimg")
            out.append(f"<div class='{cls}'><div class='text'><h2>{b['title']}</h2><ol>{steps}</ol>{extra}</div>"
                       f"<div class='shots'>{imgs}</div></div>")
    out.append("</section>")

CSS = """
@page { size: A4; margin: 16mm 14mm 16mm 14mm; }
* { box-sizing: border-box; }
body { font-family: 'Noto Sans', 'DejaVu Sans', Arial, sans-serif; color: #1f2937; font-size: 10.5pt; line-height: 1.45; margin: 0; }
.cover { height: 260mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always;
         background: linear-gradient(160deg, #eef0fb 0%, #fff 60%); border-radius: 10px; padding: 0 18mm; }
.cover .logo { width: 96px; height: 96px; border-radius: 22px;
               display: flex; align-items: center; justify-content: center; font-weight: 700; }
.cover h1 { font-size: 32pt; color: #2e2a6e; margin: 18px 0 6px; border: 0; }
.cover .sub { font-size: 15pt; color: #555; }
.cover .meta { margin-top: 40px; color: #666; font-size: 10.5pt; }
.toc { page-break-after: always; }
.toc h1 { border: 0; }
.toc ol { font-size: 12.5pt; line-height: 2.0; }
.toc a { color: #2e2a6e; text-decoration: none; }
section { page-break-before: always; }
h1 { color: #2e2a6e; font-size: 20pt; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 3px solid #f5b83d; }
h2 { color: #2e2a6e; font-size: 12.5pt; margin: 0 0 6px; }
.intro { font-size: 11.5pt; color: #444; margin: 4px 0 12px; }
.para { background: #f6f7fb; border-radius: 8px; padding: 8px 12px; margin: 8px 0 12px; break-inside: avoid; }
.topic { display: flex; gap: 14px; align-items: flex-start; padding: 10px 0 14px; border-bottom: 1px solid #eceef3; break-inside: avoid; }
.topic .text { flex: 1 1 auto; min-width: 0; }
.topic .shots { flex: 0 0 62mm; display: flex; gap: 6px; justify-content: flex-end; }
.topic.two .shots { flex-basis: 108mm; }
.topic.noimg .shots { display: none; }
figure { margin: 0; text-align: center; }
figure img { max-height: 150mm; object-fit: cover; object-position: top; width: 52mm; border: 1px solid #d5d8e0; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,.08); display: block; }
.topic:not(.two) figure img { width: 60mm; }
figcaption { font-size: 8.5pt; color: #666; margin-top: 3px; }
ol { margin: 0; padding-left: 18px; }
ol li { margin-bottom: 4px; }
.tip, .note { margin-top: 8px; padding: 6px 10px; border-radius: 6px; font-size: 9.8pt; }
.tip { background: #ecfdf3; border-left: 4px solid #2f9e62; }
.note { background: #fff7e6; border-left: 4px solid #f5b83d; }
.tip b, .note b { margin-right: 4px; }
.tblock { margin: 10px 0 14px; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
th { background: #2e2a6e; color: #fff; text-align: left; padding: 6px 8px; font-weight: 600; }
td { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
tr:nth-child(even) td { background: #f8f9fc; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 9pt; font-weight: 600; }
.pill.grey { background: #eceef3; color: #475467; } .pill.blue { background: #e5edff; color: #3346a6; }
.pill.green { background: #e3f6ea; color: #23784a; } .pill.red { background: #fde8e8; color: #b42318; }
"""

LOGO = "data:image/png;base64," + base64.b64encode((pathlib.Path(__file__).parent / "logo.png").read_bytes()).decode()

page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Team Anesthesia - User Manual</title><style>{CSS}</style></head><body>
<div class='cover'>
  <img class='logo' src='{LOGO}' alt=''>
  <h1>Team Anesthesia</h1>
  <div class='sub'>User manual for the practice</div>
  <div class='sub' style='font-size:12pt;margin-top:8px'>Cases · Payments · Follow-ups · Reports</div>
  <div class='meta'>Step-by-step guide with screenshots of every screen.<br>Version: October 2026 · Final</div>
</div>
<div class='toc'><h1>Contents</h1><ol style='list-style:none;padding-left:0'>{toc}</ol></div>
{''.join(out)}
</body></html>"""
open("manual.html", "w", encoding="utf-8").write(page)
print("sections", len(SECTIONS), "topics", sum(1 for s in SECTIONS for b in s["blocks"] if b["kind"] == "topic"))
