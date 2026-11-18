"""Cases paid a moment ago stay visible in filtered lists ("Paid just now"),
so after recording a payment the doctor sees it worked instead of the case vanishing."""
import time

KEY = "just_paid"
KEEP_SECONDS = 30 * 60


def mark_paid(request, case_ids):
    now = int(time.time())
    data = {k: v for k, v in request.session.get(KEY, {}).items() if now - v < KEEP_SECONDS}
    for pk in case_ids:
        data[str(pk)] = now
    request.session[KEY] = data


def just_paid_ids(request):
    now = int(time.time())
    return {int(k) for k, v in request.session.get(KEY, {}).items() if now - v < KEEP_SECONDS}
