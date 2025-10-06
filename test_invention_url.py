#!/usr/bin/env python3
"""
Quick test to verify invention URL construction
"""

# Simulate the parameters that would be sent
blueprint_id = 12044  # Example T2 blueprint
params = [
    f"blueprint_id={blueprint_id}",
    f"runs=1",
    f"science=5",
    f"advanced_industry=5",
    f"industry=5",
    f"amarr_encryption_methods=5",
    f"caldari_encryption_methods=5",
    f"gallente_encryption_methods=5",
    f"minmatar_encryption_methods=5",
    f"triglavian_encryption_methods=5",
    f"upwell_encryption_methods=5",
    f"sleeper_encryption_methods=5",
    f"security=NULL_SEC",
    f"system_cost_bonus=0.0",
    f"invention_cost=0.0811",
    f"facility_tax=0.0005",
    f"material_prices=ESI_AVG",
    f"decryptor_id=34201"  # Accelerant
]

url = f"https://api.everef.net/v1/industry/cost?{'&'.join(params)}"

print("Constructed URL:")
print(url)
print("\nThis should work (no structure_type_id or rig_id)")
