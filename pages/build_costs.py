import os
import sys
from dataclasses import dataclass
from typing import Sequence, Tuple, Any
import pandas as pd
import sqlalchemy as sa
import sqlalchemy.orm as orm
import streamlit as st
import pathlib
import requests
import json
# ASYNC LIBRARIES
import asyncio
import httpx


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DatabaseConfig
from build_cost_models import Structure, Rig, IndustryIndex
from logging_config import setup_logging
from millify import millify
from db_handler import (
    get_groups_for_category,
    get_types_for_group,
    get_4H_price,
    request_type_names,
)
from utils import update_industry_index, get_jita_price
import datetime
import time
from build_cost_helpers import find_invention_rig

API_TIMEOUT = 20.0
MAX_CONCURRENCY = 6  # tune for the API's rate limits
RETRIES = 2  # light retry; scale if API is flaky

build_cost_db = DatabaseConfig("build_cost")
build_cost_url = build_cost_db.url
sde_db = DatabaseConfig("sde")
sde_url = sde_db.url

valid_structures = [35827, 35825, 35826]
super_shipyard_id = 1046452498926

logger = setup_logging(__name__)

# Decryptor type IDs and their display names
DECRYPTORS = {
    "None (No Decryptor)": None,
    "Accelerant Decryptor": 34201,
    "Attainment Decryptor": 34202,
    "Augmentation Decryptor": 34203,
    "Parity Decryptor": 34204,
    "Process Decryptor": 34205,
    "Symmetry Decryptor": 34206,
    "Optimized Attainment Decryptor": 34207,
    "Optimized Augmentation Decryptor": 34208,
}

def is_t2_item(type_id: int) -> bool:
    """Check if item is Tech II (requires invention)

    Tech II items have metaGroupID = 2 in the SDE database.

    Args:
        type_id: EVE Online type ID to check

    Returns:
        True if item is Tech II, False otherwise
    """
    engine = sa.create_engine(sde_url)
    with engine.connect() as conn:
        result = conn.execute(
            sa.text("SELECT metaGroupID FROM sdeTypes WHERE typeID = :type_id AND metaGroupID = 2"),
            {"type_id": type_id}
        )
        if type_id == 44996:
            return False
        else:
            return result.fetchone() is not None

@st.cache_data(ttl=3600)
def get_t1_blueprint_for_t2_item(t2_item_id: int) -> int | None:
    """Get the T1 blueprint ID needed to invent a T2 item

    For invention, we need the T1 blueprint, not the T2 item ID.
    This function queries the manufacturing API to find the blueprint relationship.

    Args:
        t2_item_id: Type ID of the T2 item

    Returns:
        T1 blueprint type ID, or None if not found

    Note:
        This queries the EVE Ref API's manufacturing endpoint for the T2 item,
        which returns the T1 blueprint ID in the invention materials section.
    """
    try:
        # Query the manufacturing API for the T2 item to get invention materials
        url = f"https://api.everef.net/v1/industry/cost?product_id={t2_item_id}&runs=1&material_prices=ESI_AVG"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Check if there's invention data in the response
        if "invention" in data and data["invention"]:
            # The invention section has the T2 blueprint as the key
            # Get the first (and usually only) entry
            for t2_bp_id, inv_data in data["invention"].items():
                # The blueprint_id field in invention data IS the T1 blueprint we need
                if "blueprint_id" in inv_data:
                    t1_bp_id = inv_data["blueprint_id"]
                    logger.info(f"Found T1 blueprint {t1_bp_id} for T2 item {t2_item_id}")
                    return t1_bp_id

        logger.warning(f"No invention data found for T2 item {t2_item_id}")
        return None

    except Exception as e:
        logger.error(f"Error looking up T1 blueprint for {t2_item_id}: {e}")
        return None

@dataclass
class JobQuery:
    item: str
    item_id: int
    group_id: int
    runs: int
    me: int
    te: int
    security: str = "NULL_SEC"
    system_cost_bonus: float = 0.0
    material_prices: str = (
        "ESI_AVG"  # default to ESI_AVG, other valid options: "Jita Sell", "Jita Buy"
    )

    # Invention-specific fields
    calculate_invention: bool = False
    decryptor_id: int | None = None
    invention_structure: str | None = None  # Structure name for invention

    # Skills (for invention calculations)
    science: int = 5
    advanced_industry: int = 5
    industry: int = 5
    amarr_encryption: int = 5
    caldari_encryption: int = 5
    gallente_encryption: int = 5
    minmatar_encryption: int = 5
    triglavian_encryption: int = 5
    upwell_encryption: int = 5
    sleeper_encryption: int = 5

    def __post_init__(self):
        if self.group_id in [30, 659]:
            self.super = True
            st.session_state.super = True
            get_all_structures.clear()
        else:
            # clean up the cache, if our last job was a super so all structures can populate again:
            self.super = False
            if st.session_state.super:
                get_all_structures.clear()
                st.session_state.super = False

    def yield_urls(self):
        logger.info(f"Super: {st.session_state.super}")
        structure_generator = yield_structure()

        for structure in structure_generator:
            yield self.construct_url(
                structure
            ), structure.structure, structure.structure_type

    def construct_url(self, structure):

        rigs = [structure.rig_1, structure.rig_2, structure.rig_3]
        clean_rigs = [rig for rig in rigs if rig != "0" and rig is not None]

        valid_rigs = get_valid_rigs()
        system_id = structure.system_id
        system_cost_index = get_manufacturing_cost_index(system_id)

        clean_rigs = [rig for rig in clean_rigs if rig in valid_rigs]
        clean_rig_ids = [valid_rigs[rig] for rig in clean_rigs]
        tax = structure.tax

        formatted_rigs = [f"&rig_id={str(rig)}" for rig in clean_rig_ids]
        rigs = "".join(formatted_rigs)
        url = f"https://api.everef.net/v1/industry/cost?product_id={self.item_id}&runs={self.runs}&me={self.me}&te={self.te}&structure_type_id={structure.structure_type_id}&security={self.security}{rigs}&system_cost_bonus={self.system_cost_bonus}&manufacturing_cost={system_cost_index}&facility_tax={tax}&material_prices={self.material_prices}"
        return url

    def construct_invention_url(self, structure, decryptor_id: int | None = None):
        """Construct URL for invention cost calculation

        Args:
            structure: Structure object with rig and system information
            decryptor_id: Optional decryptor type ID (34201-34208), None for no decryptor

        Returns:
            URL string for EVE Ref API invention cost endpoint

        Note:
            The invention API does not accept structure_type_id or rig_id parameters.
            It only uses system cost index and facility tax from the structure.
            For T2 items, this converts the T2 item ID to the T1 blueprint ID needed for invention.
        """
        # For T2 items, get the T1 blueprint ID
        blueprint_id = get_t1_blueprint_for_t2_item(self.item_id)

        if blueprint_id is None:
            raise ValueError(f"Could not find T1 blueprint for T2 item {self.item_id}")

        # Get system cost index and facility tax from structure
        system_id = structure.system_id
        system_cost_index = get_manufacturing_cost_index(system_id)
        tax = structure.tax

        # Note: Do NOT include structure_type_id or rig_id - API doesn't accept them for invention
        base_params = [
            f"blueprint_id={blueprint_id}",  # Use T1 blueprint ID, not T2 item ID
            f"runs={self.runs}",
            f"science={self.science}",
            f"advanced_industry={self.advanced_industry}",
            f"industry={self.industry}",
            f"amarr_encryption_methods={self.amarr_encryption}",
            f"caldari_encryption_methods={self.caldari_encryption}",
            f"gallente_encryption_methods={self.gallente_encryption}",
            f"minmatar_encryption_methods={self.minmatar_encryption}",
            f"triglavian_encryption_methods={self.triglavian_encryption}",
            f"upwell_encryption_methods={self.upwell_encryption}",
            f"sleeper_encryption_methods={self.sleeper_encryption}",
            f"security={self.security}",
            f"system_cost_bonus={self.system_cost_bonus}",
            f"invention_cost={system_cost_index}",
            f"facility_tax={tax}",
            f"material_prices={self.material_prices}"
        ]
        invention_params = [
            f"product_id={self.item_id}",
            f"runs={self.runs}",
            f"science={self.science}",
            f"advanced_industry={self.advanced_industry}",
            f"industry={self.industry}",
            f"amarr_encryption_methods={self.amarr_encryption}",
            f"caldari_encryption_methods={self.caldari_encryption}",
            f"gallente_encryption_methods={self.gallente_encryption}",
            f"minmatar_encryption_methods={self.minmatar_encryption}",
            f"triglavian_encryption_methods={self.triglavian_encryption}",
            f"upwell_encryption_methods={self.upwell_encryption}",
            f"sleeper_encryption_methods={self.sleeper_encryption}",
            f"security={self.security}",
            f"system_cost_bonus={self.system_cost_bonus}",
            f"invention_cost={system_cost_index}",
            f"facility_tax={tax}",
            f"material_prices={self.material_prices}"
        ]

        # Add decryptor if specified
        if decryptor_id:
            base_params.append(f"decryptor_id={decryptor_id}")

        # Construct URL without rigs
        base_params_str = "&".join(base_params)
        url = f"https://api.everef.net/v1/industry/cost?{base_params_str}"
        return url

@st.cache_data(ttl=3600)
def get_valid_rigs():
    rigs = fetch_rigs()
    invalid_rigs = [46640, 46641, 46496, 46497, 46634, 46640, 46641]
    valid_rigs = {}
    for k, v in rigs.items():
        if v not in invalid_rigs:
            valid_rigs[k] = v
    return valid_rigs

@st.cache_data(ttl=3600)
def fetch_rigs():
    engine = sa.create_engine(build_cost_url)
    with engine.connect() as conn:
        res = conn.execute(sa.text("SELECT type_name, type_id FROM rigs"))
        res = res.fetchall()
        type_names = [item[0] for item in res]
        type_ids = [item[1] for item in res]

        types_dict = {}
        for name, id in zip(type_names, type_ids):
            types_dict[name] = id
        return types_dict

def fetch_rig_id(rig_name: str | None):
    if rig_name is None:
        return None
    elif rig_name == str(0):
        logger.info("Rig name is 0")
        return None
    else:
        try:
            engine = sa.create_engine(build_cost_url)
            with orm.Session(engine) as session:
                res = session.query(Rig).filter(Rig.type_name == rig_name).one()
                return res.type_id
        except Exception as e:
            logger.error(f"Error fetching rig id for {rig_name}: {e}")
            return None

def fetch_structure_by_name(structure_name: str):
    engine = sa.create_engine(build_cost_url)
    with engine.connect() as conn:
        res = conn.execute(
            sa.select(Structure).where(Structure.structure == structure_name)
        )
        structure = res.fetchall()
        if structure is not None:
            return structure[0]
        else:
            raise Exception(f"No structure found for {structure_name}")

@st.cache_data(ttl=3600)
def get_structure_rigs() -> dict[int, list[int]]:
    engine = sa.create_engine(build_cost_url)
    with engine.connect() as conn:
        res = conn.execute(
            sa.select(
                Structure.structure, Structure.rig_1, Structure.rig_2, Structure.rig_3
            ).where(Structure.structure_type_id.in_(valid_structures))
        )
        rigs = res.fetchall()
        rig_dict = {}
        for rig in rigs:
            structure, rig_1, rig_2, rig_3 = rig
            rig_1 = rig_1 if rig_1 != "0" and rig_1 is not None else None
            rig_2 = rig_2 if rig_2 != "0" and rig_2 is not None else None
            rig_3 = rig_3 if rig_3 != "0" and rig_3 is not None else None
            clean_rigs = [rig for rig in [rig_1, rig_2, rig_3] if rig is not None]
            valid_rigs = get_valid_rigs()
            clean_rig_ids = [
                clean_rigs
                for clean_rigs in clean_rigs
                if clean_rigs in valid_rigs.keys()
            ]
            rig_dict[structure] = clean_rig_ids
        return rig_dict

@st.cache_data(ttl=3600)
def get_manufacturing_cost_index(system_id: int) -> float | None:

    engine = sa.create_engine(build_cost_url)
    with engine.connect() as conn:
        res = conn.execute(
            sa.select(IndustryIndex.manufacturing).where(
                IndustryIndex.solar_system_id == system_id
            )
        )
        index = res.scalar()
        if index is not None:
            return float(index)
        else:
            raise Exception(f"No manufacturing cost index found for {system_id}")

def get_type_id(type_name: str) -> int:
    url = f"https://www.fuzzwork.co.uk/api/typeid.php?typename={type_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return int(data["typeID"])
    else:
        logger.error(f"Error fetching: {response.status_code}")
        raise Exception(
            f"Error fetching type id for {type_name}: {response.status_code}"
        )

def get_system_id(system_name: str) -> int:
    engine = sa.create_engine(build_cost_url)
    stmt = sa.select(Structure.system_id).where(Structure.system == system_name)
    with engine.connect() as conn:
        res = conn.execute(stmt)
        system_id = res.scalar()
        if system_id is not None:
            return system_id
        else:
            raise Exception(f"No system id found for {system_name}")

def get_costs(job: JobQuery, async_mode: bool = False) -> dict:
    if async_mode:
        results, status_log = asyncio.run(get_costs_async(job))
    else:
        results, status_log = get_costs_syncronous(job)

    return results, status_log

def get_costs_syncronous(job: JobQuery) -> tuple[dict, dict]:
    status_log = {
        "req_count": 0,
        "success_count": 0,
        "error_count": 0,
        "success_log": {},
        "error_log": {},
    }

    url_generator = job.yield_urls()
    results = {}

    structures = get_all_structures()

    progress_bar = st.progress(
        0, text=f"Fetching data from {len(structures)} structures..."
    )

    for i in range(len(structures)):

        url, structure_name, structure_type = next(url_generator)
        logger.info(structure_name)

        # Pad the line with spaces to ensure it's at least as long as the previous line
        status = f"\rFetching {i+1} of {len(structures)} structures: {structure_name}"
        progress_bar.progress(i / len(structures), text=status)

        response = requests.get(url)
        status_log["req_count"] += 1
        if response.status_code == 200:
            status_log["success_count"] += 1
            status_log["success_log"][structure_name] = (response.status_code, response.text)
            data = response.json()
            try:
                data2 = data["manufacturing"][str(job.item_id)]
            except KeyError as e:
                logger.error(f"Error: {e} No data found for {job.item_id}")
                logger.error(f"Error: {e} No data found for {job.item_id}")
                return None
        else:
            status_log["error_count"] += 1
            status_log["error_log"][structure_name] = (response.status_code, response.text)
            logger.error(
                f"Error fetching data for {structure_name}: {response.status_code}"
            )
            logger.error(f"Error: {response.text}")
            continue
        units = data2["units"]

        results[structure_name] = {
            "structure_type": structure_type,
            "units": units,
            "total_cost": data2["total_cost"],
            "total_cost_per_unit": data2["total_cost_per_unit"],
            "total_material_cost": data2["total_material_cost"],
            "facility_tax": data2["facility_tax"],
            "scc_surcharge": data2["scc_surcharge"],
            "system_cost_index": data2["system_cost_index"],
            "total_job_cost": data2["total_job_cost"],
            "materials": data2["materials"],
        }

    return results, status_log

async def fetch_one(
    client: httpx.AsyncClient,
    url: str,
    structure_name: str,
    structure_type: str,
    job: JobQuery,
):
    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        try:
            data2 = data["manufacturing"][str(job.item_id)]
        except KeyError:
            return structure_name, None, f"No data found for {job.item_id}"
        return (
            structure_name,
            {
                "structure_type": structure_type,
                "units": data2["units"],
                "total_cost": data2["total_cost"],
                "total_cost_per_unit": data2["total_cost_per_unit"],
                "total_material_cost": data2["total_material_cost"],
                "facility_tax": data2["facility_tax"],
                "scc_surcharge": data2["scc_surcharge"],
                "system_cost_index": data2["system_cost_index"],
                "total_job_cost": data2["total_job_cost"],
                "materials": data2["materials"],
            },
            None,
        )
    except Exception as e:
        return structure_name, None, str(e)

async def get_costs_async(job: JobQuery) -> tuple[dict, dict]:
    structures = get_all_structures(unwrap=True)  # list[dict]
    url_generator = job.yield_urls()

    results = {}
    status_log = {
        "req_count": 0,
        "success_count": 0,
        "error_count": 0,
        "success_log": {},
        "error_log": {},
    }
    # Reduce connection limits to be more gentle on the server
    limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY, max_keepalive_connections=MAX_CONCURRENCY
    )
    # Limit concurrent requests to 4 at a time
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def fetch_with_semaphore(client, url, structure_name, structure_type, job):
        async with semaphore:
            return await fetch_one(client, url, structure_name, structure_type, job)

    # Add headers to identify your application
    headers = {
        "User-Agent": "WCMKTS-BuildCosts/1.0 (https://github.com/OrthelT/wcmkts_production; orthel.toralen@gmail.com)"
    }

    async with httpx.AsyncClient(http2=True, limits=limits, headers=headers) as client:

        progress_bar = st.progress(
            0, text=f"Fetching data from {len(structures)} structures..."
        )
        tasks = []
        for _ in structures:
            url, structure_name, structure_type = next(url_generator)
            tasks.append(
                fetch_with_semaphore(client, url, structure_name, structure_type, job)
            )

        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            status = f"\rFetching {i} of {len(structures)} structures: {structure_name}"
            progress_bar.progress(i / len(structures), text=status)
            structure_name, result, error = await coro
            status_log["req_count"] += 1

            if result:
                results[structure_name] = result
                status_log["success_count"] += 1
                status_log["success_log"][structure_name] = (result, None)
            if error:
                status_log["error_count"] += 1
                status_log["error_log"][structure_name] = (None, error)

    # Log errors if needed
    if status_log["error_count"] > 0:
        for s, e in status_log["error_log"].items():
            logger.error(f"Error fetching {s}: {e}")

    logger.info("="*80)
    logger.info(f"Results of {len(structures)} structures:")
    logger.info(f"Results count: {status_log['success_count']}")
    logger.info(f"Errors count: {status_log['error_count']}")
    logger.info("="*80)

    return results, status_log

async def fetch_one_invention(
    client: httpx.AsyncClient,
    url: str,
    decryptor_name: str,
    job: JobQuery,
):
    """Fetch invention costs for a single decryptor

    Args:
        client: HTTPX async client
        url: API endpoint URL
        decryptor_name: Name of the decryptor (for logging)
        job: JobQuery object with item information

    Returns:
        Tuple of (decryptor_name, result_dict, error_string)
    """
    logger.info("="*80)
    logger.info(f"URL: {url}")
    logger.info("="*80)


    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()

        # Check for invention data in response
        if "invention" not in data:
            return decryptor_name, None, "No invention data in response"

        invention_data = data["invention"]

        # The invention section is keyed by the T2 blueprint ID
        # We need to find the right key (there should only be one)
        if not invention_data:
            return decryptor_name, None, "Invention data is empty"

        # Get the first (and usually only) blueprint's invention data
        bp_id = list(invention_data.keys())[0]
        bp_invention_data = invention_data[bp_id]

        return (
            decryptor_name,
            {
                "probability": bp_invention_data.get("probability", 0),
                "runs_per_copy": bp_invention_data.get("runs_per_copy", 0),
                "expected_copies": bp_invention_data.get("expected_copies", 0),
                "expected_runs": bp_invention_data.get("expected_runs", 0),
                "expected_units": bp_invention_data.get("expected_units", 0),
                "me": bp_invention_data.get("me", 0),
                "te": bp_invention_data.get("te", 0),
                "materials": bp_invention_data.get("materials", {}),
                "total_material_cost": bp_invention_data.get("total_material_cost", 0),
                "total_cost": bp_invention_data.get("total_cost", 0),
                "avg_cost_per_copy": bp_invention_data.get("avg_cost_per_copy", 0),
                "avg_cost_per_run": bp_invention_data.get("avg_cost_per_run", 0),
                "avg_cost_per_unit": bp_invention_data.get("avg_cost_per_unit", 0),
            },
            None,
        )
    except Exception as e:
        return decryptor_name, None, str(e)

async def get_invention_costs_async(job: JobQuery, structure: Structure) -> tuple[dict, dict]:
    """Get invention costs for all decryptors asynchronously

    Args:
        job: JobQuery object with invention parameters (skills, etc.)
        structure: Structure object for the invention facility

    Returns:
        Tuple of (results_dict, status_log_dict)
        results_dict maps decryptor_name -> invention_cost_data
    """
    results = {}
    status_log = {
        "req_count": 0,
        "success_count": 0,
        "error_count": 0,
        "success_log": {},
        "error_log": {},
    }

    # Reduce connection limits to be more gentle on the server
    limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY, max_keepalive_connections=MAX_CONCURRENCY
    )
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def fetch_with_semaphore(client, url, decryptor_name, job):
        async with semaphore:
            return await fetch_one_invention(client, url, decryptor_name, job)

    # Add headers to identify your application
    headers = {
        "User-Agent": "WCMKTS-BuildCosts/1.0 (https://github.com/OrthelT/wcmkts_production; orthel.toralen@gmail.com)"
    }

    async with httpx.AsyncClient(http2=True, limits=limits, headers=headers) as client:
        progress_bar = st.progress(
            0, text=f"Fetching invention costs for {len(DECRYPTORS)} decryptor options..."
        )

        tasks = []
        decryptor_list = list(DECRYPTORS.items())

        # Create tasks for each decryptor
        for decryptor_name, decryptor_id in decryptor_list:
            url = job.construct_invention_url(structure, decryptor_id)
            tasks.append(
                fetch_with_semaphore(client, url, decryptor_name, job)
            )

        # Process results as they complete
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            progress_bar.progress(i / len(decryptor_list), text=f"Fetching invention costs ({i}/{len(decryptor_list)})...")
            decryptor_name, result, error = await coro
            status_log["req_count"] += 1

            if result:
                results[decryptor_name] = result
                status_log["success_count"] += 1
                status_log["success_log"][decryptor_name] = (result, None)
            if error:
                status_log["error_count"] += 1
                status_log["error_log"][decryptor_name] = (None, error)

    # Log errors if needed
    if status_log["error_count"] > 0:
        for d, e in status_log["error_log"].items():
            logger.error(f"Error fetching invention costs for {d}: {e}")

    logger.info("="*80)
    logger.info(f"Invention cost results for {len(decryptor_list)} decryptors:")
    logger.info(f"Results count: {status_log['success_count']}")
    logger.info(f"Errors count: {status_log['error_count']}")
    logger.info("="*80)

    return results, status_log

def display_log_status(status: dict):

    logger.info("Status Report:")
    logger.info(f"Requests: {status['req_count']}")
    logger.info(f"Successes: {status['success_count']}")
    logger.info(f"Errors: {status['error_count']}")
    if status["error_count"] > 0:
        logger.error(f"Error Log: {status['error_log']}")
        st.toast(f"Errors returned for {status['error_count']}. This is likely due to problems with the external industry data API. Please try again later.", icon="⚠️")


    with open("status.log", "w") as f:
        f.write(json.dumps(status, indent=4))

@st.cache_data(ttl=3600)
def get_all_structures(
    *, unwrap: bool = False
) -> Sequence[sa.Row[Tuple[Structure]]] | list[dict[str, Any]]:
    engine = sa.create_engine(build_cost_url)
    logger.info("Getting all structures")
    if st.session_state.super:
        logger.info("Super mode enabled")
        stmt = sa.select(Structure).where(Structure.structure_id == super_shipyard_id)
    else:
        logger.info("Super mode disabled")

        stmt = (
            sa.select(Structure)
            .where(Structure.structure_id != super_shipyard_id)
            .filter(Structure.structure_type_id.in_(valid_structures))
        )

    with engine.connect() as conn:
        res = conn.execute(stmt)
        rows = res.fetchall()

        if unwrap:
            return [r._mapping for r in rows]
        else:
            return rows


def yield_structure():
    structures = get_all_structures()
    for structure in structures:
        yield structure





def is_valid_image_url(url: str) -> bool:
    """Check if the URL returns a valid image."""
    try:
        response = requests.head(url)
        return response.status_code == 200 and "image" in response.headers.get(
            "content-type", ""
        )
    except Exception as e:
        logger.error(f"Error checking image URL {url}: {e}")
        return False


def display_data(df: pd.DataFrame, selected_structure: str | None = None, is_t2: bool = False):
    # Check if dataframe has invention columns
    has_invention = "invention_cost_per_unit" in df.columns

    if selected_structure:
        selected_structure_df = df[df.index == selected_structure]

        # Use appropriate cost columns based on whether we have invention costs
        if has_invention:
            selected_total_cost = selected_structure_df["total_production_cost"].values[0]
            selected_total_cost_per_unit = selected_structure_df["total_production_cost_per_unit"].values[0]
        else:
            selected_total_cost = selected_structure_df["total_cost"].values[0]
            selected_total_cost_per_unit = selected_structure_df["total_cost_per_unit"].values[0]

        st.markdown(
            f"**Selected structure:** <span style='color: orange;'>{selected_structure}</span> <br>    *Total cost:* <span style='color: orange;'>{millify(selected_total_cost, precision=2)}</span> <br>    *Cost per unit:* <span style='color: orange;'>{millify(selected_total_cost_per_unit, precision=2)}</span>",
            unsafe_allow_html=True,
        )

        # Create comparison columns based on appropriate cost type
        if has_invention:
            df["comparison_cost"] = df["total_production_cost"].apply(
                lambda x: x - selected_total_cost
            )
            df["comparison_cost_per_unit"] = df["total_production_cost_per_unit"].apply(
                lambda x: x - selected_total_cost_per_unit
            )
        else:
            df["comparison_cost"] = df["total_cost"].apply(
                lambda x: x - selected_total_cost
            )
            df["comparison_cost_per_unit"] = df["total_cost_per_unit"].apply(
                lambda x: x - selected_total_cost_per_unit
            )

    col_order = [
        "_index",
        "structure_type",
        "units",
        "total_cost",
        "total_cost_per_unit",
        "total_material_cost",
        "total_job_cost",
        "facility_tax",
        "scc_surcharge",
        "system_cost_index",
        "structure_rigs",
    ]

    # Add invention columns if present
    if has_invention:
        col_order.insert(5, "invention_cost_per_unit")
        col_order.insert(6, "total_production_cost_per_unit")
        col_order.insert(7, "total_production_cost")

    if selected_structure:
        col_order.insert(2, "comparison_cost")
        col_order.insert(3, "comparison_cost_per_unit")

    col_config = {
        "_index": st.column_config.TextColumn(
            label="structure", help="Structure Name"
        ),

        "structure_type": " type",
        "units": st.column_config.NumberColumn(
            "units", help="Number of units built", width=60
        ),
        "total_cost": st.column_config.NumberColumn(
            "mfg cost" if has_invention else "total cost",
            help="Manufacturing cost only" if has_invention else "Total cost of building the units",
            format="localized",
            step=1
        ),
        "total_cost_per_unit": st.column_config.NumberColumn(
            "mfg cost/unit" if has_invention else "cost per unit",
            help="Manufacturing cost per unit only" if has_invention else "Cost per unit of the item",
            format="localized",
            step=1,
        ),
        "total_material_cost": st.column_config.NumberColumn(
            "material cost",
            help="Total material cost",
            format="localized",
            step=1
        ),
        "total_job_cost": st.column_config.NumberColumn(
            "total job cost",
            help="Total job cost, which includes the facility tax, SCC surcharge, and system cost index",
            format="compact",
        ),
        "facility_tax": st.column_config.NumberColumn(
            "facility tax", help="Facility tax cost", format="compact", width="small"
        ),
        "scc_surcharge": st.column_config.NumberColumn(
            "scc surcharge", help="SCC surcharge cost", format="compact", width="small"
        ),
        "system_cost_index": st.column_config.NumberColumn(
            "cost index", format="compact", width="small"
        ),
        "structure_rigs": st.column_config.ListColumn(
            "rigs",
            help="Rigs fitted to the structure",
        ),
    }

    # Add invention column configs if present
    if has_invention:
        col_config["invention_cost_per_unit"] = st.column_config.NumberColumn(
            "invention cost/unit",
            help="Average invention cost per unit (using best decryptor)",
            format="localized",
            step=1,
        )
        col_config["total_production_cost_per_unit"] = st.column_config.NumberColumn(
            "total prod cost/unit",
            help="Total production cost per unit (manufacturing + invention)",
            format="localized",
            step=1,
        )
        col_config["total_production_cost"] = st.column_config.NumberColumn(
            "total production cost",
            help="Total production cost (manufacturing + invention) for all units",
            format="localized",
            step=1,
        )

    if selected_structure:
        col_config.update(
            {
                "comparison_cost": st.column_config.NumberColumn(
                    "comparison cost",
                    help="Comparison cost",
                    format="compact",
                    width="small",
                ),
                "comparison_cost_per_unit": st.column_config.NumberColumn(
                    "comparison cost per unit",
                    help="Comparison cost per unit",
                    format="compact",
                    width="small",
                ),
            }
        )
    df = style_dataframe(df, selected_structure)

    return df, col_config, col_order


def style_dataframe(df: pd.DataFrame, selected_structure: str | None = None):
    df = df.style.apply(
        lambda x: [
            (
                "background-color: lightgreen; color: blue"
                if x.name == selected_structure
                else ""
            )
            for i in x.index
        ],
        axis=1,
    )
    return df


def check_industry_index_expiry():

    now = datetime.datetime.now().astimezone(datetime.UTC)
    if st.session_state.sci_expires:
        expires = st.session_state.sci_expires

        if expires < now:
            logger.info("Industry index expired, updating")
            try:
                update_industry_index()
            except Exception as e:
                logger.error(f"Error updating industry index: {e}")
                raise Exception(f"Error updating industry index: {e}")

    else:
        logger.info("Industry index not in session state, updating")
        try:
            update_industry_index()
        except Exception as e:
            logger.error(f"Error updating industry index: {e}")
            raise Exception(f"Error updating industry index: {e}")


def initialise_session_state():
    logger.info("initialising build cost tool")
    if "sci_expires" not in st.session_state:
        st.session_state.sci_expires = None
    if "sci_last_modified" not in st.session_state:
        st.session_state.sci_last_modified = None
    if "etag" not in st.session_state:
        st.session_state.etag = None
    if "cost_results" not in st.session_state:
        st.session_state.cost_results = None
    if "current_job_params" not in st.session_state:
        st.session_state.current_job_params = None
    if "selected_item_for_display" not in st.session_state:
        st.session_state.selected_item_for_display = None
    if "price_source" not in st.session_state:
        st.session_state.price_source = None
    if "price_source_name" not in st.session_state:
        st.session_state.price_source_name = None
    if "calculate_clicked" not in st.session_state:
        st.session_state.calculate_clicked = False
    if "button_label" not in st.session_state:
        st.session_state.button_label = "Calculate"
    if "current_job_params" not in st.session_state:
        st.session_state.current_job_params = None
    if "selected_structure" not in st.session_state:
        st.session_state.selected_structure = None
    if "super" not in st.session_state:
        st.session_state.super = False
    if "async_mode" not in st.session_state:
        st.session_state.async_mode = False

    # Invention-specific session state
    if "invention_costs" not in st.session_state:
        st.session_state.invention_costs = None
    if "selected_decryptor" not in st.session_state:
        st.session_state.selected_decryptor = "None (No Decryptor)"
    if "selected_invention_structure" not in st.session_state:
        st.session_state.selected_invention_structure = None
    # Skill levels
    if "science_level" not in st.session_state:
        st.session_state.science_level = 5
    if "advanced_industry_level" not in st.session_state:
        st.session_state.advanced_industry_level = 5
    if "industry_level" not in st.session_state:
        st.session_state.industry_level = 5
    if "amarr_encryption_level" not in st.session_state:
        st.session_state.amarr_encryption_level = 5
    if "caldari_encryption_level" not in st.session_state:
        st.session_state.caldari_encryption_level = 5
    if "gallente_encryption_level" not in st.session_state:
        st.session_state.gallente_encryption_level = 5
    if "minmatar_encryption_level" not in st.session_state:
        st.session_state.minmatar_encryption_level = 5
    if "triglavian_encryption_level" not in st.session_state:
        st.session_state.triglavian_encryption_level = 5
    if "upwell_encryption_level" not in st.session_state:
        st.session_state.upwell_encryption_level = 5
    if "sleeper_encryption_level" not in st.session_state:
        st.session_state.sleeper_encryption_level = 5

    st.session_state.initialised = True

    try:
        check_industry_index_expiry()
    except Exception as e:
        logger.error(f"Error checking industry index expiry: {e}")

@st.fragment()
def display_material_costs(results: dict, selected_structure: str, structure_names_for_materials: list):
    """
    Display material costs for a selected structure with proper formatting.

    Args:
        results: Dictionary containing cost calculation results from get_costs
        selected_structure: Name of the selected structure
        structure_names_for_materials: List of structure names for materials
    """
            # Default to the structure selected in sidebar if available
    default_index = 0
    if selected_structure and selected_structure in structure_names_for_materials:
        default_index = structure_names_for_materials.index(selected_structure)

    selected_structure_for_materials = st.selectbox(
        "Select a structure to view material breakdown:",
        structure_names_for_materials,
        index=default_index,
        key="material_structure_selector",
        help="Choose a structure to see detailed material costs and quantities",
    )

    if selected_structure_for_materials not in results:
        st.error(f"No data found for structure: {selected_structure}")
        return

    # Get materials data from results
    materials_data = results[selected_structure_for_materials]["materials"]

    # Get type names for materials
    type_ids = [int(k) for k in materials_data.keys()]
    type_names = request_type_names(type_ids)
    type_names_dict = {item["id"]: item["name"] for item in type_names}

    # Build materials list
    materials_list = []
    for type_id_str, material_info in materials_data.items():
        type_id = int(type_id_str)
        type_name = type_names_dict.get(type_id, f"Unknown ({type_id})")

        materials_list.append(
            {
                "type_id": type_id,
                "type_name": type_name,
                "quantity": material_info["quantity"],
                "volume_per_unit": material_info["volume_per_unit"],
                "volume": material_info["volume"],
                "cost_per_unit": material_info["cost_per_unit"],
                "cost": material_info["cost"],
            }
        )

    # Create DataFrame
    df = pd.DataFrame(materials_list)
    df = df.sort_values(by="cost", ascending=False)

    # Calculate cost percentage
    total_material_cost = df["cost"].sum()
    total_material_volume = df["volume"].sum()
    material_price_source = st.session_state.price_source_name

    df["cost_percentage"] = df["cost"] / total_material_cost

    # Display header
    st.subheader(f"Material Breakdown {selected_structure_for_materials}")
    st.markdown(
        f"{st.session_state.selected_item_for_display} Material Cost: <span style='color: orange;'>**{millify(total_material_cost, precision=2)} ISK**</span> (*{millify(total_material_volume, precision=2)} m³*) - {material_price_source}",unsafe_allow_html=True
    )

    # Configure columns with proper formatting
    column_config = {
        "type_name": st.column_config.TextColumn(
            "Material", help="The name of the material required", width="medium"
        ),
        "quantity": st.column_config.NumberColumn(
            "Quantity",
            help="Amount of material needed",
            format="localized",
            width="small",
        ),
        "volume_per_unit": st.column_config.NumberColumn(
            "Volume/Unit",
            help="Volume per unit of material (m³)",
            format="localized",
            width="small",
        ),
        "volume": st.column_config.NumberColumn(
            "Total Volume",
            help="Total volume of this material (m³)",
            format="localized",
            width="small",
        ),
        "cost_per_unit": st.column_config.NumberColumn(
            "Unit Price",
            help="Cost per unit of material (ISK)",
            format="localized",
            width="small",
        ),
        "cost": st.column_config.NumberColumn(
            "Total Cost",
            help="Total cost for this material (ISK)",
            format="compact",
            width="small",
        ),
        "cost_percentage": st.column_config.NumberColumn(
            "% of Total",
            help="Percentage of total material cost",
            format="percent",
            width="small",
        ),
    }
    col1, col2 = st.columns(2)
    with col1:
        # Display the dataframe with custom configuration
        st.dataframe(
            df,
            column_config=column_config,
            column_order=[
                "type_name",
                "quantity",
                "volume_per_unit",
                "volume",
                "cost_per_unit",
                "cost",
                "cost_percentage",
            ],
            hide_index=True,
            width='stretch',
        )
    with col2:
        # material cost chart
        st.bar_chart(
            df,
            x="type_name",
            y="cost",
            y_label="",
            x_label="",
            horizontal=True,
            width='content',
            height=310,
        )

    # Add download tip below the table
    st.info(
        "💡 **Tip:** You can download this data as CSV using the download icon (⬇️) in the top-right corner of the table above."
    )


@st.fragment()
def display_invention_costs(invention_results: dict, invention_structure_name: str):
    """Display invention costs comparison table for all decryptors

    Args:
        invention_results: Dictionary mapping decryptor_name -> cost_data
        invention_structure_name: Name of the structure used for invention
    """
    if not invention_results:
        st.warning("No invention cost data available.")
        return

    st.subheader(f"Invention Costs - {invention_structure_name}")
    st.markdown(
        f"Comparing invention outcomes for all decryptor options."
    )

    # Build DataFrame from invention results
    invention_list = []
    runs = st.session_state.current_job_params.get("runs", 1)
    


    for decryptor_name, data in invention_results.items():
        invention_list.append({
            "decryptor": decryptor_name,
            "success_chance": data.get("probability", 0) * 100,  # Convert to percentage
            "raw_cost_per_run": data.get("total_material_cost", 0)/runs,
            "avg_cost_per_copy": data.get("avg_cost_per_copy", 0),
            "avg_cost_per_run": data.get("avg_cost_per_run", 0),
            "avg_cost_per_unit": data.get("avg_cost_per_unit", 0),
            "me": data.get("me", 0),
            "te": data.get("te", 0),
            "runs_per_copy": data.get("runs_per_copy", 0),
            "expected_runs": round(data.get("expected_runs", 0)/runs, 2),
            "expected_units": data.get("expected_units", 0),
            "total_material_cost": data.get("total_material_cost", 0),

        })

    df = pd.DataFrame(invention_list)

    # Sort by avg_cost_per_unit (lowest first)
    df = df.sort_values(by="avg_cost_per_unit", ascending=True)

    # Find best values for highlighting
    best_cost_per_unit = df["avg_cost_per_unit"].min()
    best_success_chance = df["success_chance"].max()
    lowest_raw_cost = df["raw_cost_per_run"].min()

    # Add highlighting indicators
    df["best_cost"] = df["avg_cost_per_unit"] == best_cost_per_unit
    df["best_success"] = df["success_chance"] == best_success_chance
    df["lowest_raw"] = df["raw_cost_per_run"] == lowest_raw_cost

    st.markdown("### Decryptor Comparison Table")

    # Column configuration
    column_config = {
        "decryptor": st.column_config.TextColumn(
            "Decryptor",
            help="Type of decryptor used (or None)",
            width="medium"
        ),
        "success_chance": st.column_config.NumberColumn(
            "Success %",
            help="Probability of successful invention",
            format="%.1f%%",
            width="small"
        ),
        "raw_cost_per_run": st.column_config.NumberColumn(
            "Raw Cost (per invention attempt)",
            help="Cost of materials for each invention attempt (datacores + decryptor + job costs)",
            format="localized",
            width="medium"
        ),
        "avg_cost_per_copy": st.column_config.NumberColumn(
            "Avg Cost/Copy",
            help="Average cost per successful blueprint copy (accounting for failures)",
            format="localized",
            width="small"
        ),
        "avg_cost_per_run": st.column_config.NumberColumn(
            "Avg Cost/Run",
            help="Average cost per run of the invented blueprint",
            format="localized",
            width="small"
        ),

        "expected_runs": st.column_config.NumberColumn(
            "Expected Runs",
            help="Expected number of runs per invention attempt",
            format="localized",
            width="small"
        ),

        "me": st.column_config.NumberColumn(
            "ME",
            help="Material Efficiency of the invented blueprint",
            format="%d",
            width="small"
        ),
        "te": st.column_config.NumberColumn(
            "TE",
            help="Time Efficiency of the invented blueprint",
            format="%d",
            width="small"
        ),
        "runs_per_copy": st.column_config.NumberColumn(
            "Runs/Copy",
            help="Licensed production runs per invented blueprint copy",
            format="%d",
            width="small"
        ),
        "best_cost": st.column_config.CheckboxColumn(
            "Best Cost",
            help="Lowest average cost per unit",
            width="small"
        ),
        "best_success": st.column_config.CheckboxColumn(
            "Best Success",
            help="Highest success chance",
            width="small"
        ),
        "lowest_raw": st.column_config.CheckboxColumn(
            "Lowest Raw",
            help="Lowest raw cost per run",
            width="small"
        ),
    }

    # Display the dataframe
    st.dataframe(
        df,
        column_config=column_config,
        column_order=[
            "decryptor",
            "success_chance",
            "raw_cost_per_run",
            "avg_cost_per_copy",
            "avg_cost_per_run",
            "expected_runs",
            "me",
            "te",
            "runs_per_copy",
            "best_cost",
            "best_success",
            "lowest_raw",
        ],
        hide_index=True,
        width='stretch',
        height=400,
    )

    # Key insights

    best_overall = df.iloc[0]  # Already sorted by avg_cost_per_unit
    best_success_row = df[df["best_success"] == True].iloc[0]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Best Cost/Unit",
            f"{millify(best_overall['avg_cost_per_unit'], precision=2)} ISK",
            help=f"Using {best_overall['decryptor']}"
        )
        st.caption(f"**{best_overall['decryptor']}**")

    with col2:
        st.metric(
            "Highest Success Rate",
            f"{best_success_row['success_chance']:.1f}%",
            help=f"Using {best_success_row['decryptor']}"
        )
        st.caption(f"**{best_success_row['decryptor']}**")

    with col3:
        st.metric(
            "Expected Units per Attempt",
            f"{best_overall['expected_units']:.0f}",
            help=f"Using {best_overall['decryptor']}"
        )
        st.caption(f"ME: {best_overall['me']}, TE: {best_overall['te']}")


def main():
    logger.info("="*80)
    logger.info("Starting build cost tool")
    logger.info("="*80)
    if "initialised" not in st.session_state:
        initialise_session_state()
    else:
        logger.info("Session state already initialised, skipping initialisation")
    logger.info("build cost tool initialised and awaiting user input")

    # Handle path properly for WSL environment
    image_path = pathlib.Path(__file__).parent.parent / "images" / "wclogo.png"

    # App title and logo
    col1, col2 = st.columns([0.2, 0.8], vertical_alignment="bottom")

    with col1:
        if image_path.exists():
            st.image(str(image_path), width=150)
        else:
            pass
    with col2:
        st.title("Build Cost Tool")

    df = pd.read_csv("build_catagories.csv")
    df = df.sort_values(by="category")

    categories = df["category"].unique().tolist()

    index = categories.index("Ship")

    # This turns on asynchronous mode, an experimental feature that significantly speeds up the calculation time. This is now enabled by default. Set to False and use synchronous mode if you experience issues.
    async_mode = st.sidebar.checkbox(
        "Async Mode",
        value=True,
        help="This turns on asynchronous mode, an experimental feature that significantly speeds up the calculation time. This is now enabled by default. Set to False and use synchronous mode if you experience issues.",
    )
    if async_mode:
        st.session_state.async_mode = True
        logger.info("Async mode enabled")
    else:
        st.session_state.async_mode = False
        logger.info("Async mode disabled")

    selected_category = st.sidebar.selectbox(
        "Select a category",
        categories,
        index=index,
        placeholder="Ship",
        help="Select a category to filter the groups and items by.",
    )
    category_df = df[df["category"] == selected_category]
    category_id = category_df["id"].values[0]
    logger.info(f"Selected category: {selected_category} ({category_id})")

    if category_id == 40:
        groups = ["Sovereignty Hub"]
        selected_group = st.sidebar.selectbox("Select a group", groups)
        group_id = 1012
    else:
        groups = get_groups_for_category(category_id)
        groups = groups.sort_values(by="groupName")
        groups = groups.drop(groups[groups["groupName"] == "Abyssal Modules"].index)
        group_names = groups["groupName"].unique()
        selected_group = st.sidebar.selectbox("Select a group", group_names)
        group_id = groups[groups["groupName"] == selected_group]["groupID"].values[0]
        logger.info(f"Selected group: {selected_group} ({group_id})")
    try:
        types_df = get_types_for_group(group_id)
        types_df = types_df.sort_values(by="typeName")

        # Check if types_df is empty
        if len(types_df) == 0:
            st.warning(f"No items found for group: {selected_group}")
            selected_group = None
            selected_category = "Ship"
            index = categories.index("Ship")
            selected_category = st.sidebar.selectbox("Select a category", categories, index=index)
            category_id = df[df["category"] == selected_category]["id"].values[0]
            group_id = 1012
            st.rerun()
        else:
            type_names = types_df["typeName"].unique()
            selected_item = st.sidebar.selectbox("Select an item", type_names)
            type_names_list = type_names.tolist()
    except Exception as e:
        st.warning(f"invalid group: {e}")
        selected_group = None
        selected_category = "Ship"
        index = categories.index("Ship")
        selected_category = st.sidebar.selectbox("Select a category", categories, index=index)
        category_id = df[df["category"] == selected_category]["id"].values[0]
        group_id = 1012
        st.rerun()

    # Only proceed if we have valid data
    if 'selected_item' in locals() and 'type_names_list' in locals() and 'types_df' in locals():
        try:
            if selected_item not in type_names_list:
                st.warning(f"Selected item: {selected_item} not a buildable item")
                selected_item = None
            else:
                # Filter the DataFrame and check if any results exist
                filtered_df = types_df[types_df["typeName"] == selected_item]
                if len(filtered_df) == 0:
                    st.warning(f"Selected item: {selected_item} not found in types database")
                    selected_item = None
                else:
                    type_id = filtered_df["typeID"].values[0]
        except Exception as e:
            st.warning(f"invalid item: {e}")
            selected_item = None
            st.rerun()
    else:
        # If we don't have the required variables, set defaults
        selected_item = None
        type_id = None

    # Ensure type_id is defined before proceeding
    if 'type_id' not in locals() or type_id is None:
        st.warning(f"Selected item: {selected_item if 'selected_item' in locals() else 'None'} not a buildable item")
        selected_item = None
        st.rerun()

    runs = st.sidebar.number_input("Runs", min_value=1, max_value=100000, value=1)

    # Check if item is T2 early to determine ME/TE handling
    is_t2_early = is_t2_item(type_id) if type_id else False

    if is_t2_early:
        # For T2 items, ME/TE comes from invention (decryptor-dependent)
        st.sidebar.info("ℹ️ **T2 Item**: ME/TE will be determined by the decryptor used for invention")
        # Set dummy values - these will be overridden by invention results
        me = 0
        te = 0
    else:
        # For T1 items, allow user to set ME/TE
        me = st.sidebar.number_input("ME", min_value=0, max_value=10, value=0)
        te = st.sidebar.number_input("TE", min_value=0, max_value=20, value=0)

    st.sidebar.divider()

    price_source = st.sidebar.selectbox(
        "Select a material price source",
        ["ESI Average", "Jita Sell", "Jita Buy"],
        help="This is the source of the material prices used in the calculations. ESI Average is the CCP average price used in the in-game industry window, Jita Sell is the minimum price of sale orders in Jita, and Jita Buy is the maximum price of buy orders in Jita.",
    )

    price_source_dict = {
        "ESI Average": "ESI_AVG",
        "Jita Sell": "FUZZWORK_JITA_SELL_MIN",
        "Jita Buy": "FUZZWORK_JITA_BUY_MAX",
    }
    price_source_id = price_source_dict[price_source]
    logger.info(f"Selected price source: {price_source} ({price_source_id})")

    st.session_state.price_source_name = price_source
    st.session_state.price_source = price_source_id
    logger.info(
        f"Price source: {st.session_state.price_source_name} ({st.session_state.price_source})"
    )

    url = f"https://images.evetech.net/types/{type_id}/render?size=256"
    alt_url = f"https://images.evetech.net/types/{type_id}/icon"

    all_structures = get_all_structures()
    structure_names = [structure.structure for structure in all_structures]
    structure_names = sorted(structure_names)

    with st.sidebar.expander("Select a structure to compare (optional)"):
        selected_structure = st.selectbox(
            "Structures:",
            structure_names,
            index=None,
            placeholder="All Structures",
            help="Select a structure to compare the cost to build versus this structure. This is optional and will default to all structures.",
        )

    # Use the early T2 check (already computed above)
    is_t2 = is_t2_early

    if is_t2:
        st.sidebar.divider()
        st.sidebar.markdown("### Invention Settings")

        # Structure selection for invention
        with st.sidebar:
            # Find default structure index (4-HWWF Lab)
            default_structure = "4-HWWF - WinterCo. Laboratory Center"
            default_index = 0
            if default_structure in structure_names:
                default_index = structure_names.index(default_structure)

            selected_invention_structure = st.selectbox(
                "Select structure for invention:",
                structure_names,
                index=default_index if structure_names else None,
                help="Select the structure where invention will take place. Structure bonuses apply to invention costs.",
                key="invention_structure_selector"
            )

            st.session_state.selected_invention_structure = selected_invention_structure

        # Decryptor selection
        with st.sidebar.expander("Decryptor Selection"):
            decryptor_options = list(DECRYPTORS.keys())

            # Initialize selected decryptor in session state if not present
            if "selected_decryptor_for_costs" not in st.session_state:
                st.session_state.selected_decryptor_for_costs = "Auto (Best Cost)"

            # Add "Auto" option at the beginning
            decryptor_options_with_auto = ["Auto (Best Cost)"] + decryptor_options

            selected_decryptor = st.selectbox(
                "Select decryptor for cost calculations:",
                decryptor_options_with_auto,
                index=decryptor_options_with_auto.index(st.session_state.selected_decryptor_for_costs),
                help="Select which decryptor to use for build cost calculations. 'Auto' uses the lowest cost option.",
                key="decryptor_cost_selector"
            )
            st.session_state.selected_decryptor_for_costs = selected_decryptor

        # Skills configuration (collapsible)
        with st.sidebar.expander("Skills Configuration"):
            st.markdown("**Core Skills**")
            st.session_state.science_level = st.slider(
                "Science",
                min_value=0,
                max_value=5,
                value=st.session_state.science_level,
                help="+4% invention success chance per level",
                key="science_slider"
            )
            st.session_state.advanced_industry_level = st.slider(
                "Advanced Industry",
                min_value=0,
                max_value=5,
                value=st.session_state.advanced_industry_level,
                help="Reduces invention job costs",
                key="advanced_industry_slider"
            )
            st.session_state.industry_level = st.slider(
                "Industry",
                min_value=0,
                max_value=5,
                value=st.session_state.industry_level,
                help="Reduces job time and costs",
                key="industry_slider"
            )

            st.markdown("**Encryption Methods**")
            st.caption("Select the encryption method that matches your item's race")

            st.session_state.amarr_encryption_level = st.slider(
                "Amarr Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.amarr_encryption_level,
                help="+2% invention success per level (Amarr items)",
                key="amarr_encryption_slider"
            )
            st.session_state.caldari_encryption_level = st.slider(
                "Caldari Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.caldari_encryption_level,
                help="+2% invention success per level (Caldari items)",
                key="caldari_encryption_slider"
            )
            st.session_state.gallente_encryption_level = st.slider(
                "Gallente Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.gallente_encryption_level,
                help="+2% invention success per level (Gallente items)",
                key="gallente_encryption_slider"
            )
            st.session_state.minmatar_encryption_level = st.slider(
                "Minmatar Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.minmatar_encryption_level,
                help="+2% invention success per level (Minmatar items)",
                key="minmatar_encryption_slider"
            )
            st.session_state.triglavian_encryption_level = st.slider(
                "Triglavian Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.triglavian_encryption_level,
                help="+2% invention success per level (Triglavian items)",
                key="triglavian_encryption_slider"
            )
            st.session_state.upwell_encryption_level = st.slider(
                "Upwell Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.upwell_encryption_level,
                help="+2% invention success per level (Upwell items)",
                key="upwell_encryption_slider"
            )
            st.session_state.sleeper_encryption_level = st.slider(
                "Sleeper Encryption Methods",
                min_value=0,
                max_value=5,
                value=st.session_state.sleeper_encryption_level,
                help="+2% invention success per level (Sleeper items)",
                key="sleeper_encryption_slider"
            )

    # Create job parameters for comparison
    current_job_params = {
        "item": selected_item,
        "item_id": type_id,
        "group_id": group_id,
        "runs": runs,
        "me": me,
        "te": te,
        "price_source": st.session_state.price_source,
        # Include invention parameters if T2
        "is_t2": is_t2,
        "invention_structure": st.session_state.selected_invention_structure if is_t2 else None,
        "science": st.session_state.science_level if is_t2 else None,
        "advanced_industry": st.session_state.advanced_industry_level if is_t2 else None,
        "industry": st.session_state.industry_level if is_t2 else None,
        "amarr_encryption": st.session_state.amarr_encryption_level if is_t2 else None,
        "caldari_encryption": st.session_state.caldari_encryption_level if is_t2 else None,
        "gallente_encryption": st.session_state.gallente_encryption_level if is_t2 else None,
        "minmatar_encryption": st.session_state.minmatar_encryption_level if is_t2 else None,
        "selected_decryptor": st.session_state.get("selected_decryptor_for_costs", "Auto (Best Cost)") if is_t2 else None,
    }
    logger.info(f"Current job params: {current_job_params}")
    logger.info(
        f"st.session_state.calculate_clicked: {st.session_state.calculate_clicked}"
    )

    # Check if parameters have changed (but don't auto-calculate)
    params_changed = (
        st.session_state.current_job_params is not None
        and st.session_state.current_job_params != current_job_params
    )
    logger.info(f"Params changed: {params_changed}")
    if params_changed:
        st.session_state.button_label = "Recalculate"
        if current_job_params["group_id"] in [30, 659]:
            st.session_state.super = True
        else:
            if st.session_state.super:
                get_all_structures.clear()
                st.session_state.super = False
                structure_names = get_all_structures()
                structure_names = [structure.structure for structure in structure_names]
                structure_names = sorted(structure_names)
        logger.info(f"Params changed, Super: {st.session_state.super}")
        st.toast(
            "⚠️ Parameters have changed. Click 'Recalculate' to get updated results."
        )
        logger.info("Parameters changed")
    else:
        st.session_state.button_label = "Calculate"
        logger.info("Parameters not changed")

    calculate_clicked = st.sidebar.button(
        st.session_state.button_label,
        type="primary",
        help="Click to calculate the cost for the selected item.",
    )

    if calculate_clicked:
        st.session_state.calculate_clicked = True
        st.session_state.selected_item_for_display = selected_item

    if st.session_state.sci_last_modified:
        st.sidebar.markdown("---")
        st.sidebar.markdown(
            f"*Industry indexes last updated: {st.session_state.sci_last_modified.strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        )

    if st.session_state.calculate_clicked:
        logger.info("Calculate button clicked, calculating")
        st.session_state.calculate_clicked = False

        # For T2 items, we need to calculate invention FIRST to get the correct ME/TE
        invention_results = None
        invention_me = me
        invention_te = te
        selected_decryptor_for_me_te = None

        if is_t2 and st.session_state.selected_invention_structure:
            logger.info("=" * 80)
            logger.info("Calculating invention costs FIRST (T2 item - need ME/TE)")
            logger.info("=" * 80)

            # Create temporary job for invention
            temp_job = JobQuery(
                item=st.session_state.selected_item_for_display,
                item_id=type_id,
                group_id=group_id,
                runs=runs,
                me=0,  # Placeholder, will be replaced
                te=0,  # Placeholder, will be replaced
                material_prices=st.session_state.price_source,
                calculate_invention=is_t2,
                science=st.session_state.science_level,
                advanced_industry=st.session_state.advanced_industry_level,
                industry=st.session_state.industry_level,
                amarr_encryption=st.session_state.amarr_encryption_level,
                caldari_encryption=st.session_state.caldari_encryption_level,
                gallente_encryption=st.session_state.gallente_encryption_level,
                minmatar_encryption=st.session_state.minmatar_encryption_level,
                triglavian_encryption=st.session_state.triglavian_encryption_level,
                upwell_encryption=st.session_state.upwell_encryption_level,
                sleeper_encryption=st.session_state.sleeper_encryption_level,
            )

            # Get the structure object for invention
            invention_structure_obj = fetch_structure_by_name(st.session_state.selected_invention_structure)

            t_inv_start = time.perf_counter()
            try:
                invention_results, invention_status = asyncio.run(
                    get_invention_costs_async(temp_job, invention_structure_obj)
                )
                t_inv_end = time.perf_counter()
                invention_elapsed = round((t_inv_end - t_inv_start) * 1000, 2)

                logger.info(f"Invention status: {invention_status['success_count']} success, {invention_status['error_count']} errors")
                logger.info(f"TIME get_invention_costs_async() = {invention_elapsed} ms")

                if invention_status['error_count'] > 0:
                    st.warning(f"Some invention cost calculations failed ({invention_status['error_count']} errors). Results may be incomplete.")

                # Extract ME/TE from selected decryptor
                user_selection = st.session_state.get("selected_decryptor_for_costs", "Auto (Best Cost)")

                if user_selection == "Auto (Best Cost)":
                    # Find the best (lowest cost) decryptor
                    best_invention_cost = float('inf')
                    for decryptor_name, inv_data in invention_results.items():
                        cost = inv_data.get("avg_cost_per_unit", 0)
                        if cost < best_invention_cost:
                            best_invention_cost = cost
                            selected_decryptor_for_me_te = decryptor_name
                else:
                    selected_decryptor_for_me_te = user_selection

                # Get ME/TE from the selected decryptor's invention results
                if selected_decryptor_for_me_te and selected_decryptor_for_me_te in invention_results:
                    invention_me = invention_results[selected_decryptor_for_me_te].get("me", 0)
                    invention_te = invention_results[selected_decryptor_for_me_te].get("te", 0)
                    logger.info(f"Using ME={invention_me}, TE={invention_te} from {selected_decryptor_for_me_te}")
                else:
                    logger.warning(f"Could not find ME/TE for decryptor {selected_decryptor_for_me_te}, using defaults")

            except Exception as e:
                logger.error(f"Error calculating invention costs: {e}")
                st.error(f"Failed to calculate invention costs: {e}")
                invention_results = None
        elif is_t2 and not st.session_state.selected_invention_structure:
            st.warning("⚠️ T2 item detected but no invention structure selected. Invention costs will not be calculated.")

        # Now create the job with correct ME/TE
        job = JobQuery(
            item=st.session_state.selected_item_for_display,
            item_id=type_id,
            group_id=group_id,
            runs=runs,
            me=invention_me,  # For T2: ME from invention, for T1: ME from sidebar
            te=invention_te,  # For T2: TE from invention, for T1: TE from sidebar
            material_prices=st.session_state.price_source,
            # Invention parameters
            calculate_invention=is_t2,
            science=st.session_state.science_level,
            advanced_industry=st.session_state.advanced_industry_level,
            industry=st.session_state.industry_level,
            amarr_encryption=st.session_state.amarr_encryption_level,
            caldari_encryption=st.session_state.caldari_encryption_level,
            gallente_encryption=st.session_state.gallente_encryption_level,
            minmatar_encryption=st.session_state.minmatar_encryption_level,
            triglavian_encryption=st.session_state.triglavian_encryption_level,
            upwell_encryption=st.session_state.upwell_encryption_level,
            sleeper_encryption=st.session_state.sleeper_encryption_level,
        )

        logger.info("=" * 80)
        logger.info("=" * 80)
        logger.info("\n")
        logger.info(f"get_costs() with ME={job.me}, TE={job.te}")
        logger.info("=" * 80)
        logger.info("=" * 80)
        logger.info("\n")
        t1 = time.perf_counter()

        results, status_log = get_costs(job, async_mode)
        logger.info(f"Status log: {status_log['success_count']} success, {status_log['error_count']} errors")

        display_log_status(status_log)

        if not results:
            st.error("No results returned. This is likely due to problems with the external industry data API. Please try again later.")
            return

        t2 = time.perf_counter()
        elapsed_time = round((t2 - t1) * 1000, 2)
        logger.info("=" * 80)
        logger.info(f"TIME get_costs() = {elapsed_time} ms")
        logger.info("=" * 80)
        logger.info("\n")

        # Cache the results and parameters (invention was already calculated above for T2 items)
        st.session_state.cost_results = results
        st.session_state.invention_costs = invention_results
        st.session_state.current_job_params = current_job_params
        st.session_state.selected_item_for_display = selected_item

        # Store ME/TE information for display
        if is_t2:
            st.session_state.manufacturing_me = invention_me
            st.session_state.manufacturing_te = invention_te
            st.session_state.me_te_source = f"{selected_decryptor_for_me_te} (Invented BPC)"
        else:
            st.session_state.manufacturing_me = me
            st.session_state.manufacturing_te = te
            st.session_state.me_te_source = "User Input"

        st.rerun()

    # Display results if available (either fresh or cached)
    if (
        st.session_state.cost_results is not None
        and st.session_state.selected_item_for_display == selected_item
    ):
        # Get prices for display
        vale_price = get_4H_price(type_id)
        jita_price = get_jita_price(type_id)
        if jita_price:
            jita_price = float(jita_price)
        if vale_price:
            vale_price = float(vale_price)

        results = st.session_state.cost_results

        build_cost_df = pd.DataFrame.from_dict(results, orient="index")

        structure_rigs = get_structure_rigs()
        build_cost_df["structure_rigs"] = build_cost_df.index.map(structure_rigs)
        build_cost_df["structure_rigs"] = build_cost_df["structure_rigs"].apply(
            lambda x: ", ".join(x)
        )

        # Add invention costs if available (T2 items)
        invention_cost_per_unit = 0.0
        selected_decryptor_name = None

        logger.info(f"runs: {st.session_state.current_job_params.get('runs', 1)}")

        if is_t2 and st.session_state.invention_costs is not None:
            invention_results = st.session_state.invention_costs


            # Check if user has selected a specific decryptor
            user_selection = st.session_state.get("selected_decryptor_for_costs", "Auto (Best Cost)")

            if user_selection == "Auto (Best Cost)":
                # Find the best (lowest) invention cost per unit
                best_invention_cost = float('inf')
                for decryptor_name, inv_data in invention_results.items():
                    cost = inv_data.get("avg_cost_per_unit", 0)
                    if cost < best_invention_cost:
                        best_invention_cost = cost
                        selected_decryptor_name = decryptor_name
                invention_cost_per_unit = best_invention_cost if best_invention_cost != float('inf') else 0.0
            else:
                # Use the user-selected decryptor
                selected_decryptor_name = user_selection
                if selected_decryptor_name in invention_results:
                    invention_cost_per_unit = invention_results[selected_decryptor_name].get("avg_cost_per_unit", 0)
                else:
                    # Fallback to best cost if selected decryptor not found
                    logger.warning(f"Selected decryptor {selected_decryptor_name} not found in results, using best cost")
                    best_invention_cost = float('inf')
                    for decryptor_name, inv_data in invention_results.items():
                        cost = inv_data.get("avg_cost_per_unit", 0)
                        if cost < best_invention_cost:
                            best_invention_cost = cost
                            selected_decryptor_name = decryptor_name
                    invention_cost_per_unit = best_invention_cost if best_invention_cost != float('inf') else 0.0

            # Add invention cost columns to dataframe
            build_cost_df["invention_cost_per_unit"] = invention_cost_per_unit
            build_cost_df["total_production_cost_per_unit"] = (
                build_cost_df["total_cost_per_unit"] + invention_cost_per_unit
            )
            build_cost_df["total_production_cost"] = (
                build_cost_df["total_cost"] + (invention_cost_per_unit * build_cost_df["units"])
            )

            # Sort by total production cost instead
            build_cost_df = build_cost_df.sort_values(by="total_production_cost", ascending=True)
        else:
            build_cost_df = build_cost_df.sort_values(by="total_cost", ascending=True)

        # Get lowest cost metrics (now includes invention if T2)
        if is_t2 and st.session_state.invention_costs is not None:
            total_cost = build_cost_df["total_production_cost"].min()
            low_cost = build_cost_df["total_production_cost_per_unit"].min()
            low_cost_structure = build_cost_df["total_production_cost_per_unit"].idxmin()
        else:
            total_cost = build_cost_df["total_cost"].min()
            low_cost = build_cost_df["total_cost_per_unit"].min()
            low_cost_structure = build_cost_df["total_cost_per_unit"].idxmin()

        low_cost = float(low_cost)
        material_cost = float(
            build_cost_df.loc[low_cost_structure, "total_material_cost"]
        )
        job_cost = float(build_cost_df.loc[low_cost_structure, "total_job_cost"])
        units = build_cost_df.loc[low_cost_structure, "units"]
        material_cost_per_unit = (
            material_cost / build_cost_df.loc[low_cost_structure, "units"]
        )
        job_cost_per_unit = job_cost / build_cost_df.loc[low_cost_structure, "units"]

        col1, col2 = st.columns([0.2, 0.8])
        with col1:
            if is_valid_image_url(url):
                st.image(url)
            else:
                st.image(alt_url, width='stretch')
        with col2:
            st.header(f"Build cost for {selected_item}", divider="violet")

            # Get ME/TE values from session state (correctly shows invented BPC values for T2)
            display_me = st.session_state.get("manufacturing_me", me)
            display_te = st.session_state.get("manufacturing_te", te)
            me_te_source = st.session_state.get("me_te_source", "User Input")

            if is_t2 and st.session_state.invention_costs is not None:
                st.write(
                    f"T2 Production cost for {selected_item} with {runs} runs, {price_source} material price (type_id: {type_id})"
                )
                st.info(f"📋 **Manufacturing BPC**: ME {display_me} / TE {display_te} from {me_te_source}")
            else:
                st.write(
                    f"Build cost for {selected_item} with {runs} runs, ME {display_me}, TE {display_te}, {price_source} material price (type_id: {type_id})"
                )

            col1, col2 = st.columns([0.5, 0.5])
            with col1:
                if is_t2 and st.session_state.invention_costs is not None:
                    st.metric(
                        label="Total Production Cost per unit",
                        value=f"{millify(low_cost, precision=2)} ISK",
                        help=f"Manufacturing + Invention | Structure: {low_cost_structure}",
                    )
                    manufacturing_cost_per_unit = low_cost - invention_cost_per_unit
                    st.markdown(
                        f"**Manufacturing:** {millify(manufacturing_cost_per_unit, precision=2)} ISK | "
                        f"**Invention:** {millify(invention_cost_per_unit, precision=2)} ISK"
                    )
                    st.caption(f"*Using {selected_decryptor_name}*")
                else:
                    st.metric(
                        label="Build cost per unit",
                        value=f"{millify(low_cost, precision=2)} ISK",
                        help=f"Based on the lowest cost structure: {low_cost_structure}",
                    )
                    st.markdown(
                        f"**Materials:** {millify(material_cost_per_unit, precision=2)} ISK | **Job cost:** {millify(job_cost_per_unit, precision=2)} ISK"
                    )
            with col2:
                if is_t2 and st.session_state.invention_costs is not None:
                    st.metric(
                        label="Total Production Cost",
                        value=f"{millify(total_cost, precision=2)} ISK",
                        help=f"Manufacturing + Invention for {units} units"
                    )
                    manufacturing_total = total_cost - (invention_cost_per_unit * units)
                    invention_total = invention_cost_per_unit * units
                    st.markdown(
                        f"**Manufacturing:** {millify(manufacturing_total, precision=2)} ISK | "
                        f"**Invention:** {millify(invention_total, precision=2)} ISK"
                    )
                else:
                    st.metric(
                        label="Total Build Cost",
                        value=f"{millify(total_cost, precision=2)} ISK",
                    )
                    st.markdown(
                        f"**Materials:** {millify(material_cost, precision=2)} ISK | **Job cost:** {millify(job_cost, precision=2)} ISK"
                    )

        if vale_price:
            profit_per_unit_vale = vale_price - low_cost
            percent_profit_vale = ((vale_price - low_cost) / vale_price) * 100

            st.markdown(
                f"**4-HWWF price:** <span style='color: orange;'>{millify(vale_price, precision=2)} ISK</span> ({percent_profit_vale:.2f}% Jita | profit: {millify(profit_per_unit_vale, precision=2)} ISK)",
                unsafe_allow_html=True,
            )

        else:
            st.write("No Vale price data found for this item")

        if jita_price:
            profit_per_unit_jita = jita_price - low_cost
            percent_profit_jita = ((jita_price - low_cost) / jita_price) * 100
            st.markdown(
                f"**Jita price:** <span style='color: orange;'>{millify(jita_price, precision=2)} ISK</span> (profit: {millify(profit_per_unit_jita, precision=2)} ISK {percent_profit_jita:.2f}%)",
                unsafe_allow_html=True,
            )
        else:
            st.write("No price data found for this item")


        display_df, col_config, col_order = display_data(
            build_cost_df, selected_structure, is_t2
        )
        st.dataframe(
            display_df,
            column_config=col_config,
            column_order=col_order,
            width='stretch',
        )
        if st.session_state.super:
            st.markdown(
                """
            <span style="font-weight: bold;">Note:</span> <span style="color: orange;"> Only structures in systems with the supercapital upgrade and configured for supercapital construction are displayed.
            </span>
            """,
                unsafe_allow_html=True,
            )

        # Material breakdown section - always show if we have results
        st.subheader("Material Breakdown")
        results = st.session_state.cost_results

        structure_names_for_materials = sorted(
            list(results.keys())
        )  # Sort alphabetically

        display_material_costs(
                results, selected_structure, structure_names_for_materials
            )

        # Invention costs section - show if T2 item and we have invention results
        if is_t2 and st.session_state.invention_costs is not None:
            st.markdown("---")
            st.markdown("## Invention Costs")
            display_invention_costs(
                st.session_state.invention_costs,
                st.session_state.selected_invention_structure
            )

    else:
        st.subheader("WC Markets Build Cost Tool", divider="violet")
        st.write(
            "Find a build cost for an item by selecting a category, group, and item in the sidebar. The build cost will be calculated for all structures in the database, ordered by cost (lowest to highest) along with a table of materials required and their costs for a selected structure. You can also select a structure to compare the cost to build versus this structure. When you're ready, click the 'Calculate' button."
        )

        st.markdown(
            """

                    - <span style="font-weight: bold; color: orange;">Runs:</span> The number of runs to calculate the cost for.
                    - <span style="font-weight: bold; color: orange;">ME:</span> The material efficiency of the blueprint. (default 0)
                    - <span style="font-weight: bold; color: orange;">TE:</span> The time efficiency of the blueprint. (default 0)
                    - <span style="font-weight: bold; color: orange;">Material price source:</span> The source of the material prices used in the calculations.
                        - *ESI Average* - the CCP average price used in the in-game industry window.
                        - *Jita Sell* - the minimum price of sale orders in Jita.
                        - *Jita Buy* - the maximum price of buy orders in Jita.
                    - <span style="font-weight: bold; color: orange;">Structure:</span> The structure to compare the cost to build versus. (optional)
                    """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":

    main()
