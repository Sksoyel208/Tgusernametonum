import os
import duckdb
from fastapi import FastAPI, Query
from huggingface_hub import hf_hub_download

app = FastAPI(title="Telegram Lookup")

DB_PATH = None

def get_db():
    global DB_PATH
    if DB_PATH is None or not os.path.exists(DB_PATH or ""):
        token = os.getenv("HF_TOKEN")
        DB_PATH = hf_hub_download(
            repo_id="Watchhrr/Telegram",
            filename="Midnight_Master_v2.db",
            repo_type="dataset",
            token=token
        )
    return DB_PATH

@app.get("/search")
def search(q: str = Query(...)):
    try:
        path = get_db()
        con = duckdb.connect(':memory:')
        con.execute("INSTALL sqlite; LOAD sqlite;")
        
        q = q.strip()
        if q.startswith("@"):
            sql = f"SELECT user_id FROM sqlite_scan('{path}', 'telegram_users') WHERE LOWER(user_id) LIKE '%;{q[1:].lower()};%' LIMIT 10"
        elif q.startswith("+"):
            sql = f"SELECT user_id FROM sqlite_scan('{path}', 'telegram_users') WHERE user_id LIKE '%;{q[1:]};%' LIMIT 10"
        elif q.isdigit():
            sql = f"SELECT user_id FROM sqlite_scan('{path}', 'telegram_users') WHERE user_id LIKE '{q};%' LIMIT 10"
        else:
            sql = f"SELECT user_id FROM sqlite_scan('{path}', 'telegram_users') WHERE LOWER(user_id) LIKE '%;{q.lower()};%' LIMIT 10"
        
        rows = con.execute(sql).fetchall()
        con.close()
        
        results = []
        for r in rows:
            p = r[0].split(';')
            if len(p) >= 4:
                results.append({
                    "user_id": p[0],
                    "phone": p[1] if p[1] != "0" else None,
                    "username": f"@{p[2]}" if p[2] else None,
                    "name": p[3] if p[3] != "0" else None
                })
        
        return {"count": len(results), "results": results}
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}
