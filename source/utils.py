import json
import socket
import datetime

from calendar import monthrange

import urllib.request

def _format_json(dictionary):
    return json.dumps(dictionary, indent=4, sort_keys=True)

def truncate(n, decimals=0):
    multiplier = 10 ** decimals
    return int(n * multiplier) / multiplier

def get_current_date(current=True):
    now = datetime.date.today()
    year = now.year
    month = now.month
    if not current:
        month = month - 1
    _, last_day_in_month = monthrange(year, month)
    return year, month, last_day_in_month