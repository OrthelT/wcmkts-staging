import datetime as dt
import json
import os
import time
import streamlit as st
from logging_config import setup_logging
from sync_state import sync_state
from db_handler import get_time_since_esi_update, get_time_until_next_update

logger = setup_logging(__name__)

sync_info = sync_state()
last_sync = sync_info['last_sync']
next_sync = sync_info['next_sync']
sync_check = sync_info['sync_check']

def initialize_sync_state():
    if 'sync_status' not in st.session_state:
        st.session_state.sync_status = "Not yet run"
    if 'last_sync' not in st.session_state:
        st.session_state.last_sync = last_sync
        st.session_state.next_sync = next_sync


#cache for 15 minutes
@st.cache_data(ttl=900)
def check_sync_status():
    """Check if a sync is needed based on the next scheduled sync time"""
    now = dt.datetime.now(dt.UTC)

    # If we don't have a last sync time, we should sync
    if not st.session_state.get('last_sync'):
        return True

    # If we've passed the next sync time, we should sync
    if now >= st.session_state.next_sync:
        return True

    # If we're within 1 minute of the next sync time, we should sync
    time_to_next = st.session_state.next_sync - now
    if time_to_next.total_seconds() <= 60:
        return True

    return False

def schedule_next_sync(last_sync: dt.datetime) -> dt.datetime:
    """Schedule the next sync based on the sync times in last_sync_state.json"""
    now = dt.datetime.now(dt.UTC)
    sync_times = saved_sync_state['sync_times']

    # Convert sync times to today's datetime objects
    today_sync_times = []
    for time_str in sync_times:
        hour, minute = map(int, time_str.split(':'))
        sync_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If the time is earlier in the day and we've passed it, schedule it for tomorrow
        if sync_time < now:
            sync_time += dt.timedelta(days=1)

        today_sync_times.append(sync_time)

    # Sort sync times
    today_sync_times.sort()

    # Find the next sync time
    for sync_time in today_sync_times:
        if sync_time > now:
            logger.info(f"Next sync time: {sync_time}, timezone: {sync_time.tzname()}")
            return sync_time

    # If no sync times are left today, get the first time for tomorrow
    if today_sync_times:
        logger.info(f"No sync times left for today. Next sync time: {today_sync_times[0]}, timezone: {today_sync_times[0].tzname()}")
        return today_sync_times[0]

    # Fallback: if no sync times defined, schedule for 3 hours from now
    return now + dt.timedelta(hours=3)

if __name__ == "__main__":
    pass