from config import DatabaseConfig
import json
from sqlalchemy import text

def find_invention_rig(structure_name):
    db = DatabaseConfig("build_cost")

    with open("invention_rigs.json", "r") as f:
        invention_rigs = json.load(f)

    engine = db.engine

    irigs = [v for k, v in invention_rigs.items()]
    structure = structure_name

    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT * FROM structures_with_rig_ids WHERE structure = '{structure}'"))
        structure = result.fetchall()
        structure_rigs = structure[0].rig_1_id, structure[0].rig_2_id, structure[0].rig_3_id
    conn.close()

    for rig in structure_rigs:
        if rig in irigs:
            return rig
        else:
            return None

if __name__ == "__main__":
    pass