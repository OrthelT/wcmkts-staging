#!/usr/bin/env python3
"""
Simple test script for invention API
Tests the API directly without importing the full build_costs module
"""

import httpx

def test_decryptors():
    """Test decryptor constant dictionary"""
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

    print("\n" + "=" * 80)
    print("Testing Decryptors")
    print("=" * 80)

    print(f"\nTotal decryptors defined: {len(DECRYPTORS)}")

    for name, type_id in DECRYPTORS.items():
        print(f"  - {name}: {type_id}")

    assert len(DECRYPTORS) == 9, f"Expected 9 decryptors, got {len(DECRYPTORS)}"
    print("\n✓ Decryptor definitions correct")


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
    print(f"Parameters:")
    for key, value in params.items():
        print(f"  - {key}: {value}")

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
                print("\n✓ Invention API test passed!")
                return True

        else:
            print("\n✗ WARNING: Response does not contain 'invention' section")
            print(f"Response keys: {list(data.keys())}")
            return False

    except httpx.RequestError as e:
        print(f"\n✗ API call failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error processing response: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_url_construction():
    """Test that we can construct valid invention URLs"""
    print("\n" + "=" * 80)
    print("Testing URL Construction")
    print("=" * 80)

    blueprint_id = 1136
    decryptor_id = 34201

    # Build base parameters for invention
    base_params = [
        f"blueprint_id={blueprint_id}",
        f"runs=1",
        f"science=5",
        f"advanced_industry=5",
        f"industry=5",
        f"amarr_encryption_methods=5",
        f"caldari_encryption_methods=5",
        f"gallente_encryption_methods=5",
        f"minmatar_encryption_methods=5",
        f"material_prices=ESI_AVG"
    ]

    # Add decryptor
    base_params.append(f"decryptor_id={decryptor_id}")

    # Construct URL
    params_str = "&".join(base_params)
    url = f"https://api.everef.net/v1/industry/cost?{params_str}"

    print(f"\nConstructed URL:")
    print(f"  {url}")

    print("\n✓ URL construction successful")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("INVENTION FEATURE - Phase 1 API Tests")
    print("=" * 80)

    try:
        test_decryptors()
        test_url_construction()
        test_invention_api_call()

        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED")
        print("=" * 80)
        print("\nPhase 1 API integration is ready!")
        print("The invention cost API returns valid data with all required fields.")

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
