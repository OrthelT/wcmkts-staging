#!/usr/bin/env python3
"""
Test T1 blueprint lookup for T2 items
"""
import sqlite3

def get_t1_blueprint_for_t2_item(t2_item_id: int):
    """Get the T1 blueprint ID needed to invent a T2 item"""
    conn = sqlite3.connect('sde_lite.db')
    cursor = conn.cursor()

    # First, get the T2 item's group and name info
    cursor.execute("SELECT typeName, groupID FROM sdeTypes WHERE typeID = ?", (t2_item_id,))
    t2_item = cursor.fetchone()

    if not t2_item:
        print(f"T2 item {t2_item_id} not found in SDE")
        return None

    t2_name, group_id = t2_item
    print(f"T2 Item: {t2_name} (group {group_id})")

    # Try to find T1 version by removing " II" from name and finding in same group
    t1_name = t2_name.replace(" II", "")
    print(f"Looking for T1 item: {t1_name}")

    cursor.execute(
        "SELECT typeID FROM sdeTypes WHERE typeName = ? AND groupID = ? AND (metaGroupID != 2 OR metaGroupID IS NULL)",
        (t1_name, group_id)
    )
    t1_item = cursor.fetchone()

    if not t1_item:
        print(f"Could not find T1 version by name, trying invMetaTypes...")
        # Try alternative: look for parent type via invMetaTypes
        cursor.execute("SELECT parentTypeID FROM invMetaTypes WHERE typeID = ?", (t2_item_id,))
        parent = cursor.fetchone()
        if parent:
            t1_item_id = parent[0]
            cursor.execute("SELECT typeName FROM sdeTypes WHERE typeID = ?", (t1_item_id,))
            parent_name = cursor.fetchone()
            if parent_name:
                t1_name = parent_name[0]
                print(f"Found parent T1 item via invMetaTypes: {t1_name} (ID: {t1_item_id})")
        else:
            print(f"No parent type found for {t2_name}")
            conn.close()
            return None
    else:
        t1_item_id = t1_item[0]
        print(f"Found T1 item: {t1_name} (ID: {t1_item_id})")

    # Now find the blueprint for the T1 item
    # Blueprints typically have the same name + " Blueprint"
    bp_pattern = f"%{t1_name}%Blueprint%"
    cursor.execute(
        "SELECT t.typeID, t.typeName FROM sdeTypes t "
        "WHERE t.typeName LIKE ? "
        "AND t.groupID IN (SELECT groupID FROM invGroups WHERE categoryID = 9)",
        (bp_pattern,)
    )
    blueprint = cursor.fetchone()

    conn.close()

    if blueprint:
        print(f"Found T1 blueprint: {blueprint[1]} (ID: {blueprint[0]})")
        return blueprint[0]
    else:
        print(f"Could not find blueprint for T1 item {t1_name}")
        return None


# Test with Enyo
print("="*60)
print("Testing T1 blueprint lookup for Enyo")
print("="*60)
bp_id = get_t1_blueprint_for_t2_item(12044)
if bp_id:
    print(f"\n✓ SUCCESS: Blueprint ID = {bp_id}")
else:
    print(f"\n✗ FAILED: Could not find blueprint")
