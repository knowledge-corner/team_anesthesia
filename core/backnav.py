"""Back button that behaves like a normal website.

A form (Record payment, Edit case, ...) carries a hidden `back_nav` field filled in by
app.js: "<errors>|<form page>|<page it was opened from>". After a successful save, if
the page to show next is the form page itself or the page the form was opened from,
the browser steps back in its history to it instead of opening it again. The finished
form then drops out of the history, so the next Back goes where the doctor came from
(e.g. the filtered Cases list), not to the form or a second copy of the case.
"""
from urllib.parse import parse_qsl, urlsplit

from django.shortcuts import redirect, render


def _same(a, b):
    a, b = urlsplit(a or ""), urlsplit(b or "")
    return a.path == b.path and sorted(parse_qsl(a.query, True)) == sorted(parse_qsl(b.query, True))


def back_steps(request, target):
    parts = request.POST.get("back_nav", "").split("|", 2)
    if len(parts) != 3 or not parts[0].isdigit():
        return 0
    errors, here, came_from = int(parts[0]), parts[1], parts[2]
    if here and _same(target, here):
        return 1 + errors
    if came_from and _same(target, came_from):
        return 2 + errors
    return 0


def finish(request, target):
    """Show `target` after a successful form: step back to it if it is right behind us."""
    target = str(target)
    steps = back_steps(request, target)
    if steps and steps < 10:
        return render(request, "go_back.html", {"steps": steps, "target": target})
    return redirect(target)
