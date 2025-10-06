#!/usr/bin/env python3
"""
Test if the API can work with T2 blueprint IDs or needs T1
"""
import httpx

# Try with T2 blueprint (Enyo Blueprint = 12045)
print("Testing with T2 blueprint ID (Enyo Blueprint = 12045)...")
url = "https://api.everef.net/v1/industry/cost"
params = {
    "blueprint_id": 12045,  # Enyo Blueprint (T2)
    "runs": 1,
    "science": 5,
    "caldari_encryption_methods": 5,
    "advanced_industry": 5,
    "industry": 5,
    "material_prices": "ESI_AVG"
}

try:
    with httpx.Client() as client:
        response = client.get(url, params=params, timeout=20)
        if response.status_code == 200:
            print("✓ T2 blueprint works!")
            data = response.json()
            if "invention" in data:
                print("  Has invention data")
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"  Message: {response.text[:200]}")
except Exception as e:
    print(f"✗ Exception: {e}")

print("\n" + "="*60)
print("Testing with T1 blueprint ID (Atron Blueprint = 955)...")
params["blueprint_id"] = 955  # Atron Blueprint (T1)

try:
    with httpx.Client() as client:
        response = client.get(url, params=params, timeout=20)
        if response.status_code == 200:
            print("✓ T1 blueprint works!")
            data = response.json()
            if "invention" in data:
                print("  Has invention data")
                inv_data = data["invention"]
                print(f"  Returns T2 blueprint IDs: {list(inv_data.keys())}")
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"  Message: {response.text[:200]}")
except Exception as e:
    print(f"✗ Exception: {e}")
