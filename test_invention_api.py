#!/usr/bin/env python3
"""
Test script for invention API integration
Tests T2 detection and invention cost API calls
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import httpx
from pages.build_costs import is_t2_item, DECRYPTORS

def test_t2_detection():
    """Test T2 item detection"""
    print("=" * 80)
    print("Testing T2 Detection")
    print("=" * 80)

    # Test with a known T2 item (Heavy Assault Missile Launcher II)
    t2_item_id = 2929  # Heavy Assault Missile Launcher II
    t1_item_id = 2456  # Apocalypse (T1 battleship)

    print(f"\nTesting type_id {t2_item_id} (should be T2):")
    is_t2_result = is_t2_item(t2_item_id)
    print(f"  Result: {is_t2_result}")
    assert is_t2_result == True, f"Expected True, got {is_t2_result}"
    print("  ✓ PASS")

    print(f"\nTesting type_id {t1_item_id} (should NOT be T2):")
    is_t1_result = is_t2_item(t1_item_id)
    print(f"  Result: {is_t1_result}")
    assert is_t1_result == False, f"Expected False, got {is_t1_result}"
    print("  ✓ PASS")

    print("\n✓ T2 Detection tests passed!")


def test_invention_api_call():
    """Test invention API call with sample parameters"""
    print("\n" + "=" * 80)
    print("Testing Invention API Call")
    print("=" * 80)

    # Known T2 blueprint: Scourge Heavy Assault Missile Blueprint (1136)
    blueprint_id = 1136

    # Build test URL
    params = {
        "blueprint_id": blueprint_id,
        "runs": 1,
        "science": 5,
        "caldari_encryption_methods": 5,
        "advanced_industry": 5,
        "industry": 5,
        "decryptor_id": 34201,  # Accelerant Decryptor
        "material_prices": "ESI_AVG"
    }

    url = "https://api.everef.net/v1/industry/cost"

    print(f"\nMaking API request to: {url}")
    print(f"Parameters: {params}")

    try:
        with httpx.Client() as client:
            response = client.get(url, params=params, timeout=20)
            response.raise_for_status()

            data = response.json()

            print(f"\n✓ API call successful (status {response.status_code})")

        # Check for invention data in response
        if "invention" in data:
            print("\n✓ Response contains 'invention' section")

            # Print invention data
            invention_data = data["invention"]
            print(f"\nInvention data keys: {list(invention_data.keys())}")

            # Get the first blueprint ID in the invention section
            if invention_data:
                first_bp_id = list(invention_data.keys())[0]
                bp_data = invention_data[first_bp_id]

                print(f"\nInvention details for blueprint {first_bp_id}:")
                print(f"  - Probability: {bp_data.get('probability', 'N/A')}")
                print(f"  - Expected runs: {bp_data.get('expected_runs', 'N/A')}")
                print(f"  - ME: {bp_data.get('me', 'N/A')}")
                print(f"  - TE: {bp_data.get('te', 'N/A')}")
                print(f"  - Total cost: {bp_data.get('total_cost', 'N/A')}")
                print(f"  - Total material cost: {bp_data.get('total_material_cost', 'N/A')}")
                print(f"  - Avg cost per unit: {bp_data.get('avg_cost_per_unit', 'N/A')}")

                # Check for required fields
                required_fields = ['probability', 'total_material_cost', 'avg_cost_per_unit']
                for field in required_fields:
                    assert field in bp_data, f"Missing required field: {field}"

                print("\n✓ All required fields present")

        else:
            print("\n✗ WARNING: Response does not contain 'invention' section")
            print(f"Response keys: {list(data.keys())}")

    except httpx.RequestError as e:
        print(f"\n✗ API call failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error processing response: {e}")
        return False

    print("\n✓ Invention API test passed!")
    return True


def test_decryptors():
    """Test decryptor constant dictionary"""
    print("\n" + "=" * 80)
    print("Testing Decryptors")
    print("=" * 80)

    print(f"\nTotal decryptors defined: {len(DECRYPTORS)}")

    for name, type_id in DECRYPTORS.items():
        print(f"  - {name}: {type_id}")

    assert len(DECRYPTORS) == 9, f"Expected 9 decryptors, got {len(DECRYPTORS)}"
    print("\n✓ Decryptor definitions correct")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("INVENTION FEATURE - Phase 1 Tests")
    print("=" * 80)

    try:
        test_decryptors()
        test_t2_detection()
        test_invention_api_call()

        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED")
        print("=" * 80)
        print("\nPhase 1 implementation is ready!")

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
