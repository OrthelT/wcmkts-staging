import streamlit as st
import datetime as dt
import json
import os
from logging_config import setup_logging

logger = setup_logging(__name__)

# Static sync times every 2 hours starting at 12:00
SYNC_TIMES = ["12:00", "14:00", "16:00", "18:00", "20:00", "22:00", "00:00", "02:00", "04:00", "06:00", "08:00", "10:00"]

def sync_state(sync_time: dt.datetime = None) -> dict:
    """
    Manages database synchronization state with 2-hour intervals.

    Args:
        sync_time: Optional datetime object for the current sync time.
                  If provided, updates last_sync. If None, only checks sync status.

    Returns:
        dict: Contains last_sync, next_sync, and sync_status
    """
    # Use current time for calculations
    current_time = dt.datetime.now(dt.timezone.utc)

    # Load existing state or create default
    json_file = "last_sync_state.json"
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r') as f:
                saved_sync = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            saved_sync = {
                "last_sync": "2025-01-01 00:00 UTC",
                "next_sync": "2025-01-01 12:00 UTC",
                "sync_times": SYNC_TIMES
            }
    else:
        saved_sync = {
            "last_sync": "2025-01-01 00:00 UTC",
            "next_sync": "2025-01-01 12:00 UTC",
            "sync_times": SYNC_TIMES
        }

    if sync_time is not None:
        st.session_state.last_sync = sync_time
        current_sync_str = sync_time.strftime("%Y-%m-%d %H:%M UTC")
        saved_sync["last_sync"] = current_sync_str
        logger.info(f"saved_sync: {saved_sync}")
        logger.info(f"current_sync_str: {current_sync_str}")
    else:
        current_sync_str = saved_sync["last_sync"]

    # Parse the last_sync time (now updated if sync_time was provided)
    last_sync_datetime = dt.datetime.strptime(saved_sync["last_sync"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=dt.timezone.utc)
    logger.info(f"last_sync_datetime: {last_sync_datetime}")

    # Check if we need to sync based on last_sync time
    # If last_sync was more than 2 hours ago, we need to sync
    time_since_last_sync = current_time - last_sync_datetime
    sync_status = time_since_last_sync >= dt.timedelta(hours=2)
    logger.info(f"sync_status: {sync_status}")
    logger.info(f"time_since_last_sync: {time_since_last_sync}")
    # If sync is needed, calculate the new next sync time
    if sync_status:
        # Find the next sync time in the schedule
        next_sync_datetime = None

        for time_str in SYNC_TIMES:
            hour = int(time_str.split(':')[0])

            # Calculate the datetime for this sync time today
            potential_sync = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)

            # If this time has passed today, try tomorrow
            if potential_sync <= current_time:
                potential_sync += dt.timedelta(days=1)

            # Check if this sync time is within 2 hours
            time_diff = potential_sync - current_time
            if time_diff <= dt.timedelta(hours=2):
                next_sync_datetime = potential_sync
                break

        # If no sync time found within 2 hours, use the next available time
        if next_sync_datetime is None:
            for time_str in SYNC_TIMES:
                hour = int(time_str.split(':')[0])
                potential_sync = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)

                if potential_sync <= current_time:
                    potential_sync += dt.timedelta(days=1)

                next_sync_datetime = potential_sync
                break

        next_sync_str = next_sync_datetime.strftime("%Y-%m-%d %H:%M UTC")

        # Update saved_sync with new next_sync time
        saved_sync["next_sync"] = next_sync_str
        saved_sync["sync_times"] = SYNC_TIMES

        logger.info(f"saved_sync: {saved_sync}")
        logger.info(f"current_sync_str: {current_sync_str}")
        logger.info(f"next_sync_str: {next_sync_str}")
        logger.info(f"sync_status: {sync_status}")

        # Write to JSON file
        with open(json_file, 'w') as f:
            json.dump(saved_sync, f, indent=2)
    else:
        # Use existing next_sync time
        next_sync_str = saved_sync["next_sync"]

    # Update session state
    st.session_state["last_sync"] = current_sync_str
    st.session_state["next_sync"] = next_sync_str


    return {
        "last_sync": current_sync_str,
        "next_sync": next_sync_str,
        "sync_check": sync_status
    }

def update_saved_sync():

    sync_info = {
        "last_sync": st.session_state.last_sync,
        "next_sync": st.session_state.next_sync,
        "sync_times": SYNC_TIMES
    }
    with open("last_sync_state.json", "w") as f:
        json.dump(sync_info, f, indent=2)

if __name__ == "__main__":
    # Test the function
    ss = sync_state()
    print(ss)