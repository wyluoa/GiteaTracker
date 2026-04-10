"""
Seed script — populate initial nodes, super user, and legacy account.

Usage:
    python seed.py
"""
import sys
from pathlib import Path

# Ensure we can import from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from app.models import user as user_model
from app.models import node as node_model
from app.models import setting as setting_model

NODES = [
    ("n_a10",  "A10",   10),
    ("n_a12",  "A12",   20),
    ("n_a14",  "A14",   30),
    ("n_n2",   "N2",    40),
    ("n_a16",  "A16",   50),
    ("n_n3",   "N3",    60),
    ("n_n4n5", "N4/N5", 70),
    ("n_n6n7", "N6/N7", 80),
    ("n_000",  "000",   90),
    ("n_mtm",  "MtM",  100),
]


def main():
    app = create_app()
    with app.app_context():
        # --- Nodes ---
        created_nodes = 0
        for code, display_name, sort_order in NODES:
            existing = node_model.get_by_code(code)
            if existing:
                print(f"  Node {display_name} already exists, skipping.")
                continue
            node_model.create_node(code, display_name, sort_order)
            created_nodes += 1
        print(f"Nodes: {created_nodes} created, {len(NODES) - created_nodes} already existed.")

        # --- Super user ---
        existing_wy = user_model.get_by_username("wy")
        if existing_wy:
            print("Super user 'wy' already exists, skipping.")
        else:
            user_model.create_user(
                username="wy",
                email="wy@internal.local",
                display_name="WY",
                password="changeme",
                status="active",
                is_super_user=True,
            )
            print("Super user 'wy' created (password: changeme).")

        # --- Legacy user (for historical imports) ---
        existing_legacy = user_model.get_by_username("legacy")
        if existing_legacy:
            print("Legacy user already exists, skipping.")
        else:
            user_model.create_user_raw(
                username="legacy",
                email="legacy@internal.local",
                display_name="Legacy",
                password_hash="!disabled",  # cannot login
                status="disabled",
                is_super_user=False,
            )
            print("Legacy user created (disabled, for historical data).")

        print("\nSeed complete.")


if __name__ == "__main__":
    main()
