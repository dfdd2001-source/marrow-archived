import json
import os
import psycopg

# Phase-0 审核流原型的种子数据（见 main.py 模块注释；当前产品后端是 platform.py）
CORE_FILES = {
    "ladr-3a-3c": "../app/cores/ladr-3a-3c.json",
    "ladr-5a": "../app/cores/ladr-5a.json",
}

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

DEFAULT_DB = "host=localhost dbname=marrow_dev user=marrow password=marrow_dev"
conn = psycopg.connect(os.environ.get("MARROW_DATABASE", DEFAULT_DB))
cur = conn.cursor()

for core_id, path in CORE_FILES.items():
    with open(os.path.join(BASE, path), "r", encoding="utf-8") as f:
        data = json.load(f)

    cur.execute(
        "INSERT INTO cores (id, topic, source_book, source_section) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (id) DO NOTHING",
        (core_id, data["topic"], data["source"]["book"], data["source"]["section"]),
    )

    cur.execute(
        "INSERT INTO core_versions (core_id, version_number, data, extracted_by, review_status, reviewed_by) "
        "VALUES (%s, 1, %s, %s, 'approved', %s) RETURNING id",
        (core_id, json.dumps(data), "claude", "phase0-manual-review"),
    )
    version_id = cur.fetchone()[0]

    cur.execute(
        "UPDATE cores SET active_version_id = %s, updated_at = now() WHERE id = %s",
        (version_id, core_id),
    )
    print(f"seeded {core_id} as version {version_id}")

conn.commit()
cur.close()
conn.close()
print("done")
