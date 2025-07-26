import datetime as dt
import json

import streamlit as st
from logging_config import setup_logging


logger = setup_logging(__name__)

sync_file = "last_sync_state.json"
with open(sync_file, "r") as f:
    saved_sync_state = json.load(f)


def initialize_sync_state():
    last_saved_sync = dt.datetime.strptime(saved_sync_state['last_sync'], "%Y-%m-%d %H:%M %Z").replace(tzinfo=dt.UTC)
    next_saved_sync = dt.datetime.strptime(saved_sync_state['next_sync'], "%Y-%m-%d %H:%M %Z").replace(tzinfo=dt.UTC)

    print(last_saved_sync)
    print(f"next_sync: {next_saved_sync}")

    logger.info("session state sync_status not found, initializing")
    st.session_state.sync_status = "Not yet run"
    logger.info(f"sync_status initialized to: {st.session_state.sync_status}")

    st.session_state['last_sync'] = last_saved_sync
    st.session_state['next_sync'] = next_saved_sync

    logger.info(f"sync_status: {st.session_state.sync_status}")
    logger.info(f"last_sync: {st.session_state.last_sync}")
    logger.info(f"next_sync: {st.session_state.next_sync}")

def get_next_sync():
    with open(sync_file, "r") as f:
        saved_sync_state = json.load(f)

    stimes = saved_sync_state['sync_times']
    now = dt.datetime.now(dt.UTC)
  
    yt = [dt.datetime.strptime(t, "%H:%M").replace(tzinfo=dt.UTC, day=now.day, month=now.month, year=now.year) for t in stimes]
    future = [t for t in yt if t > now]

    next_sync = min(future)
    return next_sync

def check_sync_status():
    """Check if a sync is needed based on the next scheduled sync time"""
    now = dt.datetime.now(dt.UTC)
    
    # If we don't have a last sync time, we should sync
    if not st.session_state.get('last_sync'):
        logger.info("check_sync_status: last_sync not found in session state, syncing")
        return True
        
    # If we've passed the next sync time, we should sync
    if now >= st.session_state.next_sync:
        logger.info("check_sync_status: now >= next_sync, syncing")
        return True
        
    # If we're within 1 minute of the next sync time, we should sync
    time_to_next = st.session_state.next_sync - now
    if time_to_next.total_seconds() <= 60:
        logger.info("check_sync_status: time_to_next <= 60, syncing")
        return True
    
    logger.info("check_sync_status: no sync needed")
    return False

def update_sync_status(sync_status:str):
    st.session_state.sync_status = sync_status
    st.session_state.last_sync = dt.datetime.now(dt.UTC)
    st.session_state.next_sync = get_next_sync()

    updated_sync_state = {
        "last_sync": st.session_state.last_sync.strftime("%Y-%m-%d %H:%M %Z"),
        "next_sync": st.session_state.next_sync.strftime("%Y-%m-%d %H:%M %Z")   ,
        "sync_status": st.session_state.sync_status,
        "sync_times": saved_sync_state['sync_times']
    }

    logger.info(f"updated_sync_state: {updated_sync_state}")
    logger.info(f"sync_file: {sync_file}")
    
    with open(sync_file, "w") as f:
        json.dump(updated_sync_state, f)

if __name__ == "__main__":
    pass
