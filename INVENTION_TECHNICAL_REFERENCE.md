# Invention Cost Calculator - Technical Reference

## Quick Reference for Implementation

This document provides detailed technical specifications for implementing the Invention Cost Calculator feature.

---

## 1. API Integration

### 1.1 Endpoint Specification

**Base URL**: `https://api.everef.net/v1/industry/cost`

**Method**: GET

**Query Parameters**:

```python
INVENTION_PARAMS = {
    # Required
    "blueprint_id": int,              # Source T1 blueprint ID
    "runs": int,                      # Number of invention jobs

    # Optional - Decryptor
    "decryptor_id": int | None,       # None or type ID (34201-34208)

    # Material Pricing
    "material_prices": str,           # "ESI_AVG" | "FUZZWORK_JITA_SELL_MIN" | "FUZZWORK_JITA_BUY_MAX"

    # Skills (all default to 5)
    "science": int,                   # 0-5
    "advanced_industry": int,         # 0-5
    "industry": int,                  # 0-5
    "amarr_encryption_methods": int,  # 0-5
    "caldari_encryption_methods": int,# 0-5
    "gallente_encryption_methods": int,# 0-5
    "minmatar_encryption_methods": int,# 0-5
    "triglavian_encryption_methods": int,# 0-5
    "upwell_encryption_methods": int, # 0-5
    "sleeper_encryption_methods": int,# 0-5

    # System/Facility (optional)
    "invention_cost": float,          # System cost index for invention
    "facility_tax": float,            # Facility tax rate (0.0-1.0)
    "system_cost_bonus": float,       # System cost bonus
    "security": str,                  # "HIGH_SEC" | "LOW_SEC" | "NULL_SEC"

    # Other
    "alpha": bool,                    # Alpha clone calculation (default False)
}
```

### 1.2 Response Structure

```json
{
  "invention": {
    "12619": {                        // T2 blueprint type ID (output)
      "product_id": 12619,
      "blueprint_id": 1136,           // Source T1 blueprint ID
      "runs": 1.0,
      "time": "PT5H23M",

      // Probability & Outcomes
      "probability": 0.595,           // Success chance (0.0-1.0)
      "runs_per_copy": 11,            // Runs on invented BPC
      "units_per_run": 5000,          // Units produced per run
      "expected_copies": 0.595,       // Expected BPCs per job
      "expected_runs": 6.545,         // Expected runs from expected copies
      "expected_units": 32725.0,      // Expected total units

      // Blueprint Stats
      "me": 4,                        // Material Efficiency of invented BPC
      "te": 14,                       // Time Efficiency of invented BPC

      // Costs
      "total_material_cost": 554627.49,
      "total_job_cost": 73,
      "total_cost": 554700.49,
      "job_cost_base": 1815,

      // Averaged Costs (accounting for probability)
      "avg_time_per_copy": "PT9H2M51.428S",
      "avg_time_per_run": "PT49M21.038S",
      "avg_time_per_unit": "PT0.592S",
      "avg_cost_per_copy": 932269.73,  // Important: Cost per SUCCESSFUL invention
      "avg_cost_per_run": 84751.79,
      "avg_cost_per_unit": 16.95,      // Important: Invention cost per final unit

      // Materials (includes datacores + decryptor if used)
      "materials": {
        "20412": {                    // Datacore - Caldari Starship Engineering
          "type_id": 20412,
          "quantity": 1.0,
          "cost_per_unit": 97532.32,
          "cost": 97532.32
        },
        "20414": {                    // Datacore - Missile Launcher Design
          "type_id": 20414,
          "quantity": 1.0,
          "cost_per_unit": 97922.97,
          "cost": 97922.97
        },
        "34201": {                    // Accelerant Decryptor (if used)
          "type_id": 34201,
          "quantity": 1.0,
          "cost_per_unit": 359172.2,
          "cost": 359172.2
        }
      },
      "materials_volume": 0.3,
      "product_volume": 0.01,
      "estimated_item_value": 90766,

      // System/Structure
      "system_cost_index": 0,
      "system_cost_bonuses": 0,
      "facility_tax": 0,
      "scc_surcharge": 73,
      "alpha_clone_tax": 0
    }
  },
  "manufacturing": { /* ... */ },
  "copying": { /* ... */ },
  "input": { /* Echo of input parameters */ }
}
```

---

## 2. Database Queries

### 2.1 Detect T2 Items

**Database**: `sde_lite.db`

```sql
-- Check if item is Tech II
SELECT metaGroupID
FROM sdeTypes
WHERE typeID = ?
  AND metaGroupID = 2;
```

**Python Implementation**:

```python
def is_t2_item(type_id: int) -> bool:
    """Check if item requires invention (Tech II)"""
    import sqlite3

    conn = sqlite3.connect('sde_lite.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT metaGroupID FROM sdeTypes WHERE typeID = ? AND metaGroupID = 2",
        (type_id,)
    )
    result = cursor.fetchone()
    conn.close()

    return result is not None
```

### 2.2 Get Decryptor Info

**Database**: `sde_lite.db`

```sql
-- Get all decryptors
SELECT typeID, typeName
FROM sdeTypes
WHERE groupID = 1304
ORDER BY typeID;
```

**Expected Results**:
```
34201 | Accelerant Decryptor
34202 | Attainment Decryptor
34203 | Augmentation Decryptor
34204 | Parity Decryptor
34205 | Process Decryptor
34206 | Symmetry Decryptor
34207 | Optimized Attainment Decryptor
34208 | Optimized Augmentation Decryptor
```

### 2.3 Get T2 Blueprint from T1 Item

**Problem**: Given a T1 blueprint ID, find the T2 blueprint ID that results from invention

**Solution**: The API response provides this in `invention.<t2_blueprint_id>`, so no query needed

---

## 3. Cost Calculation Formulas

### 3.1 Invention Cost Per Unit

The API provides `avg_cost_per_unit` which already accounts for probability:

```python
invention_cost_per_unit = response["invention"][t2_bp_id]["avg_cost_per_unit"]
```

**Manual Calculation** (if needed):
```python
total_invention_cost = response["invention"][t2_bp_id]["total_cost"]
expected_units = response["invention"][t2_bp_id]["expected_units"]

avg_cost_per_unit = total_invention_cost / expected_units
```

### 3.2 Combined T2 Production Cost

```python
def calculate_t2_total_cost(
    invention_result: dict,
    manufacturing_result: dict
) -> dict:
    """
    Calculate total T2 production cost

    Args:
        invention_result: Data from response["invention"][t2_bp_id]
        manufacturing_result: Data from response["manufacturing"][product_id]

    Returns:
        dict with combined cost metrics
    """

    # Invention cost per unit (already amortized)
    invention_cost_per_unit = invention_result["avg_cost_per_unit"]

    # Manufacturing cost per unit
    mfg_cost_per_unit = manufacturing_result["total_cost_per_unit"]

    # Total cost per unit
    total_cost_per_unit = invention_cost_per_unit + mfg_cost_per_unit

    # Units produced
    units = manufacturing_result["units"]

    return {
        "invention_cost_per_unit": invention_cost_per_unit,
        "manufacturing_cost_per_unit": mfg_cost_per_unit,
        "total_cost_per_unit": total_cost_per_unit,
        "total_cost": total_cost_per_unit * units,
        "units": units,

        # Breakdown percentages
        "invention_pct": invention_cost_per_unit / total_cost_per_unit,
        "manufacturing_pct": mfg_cost_per_unit / total_cost_per_unit,

        # Additional metrics
        "invention_probability": invention_result["probability"],
        "me": invention_result["me"],
        "te": invention_result["te"],
        "runs_per_copy": invention_result["runs_per_copy"]
    }
```

### 3.3 Profit Calculation

```python
def calculate_profit_margin(
    total_production_cost: float,
    market_price: float
) -> dict:
    """Calculate profit margin for T2 item"""

    profit = market_price - total_production_cost
    margin_pct = (profit / market_price) * 100 if market_price > 0 else 0
    markup_pct = (profit / total_production_cost) * 100 if total_production_cost > 0 else 0

    return {
        "profit_per_unit": profit,
        "profit_margin_pct": margin_pct,      # (Profit / Revenue) * 100
        "markup_pct": markup_pct,              # (Profit / Cost) * 100
        "market_price": market_price,
        "production_cost": total_production_cost
    }
```

---

## 4. Code Examples

### 4.1 Complete Invention Cost Fetcher

```python
async def fetch_invention_costs_for_decryptors(
    blueprint_id: int,
    runs: int,
    skills: dict,
    material_prices: str = "ESI_AVG"
) -> dict:
    """
    Fetch invention costs for all decryptor options

    Args:
        blueprint_id: T1 blueprint type ID
        runs: Number of invention jobs
        skills: Dict of skill levels
        material_prices: Price source

    Returns:
        dict: {
            "None": {...},
            "Accelerant Decryptor": {...},
            ...
        }
    """
    import asyncio
    import httpx

    DECRYPTORS = {
        "None": None,
        "Accelerant Decryptor": 34201,
        "Attainment Decryptor": 34202,
        "Augmentation Decryptor": 34203,
        "Parity Decryptor": 34204,
        "Process Decryptor": 34205,
        "Symmetry Decryptor": 34206,
        "Optimized Attainment Decryptor": 34207,
        "Optimized Augmentation Decryptor": 34208,
    }

    async def fetch_one(client, decryptor_name, decryptor_id):
        params = {
            "blueprint_id": blueprint_id,
            "runs": runs,
            "material_prices": material_prices,
            **skills
        }
        if decryptor_id:
            params["decryptor_id"] = decryptor_id

        url = "https://api.everef.net/v1/industry/cost"
        response = await client.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        # Extract invention data
        invention_data = data.get("invention", {})
        if not invention_data:
            return decryptor_name, None, "No invention data"

        # Get the first (and usually only) invention result
        t2_bp_id = next(iter(invention_data.keys()))
        return decryptor_name, invention_data[t2_bp_id], None

    results = {}
    errors = {}

    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_one(client, name, dec_id)
            for name, dec_id in DECRYPTORS.items()
        ]

        for task in asyncio.as_completed(tasks):
            decryptor_name, data, error = await task
            if data:
                results[decryptor_name] = data
            if error:
                errors[decryptor_name] = error

    return results
```

### 4.2 Display Invention Comparison Table

```python
def display_invention_comparison(invention_results: dict):
    """Display comparison table of invention costs by decryptor"""
    import pandas as pd
    import streamlit as st

    # Build dataframe
    rows = []
    for decryptor_name, data in invention_results.items():
        rows.append({
            "Decryptor": decryptor_name,
            "Success %": f"{data['probability'] * 100:.1f}%",
            "Cost/Copy": data['avg_cost_per_copy'],
            "Cost/Run": data['avg_cost_per_run'],
            "Cost/Unit": data['avg_cost_per_unit'],
            "ME": data['me'],
            "TE": data['te'],
            "Runs/Copy": data['runs_per_copy'],
            "Material Cost": data['total_material_cost']
        })

    df = pd.DataFrame(rows)

    # Sort by cost per unit (ascending)
    df = df.sort_values('Cost/Unit')

    # Column configuration
    col_config = {
        "Decryptor": st.column_config.TextColumn("Decryptor", width="medium"),
        "Success %": st.column_config.TextColumn("Success Rate", width="small"),
        "Cost/Copy": st.column_config.NumberColumn(
            "Avg Cost/Copy",
            format="%.0f ISK",
            help="Average cost per successful invention (accounting for failures)"
        ),
        "Cost/Run": st.column_config.NumberColumn(
            "Avg Cost/Run",
            format="%.0f ISK"
        ),
        "Cost/Unit": st.column_config.NumberColumn(
            "Avg Cost/Unit",
            format="%.2f ISK",
            help="Invention cost per final manufactured unit"
        ),
        "ME": st.column_config.NumberColumn("ME", width="small"),
        "TE": st.column_config.NumberColumn("TE", width="small"),
        "Runs/Copy": st.column_config.NumberColumn("Runs/Copy", width="small"),
        "Material Cost": st.column_config.NumberColumn(
            "Material Cost",
            format="%.0f ISK",
            help="Total material cost (datacores + decryptor)"
        )
    }

    # Display table
    st.dataframe(
        df,
        column_config=col_config,
        hide_index=True,
        use_container_width=True
    )

    # Highlight lowest cost
    min_cost_idx = df['Cost/Unit'].idxmin()
    best_decryptor = df.loc[min_cost_idx, 'Decryptor']
    st.info(f"💡 Lowest cost: **{best_decryptor}** at {df.loc[min_cost_idx, 'Cost/Unit']:.2f} ISK/unit")
```

### 4.3 Skills Input UI Component

```python
def render_skills_input() -> dict:
    """Render skills configuration UI and return skill levels"""
    import streamlit as st

    with st.sidebar.expander("⚙️ Skills Configuration", expanded=False):
        st.markdown("Configure your character skills for invention calculations")

        # Core skills
        st.subheader("Core Skills")
        science = st.slider("Science", 0, 5, 5,
            help="Base science skill. +4% success per level")
        advanced_industry = st.slider("Advanced Industry", 0, 5, 5,
            help="Reduces job costs")
        industry = st.slider("Industry", 0, 5, 5,
            help="Reduces manufacturing time/cost")

        # Encryption methods
        st.subheader("Encryption Methods")
        st.caption("Race-specific skills. +2% success per level for matching race.")

        col1, col2 = st.columns(2)
        with col1:
            amarr_enc = st.slider("Amarr", 0, 5, 5, key="amarr")
            caldari_enc = st.slider("Caldari", 0, 5, 5, key="caldari")
            gallente_enc = st.slider("Gallente", 0, 5, 5, key="gallente")
            minmatar_enc = st.slider("Minmatar", 0, 5, 5, key="minmatar")

        with col2:
            triglavian_enc = st.slider("Triglavian", 0, 5, 5, key="triglavian")
            upwell_enc = st.slider("Upwell", 0, 5, 5, key="upwell")
            sleeper_enc = st.slider("Sleeper", 0, 5, 5, key="sleeper")

        # Preset buttons
        st.subheader("Presets")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("All 5"):
                st.session_state.update({
                    'science': 5, 'advanced_industry': 5, 'industry': 5,
                    'amarr': 5, 'caldari': 5, 'gallente': 5, 'minmatar': 5,
                    'triglavian': 5, 'upwell': 5, 'sleeper': 5
                })
                st.rerun()
        with col2:
            if st.button("All 4"):
                st.session_state.update({
                    'science': 4, 'advanced_industry': 4, 'industry': 4,
                    'amarr': 4, 'caldari': 4, 'gallente': 4, 'minmatar': 4,
                    'triglavian': 4, 'upwell': 4, 'sleeper': 4
                })
                st.rerun()
        with col3:
            if st.button("All 3"):
                st.session_state.update({
                    'science': 3, 'advanced_industry': 3, 'industry': 3,
                    'amarr': 3, 'caldari': 3, 'gallente': 3, 'minmatar': 3,
                    'triglavian': 3, 'upwell': 3, 'sleeper': 3
                })
                st.rerun()

    return {
        "science": science,
        "advanced_industry": advanced_industry,
        "industry": industry,
        "amarr_encryption_methods": amarr_enc,
        "caldari_encryption_methods": caldari_enc,
        "gallente_encryption_methods": gallente_enc,
        "minmatar_encryption_methods": minmatar_enc,
        "triglavian_encryption_methods": triglavian_enc,
        "upwell_encryption_methods": upwell_enc,
        "sleeper_encryption_methods": sleeper_enc,
    }
```

---

## 5. Testing Utilities

### 5.1 Test Data

```python
# Test cases for validation
T2_TEST_ITEMS = {
    # Ammunition
    "Scourge Rage HAM": {
        "t1_blueprint_id": 1136,
        "t2_product_id": 221,  # Scourge Rage Heavy Assault Missile
        "t2_blueprint_id": 12619,
        "expected_datacores": ["Caldari Starship Engineering", "Missile Launcher Design"],
        "expected_success_rate_range": (0.40, 0.60)  # Without decryptor, L5 skills
    },

    # Frigate
    "Crow": {
        "t1_blueprint_id": 11176,  # Condor blueprint
        "t2_product_id": 11176,    # Crow
        "expected_datacores": ["Caldari Starship Engineering", "Gravimetric Engineering"],
    },

    # Module
    "Heavy Assault Missile Launcher II": {
        "t1_blueprint_id": 3514,   # Arbalest Heavy Missile Launcher blueprint
        "t2_product_id": 3518,     # Heavy Assault Missile Launcher II
        "expected_datacores": ["Missile Launcher Design", "Gravimetric Engineering"],
    }
}
```

### 5.2 Validation Function

```python
def validate_invention_result(result: dict, test_case: dict) -> list[str]:
    """
    Validate invention API result against expected values

    Returns:
        list of error messages (empty if all valid)
    """
    errors = []

    # Check probability is in reasonable range
    prob = result.get("probability", 0)
    if "expected_success_rate_range" in test_case:
        min_prob, max_prob = test_case["expected_success_rate_range"]
        if not (min_prob <= prob <= max_prob):
            errors.append(
                f"Probability {prob:.2%} outside expected range "
                f"{min_prob:.2%}-{max_prob:.2%}"
            )

    # Check probability is between 0 and 1
    if not (0 <= prob <= 1):
        errors.append(f"Invalid probability: {prob}")

    # Check ME/TE are reasonable
    me = result.get("me", 0)
    te = result.get("te", 0)
    if not (-10 <= me <= 10):
        errors.append(f"Invalid ME: {me}")
    if not (-20 <= te <= 20):
        errors.append(f"Invalid TE: {te}")

    # Check costs are positive
    if result.get("total_cost", 0) <= 0:
        errors.append("Total cost must be positive")
    if result.get("avg_cost_per_unit", 0) <= 0:
        errors.append("Avg cost per unit must be positive")

    # Check expected values are consistent
    expected_copies = result.get("expected_copies", 0)
    if not (0 < expected_copies <= 1):
        errors.append(f"Invalid expected_copies: {expected_copies}")

    return errors
```

### 5.3 Performance Test

```python
async def benchmark_invention_calculation():
    """Benchmark invention cost calculation performance"""
    import time
    import asyncio

    test_blueprint_id = 1136  # Scourge HAM
    skills = {
        "science": 5,
        "advanced_industry": 5,
        "industry": 5,
        "caldari_encryption_methods": 5,
        # ... other skills
    }

    start = time.perf_counter()
    results = await fetch_invention_costs_for_decryptors(
        blueprint_id=test_blueprint_id,
        runs=1,
        skills=skills
    )
    elapsed = time.perf_counter() - start

    print(f"Fetched {len(results)} decryptor options in {elapsed:.2f}s")
    print(f"Average: {elapsed/len(results):.2f}s per decryptor")

    return elapsed
```

---

## 6. Error Handling

### 6.1 Common Errors

```python
class InventionError(Exception):
    """Base exception for invention calculations"""
    pass

class NotInventableError(InventionError):
    """Item is not a T2 item or cannot be invented"""
    pass

class InventionAPIError(InventionError):
    """API returned error or unexpected data"""
    pass

class InvalidSkillsError(InventionError):
    """Skill levels are invalid"""
    pass

def handle_invention_errors(func):
    """Decorator to handle common invention calculation errors"""
    import functools
    import streamlit as st

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except NotInventableError as e:
            st.warning(f"⚠️ This item cannot be invented: {e}")
            return None
        except InventionAPIError as e:
            st.error(f"❌ API Error: {e}")
            return None
        except InvalidSkillsError as e:
            st.error(f"❌ Invalid skills: {e}")
            return None
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
            logger.exception("Unexpected error in invention calculation")
            return None

    return wrapper
```

---

## 7. Performance Optimization

### 7.1 Caching Strategy

```python
from functools import lru_cache
import hashlib
import json

def cache_key_from_params(**params) -> str:
    """Generate cache key from parameters"""
    # Sort keys for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True)
    return hashlib.md5(sorted_params.encode()).hexdigest()

@st.cache_data(ttl=3600)
def get_invention_costs_cached(
    blueprint_id: int,
    runs: int,
    skills_hash: str,
    material_prices: str
):
    """Cached version of invention cost calculation"""
    # Reconstruct skills from hash or pass through
    # Call actual calculation
    # Return results
    pass
```

### 7.2 Batch Optimization

```python
# Instead of 8 separate API calls (one per decryptor),
# could potentially batch if API supports it
# Currently API doesn't support batch, so use async concurrency

# Current approach (GOOD):
async with httpx.AsyncClient() as client:
    tasks = [fetch_one(client, name, dec_id) for name, dec_id in DECRYPTORS.items()]
    results = await asyncio.gather(*tasks)

# Limit concurrency to avoid rate limiting
semaphore = asyncio.Semaphore(6)  # Max 6 concurrent requests
```

---

## 8. Constants & Enums

### 8.1 Decryptors

```python
from enum import Enum

class Decryptor(Enum):
    NONE = None
    ACCELERANT = 34201
    ATTAINMENT = 34202
    AUGMENTATION = 34203
    PARITY = 34204
    PROCESS = 34205
    SYMMETRY = 34206
    OPTIMIZED_ATTAINMENT = 34207
    OPTIMIZED_AUGMENTATION = 34208

    @classmethod
    def get_name(cls, type_id: int | None) -> str:
        """Get display name for decryptor type ID"""
        for dec in cls:
            if dec.value == type_id:
                return dec.name.replace("_", " ").title()
        return "Unknown"

    @classmethod
    def get_all(cls) -> dict[str, int | None]:
        """Get all decryptors as dict"""
        return {
            dec.name.replace("_", " ").title(): dec.value
            for dec in cls
        }
```

### 8.2 Material Price Sources

```python
class MaterialPriceSource(Enum):
    ESI_AVG = "ESI_AVG"
    JITA_SELL = "FUZZWORK_JITA_SELL_MIN"
    JITA_BUY = "FUZZWORK_JITA_BUY_MAX"

    def display_name(self) -> str:
        return {
            "ESI_AVG": "ESI Average",
            "FUZZWORK_JITA_SELL_MIN": "Jita Sell",
            "FUZZWORK_JITA_BUY_MAX": "Jita Buy"
        }[self.value]
```

---

## 9. Logging

### 9.1 Recommended Log Points

```python
from logging_config import setup_logging

logger = setup_logging(__name__)

# 1. Detection
logger.info(f"Item {type_id} is T2, enabling invention calculations")

# 2. API Requests
logger.debug(f"Fetching invention costs for blueprint {blueprint_id} with {len(decryptors)} decryptors")

# 3. Results
logger.info(f"Successfully calculated invention costs: {len(results)} decryptors in {elapsed:.2f}s")

# 4. Errors
logger.error(f"Failed to fetch invention cost for {decryptor_name}: {error}")

# 5. Performance
logger.debug(f"Invention calculation took {elapsed:.2f}s ({elapsed/len(results):.2f}s per decryptor)")
```

---

## 10. Integration Checklist

When integrating into `pages/build_costs.py`:

- [ ] Import necessary modules (asyncio, httpx, etc.)
- [ ] Add DECRYPTORS constant
- [ ] Extend JobQuery dataclass
- [ ] Add T2 detection function
- [ ] Add skills input UI to sidebar
- [ ] Create invention cost calculation function
- [ ] Add invention results to session state
- [ ] Create invention comparison table display
- [ ] Create material breakdown for invention
- [ ] Add combined cost calculation
- [ ] Update main calculation flow to call invention for T2 items
- [ ] Add caching for invention results
- [ ] Add error handling
- [ ] Add logging
- [ ] Test with multiple T2 item types
- [ ] Update documentation

---

**Document Version**: 1.0
**Date**: 2025-10-05
**Purpose**: Technical reference for developers implementing invention cost feature
