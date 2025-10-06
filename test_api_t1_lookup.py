#!/usr/bin/env python3
"""
Test T1 blueprint lookup via API
"""
import requests

def get_t1_blueprint_for_t2_item(t2_item_id: int):
    """Get the T1 blueprint ID by querying the manufacturing API"""
    try:
        url = f"https://api.everef.net/v1/industry/cost?product_id={t2_item_id}&runs=1&material_prices=ESI_AVG"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if "invention" in data and data["invention"]:
            for t2_bp_id, inv_data in data["invention"].items():
                if "blueprint_id" in inv_data:
                    t1_bp_id = inv_data["blueprint_id"]
                    print(f"✓ Found T1 blueprint {t1_bp_id} for T2 item {t2_item_id}")
                    print(f"  T2 Blueprint ID: {t2_bp_id}")
                    return t1_bp_id

        print(f"✗ No invention data found for T2 item {t2_item_id}")
        return None

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


# Test with Enyo (12044)
print("Testing with Enyo (T2 Assault Frigate, ID 12044)")
print("="*60)
bp_id = get_t1_blueprint_for_t2_item(12044)

if bp_id:
    print(f"\nNow testing invention API with T1 blueprint {bp_id}...")
    import httpx
    url = "https://api.everef.net/v1/industry/cost"
    params = {
        "blueprint_id": bp_id,
        "runs": 1,
        "science": 5,
        "gallente_encryption_methods": 5,
        "advanced_industry": 5,
        "industry": 5,
        "material_prices": "ESI_AVG",
        "decryptor_id": 34201
    }

    with httpx.Client() as client:
        response = client.get(url, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if "invention" in data:
                print("✓ Invention API call successful!")
                inv_data = data["invention"]
                print(f"  T2 blueprints returned: {list(inv_data.keys())}")
                for bp_id, details in inv_data.items():
                    print(f"    - BP {bp_id}: {details.get('probability', 0)*100:.1f}% success")
        else:
            print(f"✗ API error: {response.status_code}")
