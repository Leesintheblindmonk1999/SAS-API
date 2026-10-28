"""
check_keys.py — Identifica qué usuario/plan corresponde a cada api_key_hash
======================================================================
Uso (en la shell de Render):
    python scripts/check_keys.py

Muestra todos los usuarios con su plan, status, y api_key_hash completo
para poder cruzar con los hashes acortados del funnel report.
"""

import sqlite3
import sys

DB = "/app/data/auth.db"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("USUARIOS EN AUTH DB")
    print("=" * 70)

    rows = conn.execute(
        "SELECT id, email_hash, name, plan, status, api_key_hash, "
        "created_at, last_key_issued_at FROM users ORDER BY id"
    ).fetchall()

    if not rows:
        print("(no users)")
        return

    for r in rows:
        d = dict(r)
        key_hash = d.get("api_key_hash") or ""
        short = key_hash[:12] if key_hash else "(sin key)"
        print(f"\nid={d['id']}  plan={d['plan']}  status={d['status']}  name={d['name']}")
        print(f"  email_hash     : {d['email_hash']}")
        print(f"  api_key_hash   : {key_hash}")
        print(f"  short (12)     : {short}")
        print(f"  created_at     : {d['created_at']}")
        print(f"  last_key_issued: {d['last_key_issued_at']}")

    print("\n" + "=" * 70)
    print("CRUCE CON FUNNEL REPORT")
    print("=" * 70)
    print("Funnel report mostró:")
    print("  8007eea333d0  pro     (18 requests, IPs US)")
    print("  a8b6b1740d86  legacy  (5 requests)")
    print("  55aeffaf4e32  (interaction events, user_id=3)")
    print()
    print("Buscá cuál de los api_key_hash de arriba empieza con esos prefijos.")
    print("Si NINGUNO coincide con 8007eea333d0 -> esa key NO está en la DB")
    print("y fue usada con una key que ya no existe (rotada/borrada) o es")
    print("una key hardcodeada en el código (legacy_bootstrap_api_key).")

    conn.close()


if __name__ == "__main__":
    main()