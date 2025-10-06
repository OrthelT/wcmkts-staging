#!/usr/bin/env python3
"""
Test the fixed invention URL against the API
"""
import httpx

url = "https://api.everef.net/v1/industry/cost"
params = {
    "blueprint_id": 12044,
    "runs": 1,
    "science": 5,
    "advanced_industry": 5,
    "industry": 5,
    "amarr_encryption_methods": 5,
    "caldari_encryption_methods": 5,
    "gallente_encryption_methods": 5,
    "minmatar_encryption_methods": 5,
    "triglavian_encryption_methods": 5,
    "upwell_encryption_methods": 5,
    "sleeper_encryption_methods": 5,
    "security": "NULL_SEC",
    "system_cost_bonus": 0.0,
    "invention_cost": 0.0811,
    "facility_tax": 0.0005,
    "material_prices": "ESI_AVG",
    "decryptor_id": 34201
}

print("Testing fixed invention URL...")
print(f"Blueprint ID: {params['blueprint_id']}")
print(f"Decryptor: 34201 (Accelerant)")

try:
    with httpx.Client() as client:
        response = client.get(url, params=params, timeout=20)
        response.raise_for_status()

        data = response.json()

        if "invention" in data:
            print("\n✓ SUCCESS! API returned invention data")
            invention_data = data["invention"]
            bp_id = list(invention_data.keys())[0]
            bp_data = invention_data[bp_id]

            print(f"\nInvention results for blueprint {bp_id}:")
            print(f"  Probability: {bp_data.get('probability', 0) * 100:.1f}%")
            print(f"  Total material cost: {bp_data.get('total_material_cost', 0):,.2f} ISK")
            print(f"  Avg cost per unit: {bp_data.get('avg_cost_per_unit', 0):,.2f} ISK")
        else:
            print("\n✗ No invention data in response")

except httpx.HTTPStatusError as e:
    print(f"\n✗ HTTP Error: {e}")
    print(f"Response: {e.response.text[:500]}")
except Exception as e:
    print(f"\n✗ Error: {e}")
