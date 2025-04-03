from datetime import datetime
import pytz
import re

def extract_display_names(message):
    matches = re.findall(r'\[(.*?)\]', message)
    return matches if matches else []

def format_datetime(dt_str):
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    est = pytz.timezone('US/Eastern')
    return dt.astimezone(est).strftime("%Y-%m-%d %H:%M:%S EDT")