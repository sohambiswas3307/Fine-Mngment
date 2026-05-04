import sqlite3

DB_PATH = r"D:\fINE mNGMENT\trafficai.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def sql(query):
    try:
        cur.execute(query)
        rows = cur.fetchall()
        if rows:
            cols = list(rows[0].keys())
            col_widths = [max(len(str(c)), max(len(str(r[c])) for r in rows)) for c in cols]
            header = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(cols))
            divider = "-+-".join("-" * w for w in col_widths)
            print(header)
            print(divider)
            for r in rows:
                print(" | ".join(str(r[c]).ljust(col_widths[i]) for i, c in enumerate(cols)))
            print(f"\n({len(rows)} row(s))")
        else:
            conn.commit()
            print(f"OK — {cur.rowcount} row(s) affected.")
    except Exception as e:
        print(f"ERROR: {e}")

def tables():
    sql("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")

def schema(table_name):
    sql(f"PRAGMA table_info({table_name})")

print("=" * 55)
print("  SQLite CLI  —  trafficai.db")
print("=" * 55)
print("Commands:")
print("  sql('SELECT * FROM ...')   — run any SQL")
print("  tables()                   — list all tables")
print("  schema('table_name')       — show table columns")
print("  conn.commit()              — commit changes")
print("  exit()                     — quit")
print("=" * 55)
print()
print("Tables in database:")
tables()
