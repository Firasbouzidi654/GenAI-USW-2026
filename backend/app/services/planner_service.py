from datetime import date


def get_event_priority(event_date: date) -> dict:
    today = date.today()
    days_remaining = (event_date - today).days

    if days_remaining <= 7:
        priority = "URGENT"
    elif days_remaining <= 14:
        priority = "HIGH"
    else:
        priority = "NORMAL"

    return {
        "days_remaining": max(days_remaining, 0),
        "priority": priority,
    }
