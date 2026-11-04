"""
Receivables and follow-up business rules.

Kept free of request/response code so the same logic can back a future
REST API or native app.
"""
import datetime
from dataclasses import dataclass

from django.utils import timezone

from cases.models import Case


@dataclass
class ReminderState:
    due: bool
    last_trigger: datetime.date | None  # most recent reminder date already reached
    next_trigger: datetime.date | None  # next upcoming reminder date
    snoozed_until: datetime.date | None  # a reminder date set by the doctor that is still ahead


def reminder_dates(case):
    """A case reminds on two kinds of dates only:

    1. its expected payment date (30 days after the case date when none was entered), and
    2. a "remind me on" date the doctor set in a follow-up (or with "Remind me in ...").
    """
    return sorted({d for d in (case.due_date, case.followup_snoozed_until) if d})


def reminder_state(case, today=None):
    """Is a payment reminder due for this case today?

    Due once a reminder date is reached, the case is not fully paid and no follow-up
    has been logged on/after that date. Logging a follow-up clears it until the next
    reminder date (if any).
    """
    today = today or timezone.localdate()
    dates = reminder_dates(case)
    reached = [d for d in dates if d <= today]
    upcoming = [d for d in dates if d > today]
    last_trigger = reached[-1] if reached else None
    next_trigger = upcoming[0] if upcoming else None
    custom = case.followup_snoozed_until if (
        case.followup_snoozed_until and case.followup_snoozed_until > today
    ) else None

    last_followup = getattr(case, "last_followup_date", None)
    if last_followup is None and not hasattr(case, "last_followup_date"):
        latest = case.followups.order_by("-followup_date").first()
        last_followup = latest.followup_date if latest else None

    due = (
        case.open_case
        and last_trigger is not None
        and custom is None
        and (last_followup is None or last_followup < last_trigger)
    )
    return ReminderState(due=due, last_trigger=last_trigger, next_trigger=next_trigger, snoozed_until=custom)


def receivables_for(user, today=None):
    """Outstanding cases visible to `user`, annotated with totals, age and reminder state."""
    today = today or timezone.localdate()
    cases = list(
        Case.objects.for_user(user)
        .with_totals(today)
        .with_last_followup()
        .filter(is_open=True)
        .select_related("hospital", "doctor", "surgeon")
        .order_by("case_date", "id")
    )
    for case in cases:
        case.reminder = reminder_state(case, today)
    return cases


def snooze(case, days):
    """'Remind me in N days': hide the reminder now and raise it again on that date."""
    case.followup_snoozed_until = timezone.localdate() + datetime.timedelta(days=days)
    case.save(update_fields=["followup_snoozed_until", "updated_at"])


def apply_followup(followup):
    """After a follow-up is logged: the next reminder is the date the doctor chose,
    else the promised payment date, else none (until the expected date, if still ahead)."""
    case = followup.case
    today = timezone.localdate()
    nxt = followup.next_reminder or followup.promised_payment_date
    case.followup_snoozed_until = nxt if nxt and nxt > today else None
    case.save(update_fields=["followup_snoozed_until", "updated_at"])
