"""Cria o household, os usuários e as categorias iniciais (rodar uma vez via terminal).

Uso:
    python scripts/seed_household.py                 # household + usuários + categorias + índices
    python scripts/seed_household.py --categories    # só (re)cria categorias que faltam no household existente
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash

from app import create_app
from app.config import DEFAULT_CATEGORIES
from app.extensions import ensure_indexes


def seed_categories(db, household_id):
    """Insere as DEFAULT_CATEGORIES que ainda não existem (por nome). Idempotente."""
    existing = {c["name"] for c in db.categories.find({"household_id": household_id}, {"name": 1})}
    created = 0
    for order, cat in enumerate(DEFAULT_CATEGORIES):
        if cat["name"] in existing:
            continue
        db.categories.insert_one(
            {
                "household_id": household_id,
                "name": cat["name"],
                "icon": cat["icon"],
                "color": cat["color"],
                "order": order,
                "subcategories": list(cat["subcategories"]),
                "spec_fields": [dict(f) for f in cat["spec_fields"]],
                "has_exif": cat.get("has_exif", False),
                "created_at": datetime.now(timezone.utc),
            }
        )
        created += 1
    return created


def prompt_user(label):
    print(f"\n-- {label} --")
    name = input("Nome: ").strip()
    email = input("Email: ").strip().lower()
    password = input("Senha (vai aparecer na tela, é só rodar num lugar privado): ")
    return {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": "admin",
    }


def main():
    app = create_app()
    with app.app_context():
        db = app.db
        ensure_indexes(db)

        if "--categories" in sys.argv:
            household = db.households.find_one({})
            if not household:
                print("Nenhum household ainda — rode sem --categories primeiro.")
                return
            n = seed_categories(db, household["_id"])
            print(f"{n} categoria(s) criada(s).")
            return

        if db.households.find_one({}):
            print("Já existe um household criado. Abortando pra não duplicar.")
            print("(pra só completar as categorias: --categories)")
            return

        household_name = input("Nome do household (ex: Kaue & Ba): ").strip()
        household_id = db.households.insert_one(
            {
                "name": household_name,
                "member_ids": [],
                # 🌱 PLANO.md §8.1 — preencher quando ligar a integração com o guardiola
                "guardiola_household_id": None,
                "created_at": datetime.now(timezone.utc),
            }
        ).inserted_id

        member_ids = []
        num_users = int(input("Quantos usuários criar? ") or "2")
        for i in range(num_users):
            user = prompt_user(f"Usuário {i + 1}")
            user["household_id"] = household_id
            member_ids.append(db.users.insert_one(user).inserted_id)

        db.households.update_one({"_id": household_id}, {"$set": {"member_ids": member_ids}})
        n = seed_categories(db, household_id)
        print(f"\nHousehold '{household_name}' criado com {len(member_ids)} usuário(s) e {n} categorias.")


if __name__ == "__main__":
    main()
