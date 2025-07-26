import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import streamlit as st

import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import pytz
from logging_config import setup_logging
import time
import threading
import datetime
from db_utils import sync_db
import json
import libsql_experimental as libsql
import pathlib

# Database URLs
local_mkt_url = "sqlite+libsql:///wcmkt2.db"  # Changed to standard SQLite format for local dev
local_sde_url = "sqlite+libsql:///sde2.db"    # Changed to standard SQLite format for local dev
build_cost_url = "sqlite+libsql:///build_cost.db"
local_mkt_path = pathlib.Path("wcmkt2.db")
local_sde_path = pathlib.Path("sde2.db")
local_build_cost_path = pathlib.Path("build_cost.db")

# Load environment variables
logger = setup_logging(__name__)

# Use environment variables for production
mkt_url = st.secrets["TURSO_DATABASE_URL"]
mkt_auth_token = st.secrets["TURSO_AUTH_TOKEN"]

sde_url = st.secrets["NEW_SDE_URL"]
sde_auth_token = st.secrets["NEW_SDE_AUTH_TOKEN"]

def check_db_exists(db_path):
    if not db_path.exists():
        print(f"Database file {db_path} does not exist, syncing database")
        return False
    else:
        logger.info(f"Database file exists: {db_path}")
        print(f"Database file exists: {db_path}")
        return True

mkt_query = """
    SELECT * FROM marketorders 
    WHERE is_buy_order = 1 
    ORDER BY order_id
"""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def execute_query_with_retry(session, query):
    try:
        result = session.execute(text(query))
        return result.fetchall(), result.keys()
    except Exception as e:
        logger.error(f"Query failed, retrying... Error: {str(e)}")
        raise

@st.cache_data(ttl=600)
def get_mkt_data(base_query):
    mkt_start = time.time()
    logger.info("\n")
    logger.info(f"="*80)
    logger.info(f"getting market data with cache, start time: {mkt_start}")
    
    with Session(get_local_mkt_engine()) as session:
        try:
            result, columns = execute_query_with_retry(session, base_query)
            df = pd.DataFrame(result, columns=columns)
        except Exception as e:
            logger.error(f"Failed to get market data: {str(e)}")
            raise

    mkt_end = time.time()
    logger.info(f"getting market data, end time: {mkt_end}")
    logger.info(f"getting market data, total time: {mkt_end - mkt_start} seconds")
    logger.info(f"="*80)
    logger.info("\n")
    return df

def request_type_names(type_ids):
    logger.info(f"requesting type names with cache")
    # Process in chunks of 1000
    chunk_size = 1000
    all_results = []
    
    for i in range(0, len(type_ids), chunk_size):
        chunk = type_ids[i:i + chunk_size]
        url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
        headers = {
            "Accept": "application/json",
            "User-Agent": "dfexplorer"
        }
        response = requests.post(url, headers=headers, json=chunk)
        all_results.extend(response.json())
    
    return all_results

def insert_type_names(df):
    type_names = request_type_names(df.type_id.unique().tolist())
    df_names = pd.DataFrame(type_names)
    df_names = df_names.drop(columns=['category'])
    df_names = df_names.rename(columns={'id': 'type_id', 'name': 'type_name'})
    df_names.set_index('type_id')
    df = df.merge(df_names, on='type_id', how='left')
    return df

def clean_mkt_data(df):
    # Create a copy first
    df = df.copy()
    df = df.reset_index(drop=True)

    df.rename(columns={'typeID': 'type_id', 'typeName': 'type_name'}, inplace=True)
    
    new_cols = ['order_id', 'is_buy_order', 'type_id', 'type_name', 'price',
        'volume_remain', 'duration', 'issued']
    df = df[new_cols]
    
    # Make sure issued is datetime before using dt accessor
    if not pd.api.types.is_datetime64_any_dtype(df['issued']):
        df['issued'] = pd.to_datetime(df['issued'])
    
    df['expiry'] = df.apply(lambda row: row['issued'] + pd.Timedelta(days=row['duration']), axis=1)
    df['days_remaining'] = (df['expiry'] - pd.Timestamp.now()).dt.days
    df['days_remaining'] = df['days_remaining'].apply(lambda x: x if x > 0 else 0)
    df['days_remaining'] = df['days_remaining'].astype(int)
    
    # Format dates after calculations are done
    df['issued'] = df['issued'].dt.date
    df['expiry'] = df['expiry'].dt.date
    
    return df

@st.cache_data(ttl=600)
def get_fitting_data(type_id):
    logger.info(f"getting fitting data with cache")
    with Session(get_local_mkt_engine()) as session:
        query = f"""
            SELECT * FROM doctrines 
            """
        
        try:
            fit = session.execute(text(query))
            fit = fit.fetchall()
            df = pd.DataFrame(fit)
        except Exception as e:
            print(f"Failed to get data for {fit_id}: {str(e)}")
            raise
        session.close()

        df2 = df.copy()
        df2 = df2[df2['type_id'] == type_id]
        df2.reset_index(drop=True, inplace=True)
        try:
            fit_id = df2.iloc[0]['fit_id']
        except:
            return None, None

        df3 = df.copy()
        df3 = df3[df3['fit_id'] == fit_id]
        df3.reset_index(drop=True, inplace=True)
        
        cols = ['fit_id', 'ship_id', 'ship_name', 'hulls', 'type_id', 'type_name',
       'fit_qty', 'fits_on_mkt', 'total_stock', '4H_price', 'avg_vol', 'days',
       'group_id', 'group_name', 'category_id', 'category_name', 'timestamp',
       'id']
        timestamp = df3.iloc[0]['timestamp']
        df3.drop(columns=['ship_id', 'hulls', 'group_id', 'category_name', 'id', 'timestamp'], inplace=True)


        numeric_formats = {

            'total_stock': '{:,.0f}',
            '4H_price': '{:,.2f}',
            'avg_vol': '{:,.0f}',
            'days': '{:,.0f}',
        }

        for col, format_str in numeric_formats.items():
            if col in df3.columns:  # Only format if column exists
                df3[col] = df3[col].apply(lambda x: safe_format(x, format_str))
        df3.rename(columns={'fits_on_mkt': 'Fits on Market'}, inplace=True)
        df3 = df3.sort_values(by='Fits on Market', ascending=True)
        df3.reset_index(drop=True, inplace=True)
    return df3, timestamp

@st.cache_resource(ttl=600)
def get_local_mkt_engine():
    return create_engine(local_mkt_url, echo=False)  # Set echo=False to reduce console output

@st.cache_resource(ttl=600)
def get_local_mkt_db(query: str) -> pd.DataFrame:
    engine = create_engine(local_mkt_url, echo=False)
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return df

@st.cache_resource(ttl=600)
def get_local_sde_engine():
    return create_engine(local_sde_url, echo=False)

@st.cache_resource(ttl=600)
def get_local_sde_db(query: str) -> pd.DataFrame:
    engine = create_engine(local_sde_url, echo=False)
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return df

@st.cache_resource(ttl=600)
def get_stats(stats_query):
    engine = get_local_mkt_engine()
    with engine.connect() as conn:
        stats = pd.read_sql_query(stats_query, conn)
    return stats

# Helper function to safely format numbers
def safe_format(value, format_string):
    try:
        if pd.isna(value) or value is None:
            return ''
        return format_string.format(float(value))
    except (ValueError, TypeError):
        return ''

@st.cache_data(ttl=600)
def get_market_history(type_id):
    query = f"""
        SELECT date, average, volume
        FROM market_history
        WHERE type_id = {type_id}
        ORDER BY date
    """
    return pd.read_sql_query(query, (get_local_mkt_engine()))

def get_update_time()->str:
    query = """
        SELECT last_update FROM marketstats LIMIT 1
    """
    try:
        df = get_local_mkt_db(query)
        data_update = df.iloc[0]['last_update']
        data_update = pd.to_datetime(data_update, utc=True)
        data_update = data_update.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Last ESI update: {data_update}")
        st.session_state['update_time'] = data_update
        return data_update
    except Exception as e:
        logger.error(f"Failed to get update time: {str(e)}")
        return None
    
def get_time_since_esi_update()->str:
    query = """
        SELECT last_update FROM marketstats LIMIT 1
    """
    df = get_local_mkt_db(query)
    dt_last_update = datetime.datetime.strptime(df.iloc[0]['last_update'], '%Y-%m-%d %H:%M:%S.%f')
    dt_now = datetime.datetime.utcnow()
    time_since_update = dt_now - dt_last_update

    # Calculate hours and minutes from total seconds
    total_seconds = int(time_since_update.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    #get the grammer right by using correct singular/plural for minutes and hours
    if minutes == 1:
        min = "minute"
    else:
        min = "minutes"
    if hours == 1:
        hour = "hour"
    else:
        hour = "hours"

    #avoid returning 0 hours, because we have the OCD
    if hours == 0:
        result = f"({int(minutes)} {min} ago)"
    else:
        result = f"{int(hours)} {hour}, {int(minutes)} {min} ago"
    return result

def get_time_until_next_update()->str:

    #get the next sync time from the last_sync_state.json file
    with open("last_sync_state.json", "r") as f:
        last_sync_state = json.load(f)
    next_sync = last_sync_state['next_sync']

    next_sync = datetime.datetime.strptime(next_sync, '%Y-%m-%d %H:%M UTC')
    dt_now = datetime.datetime.utcnow()
    time_until_update = next_sync - dt_now
    if time_until_update.total_seconds() < 0:
        st.session_state.sync_available = True
        return "update available, use sync now to refresh data"
    else:
        st.session_state.sync_available = False
        
    hours = time_until_update.total_seconds() // 3600
    minutes = (time_until_update.total_seconds() % 3600) // 60

    #get the grammer right by using correct singular/plural for minutes and hours
    if minutes == 1:
        min = "minute"
    else:
        min = "minutes"
    if hours == 1:
        hour = "hour"
    else:
        hour = "hours"

    #avoid returning 0 hours, because we have the OCD
    if hours == 0:
        result = f"{int(minutes)} {min}"
    else:
        result = f"{int(hours)} {hour}, {int(minutes)} {min}"
    return result


def get_module_fits(type_id):
    
    with Session(get_local_mkt_engine()) as session:
        query = f"""
            SELECT * FROM doctrines WHERE type_id = {type_id}
            """
        try:
            fit = session.execute(text(query))
            fit = fit.fetchall()
            df = pd.DataFrame(fit)
        except Exception as e:
            print(f"Failed to get data for {type_id}: {str(e)}")
            raise
        session.close()

        df2 = df.copy()
        try:
            ships = df2['ship_name'].tolist()
            fit_qty = df2['fit_qty'].tolist()
            ships = [f"{ship} ({qty})" for ship, qty in zip(ships, fit_qty)]
            ships = ', '.join(ships)
            return ships
        except:
            return None

def get_group_fits(group_id):
    with Session(get_local_mkt_engine()) as session:
        query = f"""
            SELECT * FROM doctrines WHERE group_id = {group_id}
            """
        return pd.read_sql_query(query, (get_local_mkt_engine()))

def get_groups()->pd.DataFrame:
    query = """
        SELECT DISTINCT groupID, groupName FROM invGroups
        """
    return pd.read_sql_query(query, (get_local_sde_engine()))

def get_categories()->pd.DataFrame:
    query = """
        SELECT DISTINCT categoryID, categoryName FROM invCategories
        """
    return pd.read_sql_query(query, (get_local_sde_engine()))

def get_groups_for_category(category_id: int)->pd.DataFrame:
    if category_id == 17:
        df = pd.read_csv("build_commodity_groups.csv")
        return df
    else:
        query = f"""
            SELECT DISTINCT groupID, groupName FROM invGroups WHERE categoryID = {category_id}
        """
    df = pd.read_sql_query(query, (get_local_sde_engine()))
    return df

def get_types_for_group(group_id: int)->pd.DataFrame:
    df = pd.read_csv("industry_types.csv")
    df = df[df['groupID'] == group_id]
    df = df.drop_duplicates(subset=['typeID'])
    df.reset_index(drop=True, inplace=True) 
    df2 = df.copy()
    df = df2[['typeID', 'typeName']]
    return df

def get_type_id(type_name: str)->int:
    query = f"""
        SELECT typeID FROM invTypes WHERE typeName = '{type_name}'
        """
    return pd.read_sql_query(query, (get_local_sde_engine()))

def get_system_id(system_name: str)->int:
    query = f"""
        SELECT solarSystemID FROM mapSolarSystems WHERE solarSystemName = '{system_name}'
        """
    return pd.read_sql_query(query, (get_local_sde_engine()))

def get_4H_price(type_id):
    query = f"""
        SELECT * FROM marketstats WHERE type_id = {type_id}
        """
    df = pd.read_sql_query(query, (get_local_mkt_engine()))
    try:
        return df.price.iloc[0]
    except:
        return None
    
def update_taxes(df):
    updates = df.to_dict(orient='records')

    engine = create_engine(build_cost_url)
    with engine.connect() as conn:
        for record in updates:
            structure = record["structure"]
            tax = record["tax"]
            conn.execute(text(f"UPDATE structures SET tax = {tax} WHERE structure = '{structure}'"))
        conn.commit()
        print("Taxes updated successfully")

def fix_duplicate_structures():
    engine = create_engine("sqlite:///build_cost.db")
    with engine.connect() as conn:
        # First, get all duplicate structures
        res = conn.execute(text("""
            SELECT structure, COUNT(*) as count 
            FROM structures 
            GROUP BY structure 
            HAVING COUNT(*) > 1
        """))
        duplicates = res.fetchall()
        print(duplicates)
        
        for dup in duplicates:
            structure_name = dup[0]
            # Keep the first occurrence and delete the rest
            conn.execute(text(f"""
                DELETE FROM structures 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) 
                    FROM structures 
                    WHERE structure = '{structure_name}'
                )
                AND structure = '{structure_name}'
            """))
        conn.commit()
        print("Duplicate structures have been fixed")

if __name__ == "__main__":
    print(local_mkt_path)
    check_db_exists(local_mkt_path)