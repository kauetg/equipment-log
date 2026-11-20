"""Importa o "Camera Log" do AppSheet (xlsx + pasta de arquivos) pro household existente.

Uso:
    python scripts/import_appsheet.py "Camera Log.xlsx"                     # dry-run (não grava nada)
    python scripts/import_appsheet.py "Camera Log.xlsx" --apply             # grava
    python scripts/import_appsheet.py "Camera Log.xlsx" --files ~/Downloads/camera_log --apply
    python scripts/import_appsheet.py ... --household "Kaue & Ba"          # se houver mais de um

Idempotente: equipamento/manutenção por `legacy_id`, pedido por `legacy_ids` (ids das transações).
Rodar de novo NÃO sobrescreve o que foi editado no app — só cria o que falta e anexa arquivos que
ainda não foram anexados (ex.: rodar de novo depois de baixar a pasta do Drive com --files).

A pasta de arquivos é a do app no Google Drive (baixar como zip e extrair). Os caminhos no xlsx
são relativos a ela: Equipamentos_Files_/…, Equipamentos_Images/…, Transacoes_Files_/…,
Transacoes_Images/…, Log_Manutencao_Images/…
"""
import argparse
import mimetypes
import sys
import unicodedata
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------------------
# Normalizações (editar aqui se algo vier estranho)
# ---------------------------------------------------------------------------------------

# contraparte crua do xlsx → (loja, plataforma, nota extra)
COUNTERPARTIES = {
    "Lazada": ("", "Lazada", ""),
    "Lazada TCA House": ("TCA House", "Lazada", ""),
    "Lazada - Camera Haus": ("Camera Haus", "Lazada", ""),
    "Lazada - Super Cool Digital": ("Super Cool Digital", "Lazada", ""),
    "Lazada - Asus Official": ("Asus Official Store", "Lazada", ""),
    "Lazada - Lenovo Tablet Store": ("Lenovo Tablet Store", "Lazada", ""),
    "Lazada - Garmin Official Store": ("Garmin Official Store", "Lazada", ""),
    "Lazada - HK Electronic Digital": ("HK Electronic Digital", "Lazada", ""),
    "Lazada- Conta Kaue": ("", "Lazada", "Conta do Kauê"),
    "Lazada - Conta Kaue": ("", "Lazada", "Conta do Kauê"),
    "Lazada Ph": ("", "Lazada", "Lazada PH"),
    "Lazada Malaysia": ("", "Lazada", "Lazada Malaysia"),
    "DJI Official Store - Lazada": ("DJI Official Store", "Lazada", ""),
    "Splash UW Photo": ("Splash UW Photo", "Loja física", ""),
    "Splash Uw Photo": ("Splash UW Photo", "Loja física", ""),
    "Spash Underwater Imaging": ("Splash UW Photo", "Loja física", ""),
    "Dive Sea - Adex": ("Dive Sea Adex", "Loja física", ""),
    "DiveInn - Madrid": ("DiveInn Madrid", "Loja física", ""),
    "DiveInn Madrid": ("DiveInn Madrid", "Loja física", ""),
    "El Corte Ingles": ("El Corte Inglés", "Loja física", ""),
    "Sony Store - V Holland SG": ("Sony Store Holland Village (SG)", "Loja física", ""),
    "Sony Store One Holland": ("Sony Store Holland Village (SG)", "Loja física", ""),
    "Harvey Norman": ("Harvey Norman", "Loja física", ""),
    "Amazon - Espanha": ("Amazon Espanha", "Amazon", ""),
    "Doha Airport Free Shop": ("Doha Airport Duty Free", "Loja física", ""),
}

TX_KINDS = {"compra": "purchase", "upgrade": "upgrade", "venda": "sale"}
EQUIPMENT_STATUS = {"ativo": "active", "quebrado": "broken", "descartado": "discarded", "vendido": "sold"}
CONDITION = {"perfeito": "perfect", "funcionando": "working", "sinais de uso": "wear", "quebrado": "broken"}

# Valores "de mentira" do AppSheet: transação de 0.01 = brinde; custo de manutenção 1.0 era
# preenchimento obrigatório, não dinheiro de verdade.
GIFT_MAX_VALUE = 0.01
MAINTENANCE_FAKE_COST = 1.0

SPEC_COLUMNS = ("memoria_ram", "storage", "depth_range")


def norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def guess_maintenance_kind(title):
    t = norm(title)
    if "limpeza" in t:
        return "cleaning"
    if "memoria" in t:
        return "upgrade"
    if "retirada" in t or "reparo" in t or "troca" in t:
        return "repair"
    if "inspec" in t:
        return "inspection"
    return "damage"


def to_date(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc)
    return None


def to_number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def text(value):
    return str(value).strip() if value not in (None, "") else ""


# ---------------------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------------------


def read_sheet(wb, name):
    ws = wb[name]
    it = ws.iter_rows(values_only=True)
    header = [h.strip() if isinstance(h, str) else h for h in next(it)]
    return [dict(zip(header, r)) for r in it if any(v not in (None, "") for v in r)]


class Report:
    def __init__(self):
        self.counts = defaultdict(int)
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(msg)

    def print(self, dry_run):
        print("\n" + ("DRY-RUN — nada foi gravado" if dry_run else "IMPORT APLICADO"))
        for k, v in self.counts.items():
            print(f"  {k}: {v}")
        if self.warnings:
            print(f"\n{len(self.warnings)} aviso(s):")
            for w in self.warnings:
                print("  -", w)


# ---------------------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------------------


class Importer:
    def __init__(self, db, household, files_dir, dry_run, report):
        self.db = db
        self.household = household
        self.hid = household["_id"]
        self.files_dir = Path(files_dir).expanduser() if files_dir else None
        self.dry_run = dry_run
        self.r = report
        self.now = datetime.now(timezone.utc)
        self.users = list(db.users.find({"household_id": self.hid}, {"name": 1}))
        self.categories = {c["name"]: c for c in db.categories.find({"household_id": self.hid})}
        self.equipment_by_legacy = {}  # legacy_id → _id
        self.touched = set()

    # ---- arquivos ----

    def file_ref(self, path_or_url, kind):
        """URL → ref externa; caminho → sobe o arquivo (se a pasta foi informada e ele existe)."""
        from app.services.storage import external_ref, save_bytes

        value = text(path_or_url)
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            ref = external_ref(value, kind=kind)
            ref["legacy_path"] = value
            return ref
        if not self.files_dir:
            self.r.counts["arquivos pendentes (sem --files)"] += 1
            return None
        path = self.files_dir / value
        if not path.is_file():
            self.r.warn(f"arquivo não encontrado: {value}")
            self.r.counts["arquivos não encontrados"] += 1
            return None
        self.r.counts["arquivos enviados"] += 1
        if self.dry_run:
            return {"id": None, "legacy_path": value, "kind": kind}
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        ref = save_bytes(path.read_bytes(), path.name, content_type, self.hid, kind=kind)
        ref["legacy_path"] = value
        return ref

    @staticmethod
    def has_file(refs, legacy_path):
        return any(r and r.get("legacy_path") == legacy_path for r in refs)

    # ---- pessoas ----

    def person(self, raw):
        name = text(raw)
        if not name:
            return None
        key = norm(name)
        for u in self.users:
            if norm(u["name"]).split(" ")[0] == key.split(" ")[0]:
                return {"user_id": u["_id"], "name": u["name"]}
        return {"user_id": None, "name": name}

    # ---- categorias ----

    def category(self, name, subcategory):
        name = text(name)
        cat = self.categories.get(name)
        if not cat:
            self.r.warn(f"categoria “{name}” não existe no household — criada vazia")
            cat = {"_id": None, "name": name, "subcategories": []}
            if not self.dry_run:
                last = self.db.categories.find_one({"household_id": self.hid}, sort=[("order", -1)])
                cat = {
                    "household_id": self.hid, "name": name, "icon": "bi-box", "color": "#898781",
                    "order": (last["order"] + 1) if last else 0, "subcategories": [], "spec_fields": [],
                    "has_exif": False, "created_at": self.now,
                }
                cat["_id"] = self.db.categories.insert_one(cat).inserted_id
            self.categories[name] = cat
            self.r.counts["categorias criadas"] += 1
        sub = text(subcategory)
        if sub and sub not in cat.get("subcategories", []):
            cat.setdefault("subcategories", []).append(sub)
            if not self.dry_run:
                self.db.categories.update_one({"_id": cat["_id"]}, {"$addToSet": {"subcategories": sub}})
        return cat

    # ---- equipamentos ----

    def import_equipment(self, rows):
        for row in rows:
            legacy_id = text(row.get("id_equipamento"))
            name = text(row.get("nome"))
            if not legacy_id or not name:
                self.r.warn(f"equipamento sem id/nome pulado: {row}")
                continue
            cat = self.category(row.get("categoria"), row.get("sub_categoria"))

            existing = self.db.equipment.find_one({"household_id": self.hid, "legacy_id": legacy_id})
            if existing:
                self.equipment_by_legacy[legacy_id] = existing["_id"]
                self.attach_equipment_files(existing, row)
                self.r.counts["equipamentos já existentes"] += 1
                continue

            specs = {}
            for col in SPEC_COLUMNS:
                v = to_number(row.get(col))
                if v is not None:
                    specs[col] = v
            status_raw = norm(row.get("status"))
            status = EQUIPMENT_STATUS.get(status_raw, "active")
            if status_raw and status_raw not in EQUIPMENT_STATUS:
                self.r.warn(f"{name}: status “{row.get('status')}” desconhecido → Ativo")

            doc = {
                "household_id": self.hid,
                "legacy_id": legacy_id,
                "name": name,
                "brand": text(row.get("marca")),
                "model": text(row.get("modelo")),
                "serial_number": text(row.get("numero_serie")),
                "category_id": cat["_id"],
                "subcategory": text(row.get("sub_categoria")),
                "status": status,
                "condition": None,
                "acquired_at": to_date(row.get("data_aquisicao")),
                "specs": specs,
                "specs_text": text(row.get("especificacoes_tecnicas")),
                "notes": text(row.get("observacoes")),
                "exif_keys": [],
                "photo": None,
                "documents": [],
                "gallery": [],
                "total_cost": 0,
                "created_by": "import_appsheet",
                "created_at": self.now,
                "updated_at": self.now,
            }
            self.fill_equipment_files(doc, row)
            self.r.counts["equipamentos criados"] += 1
            if self.dry_run:
                self.equipment_by_legacy[legacy_id] = f"dry:{legacy_id}"
                continue
            self.equipment_by_legacy[legacy_id] = self.db.equipment.insert_one(doc).inserted_id
            self.touched.add(self.equipment_by_legacy[legacy_id])

    def fill_equipment_files(self, doc, row):
        photo = self.file_ref(row.get("foto"), "photo")
        if photo:
            doc["photo"] = photo
        for col, kind in (("garantia", "warranty"), ("manual", "manual")):
            ref = self.file_ref(row.get(col), kind)
            if ref:
                doc["documents"].append(ref)

    def attach_equipment_files(self, existing, row):
        """Re-run: anexa só o que ainda não foi (por legacy_path). Não troca foto escolhida no app."""
        update = {}
        foto = text(row.get("foto"))
        if foto and not existing.get("photo"):
            ref = self.file_ref(foto, "photo")
            if ref:
                update["photo"] = ref
        documents = list(existing.get("documents", []))
        for col, kind in (("garantia", "warranty"), ("manual", "manual")):
            path = text(row.get(col))
            if path and not self.has_file(documents, path):
                ref = self.file_ref(path, kind)
                if ref:
                    documents.append(ref)
        if len(documents) != len(existing.get("documents", [])):
            update["documents"] = documents
        if update:
            self.r.counts["equipamentos com arquivos anexados"] += 1
            if not self.dry_run:
                self.db.equipment.update_one({"_id": existing["_id"]}, {"$set": update})

    # ---- pedidos ----

    def group_transactions(self, rows):
        """Transações → pedidos. Mesmo recibo = mesmo pedido; sem recibo, mesma data + mesma
        loja/nota (normalizadas) = mesmo pedido. Brinde (0.01) sem recibo fica sozinho."""
        groups = OrderedDict()
        for row in rows:
            kind = TX_KINDS.get(norm(row.get("tipo")))
            if not kind:
                self.r.warn(f"transação {row.get('id_transacao')}: tipo “{row.get('tipo')}” desconhecido — pulada")
                continue
            raw_cp = text(row.get("contraparte"))
            if raw_cp and raw_cp not in COUNTERPARTIES:
                self.r.warn(f"contraparte sem mapeamento (mantida como veio): “{raw_cp}”")
            cp, platform, cp_note = COUNTERPARTIES.get(raw_cp, (raw_cp, "", ""))
            value = to_number(row.get("valor")) or 0
            date = to_date(row.get("data"))
            receipt = text(row.get("receipt_file"))

            if receipt:
                key = ("receipt", receipt)
            elif (cp or cp_note) and value > GIFT_MAX_VALUE:
                key = ("shop", kind, date, cp, cp_note)
            else:
                key = ("single", text(row.get("id_transacao")))
            g = groups.setdefault(
                key,
                {"kind": kind, "date": date, "counterparty": cp, "platform": platform, "notes": [],
                 "rows": [], "receipt": receipt},
            )
            for note in (cp_note, text(row.get("observacoes"))):
                if note and note not in g["notes"]:
                    g["notes"].append(note)
            g["rows"].append(row)
        return list(groups.values())

    def import_orders(self, rows):
        for g in self.group_transactions(rows):
            legacy_ids = [text(r.get("id_transacao")) for r in g["rows"]]
            existing = self.db.orders.find_one({"household_id": self.hid, "legacy_ids": {"$in": legacy_ids}})

            items = []
            for r in g["rows"]:
                eid = self.equipment_by_legacy.get(text(r.get("ref_equipamento")))
                if not eid:
                    self.r.warn(f"transação {r.get('id_transacao')}: equipamento {r.get('ref_equipamento')} não encontrado")
                    continue
                value = to_number(r.get("valor")) or 0
                amount = 0.0 if value <= GIFT_MAX_VALUE else round(value, 2)
                items.append({"equipment_id": eid, "amount": amount})
            if not items:
                continue

            kind = g["kind"]
            if kind == "purchase" and all(i["amount"] == 0 for i in items):
                kind = "gift"

            if existing:
                self.r.counts["pedidos já existentes"] += 1
                if g["receipt"] and not self.has_file(existing.get("receipts", []), g["receipt"]):
                    ref = self.file_ref(g["receipt"], "receipt")
                    if ref:
                        self.r.counts["pedidos com recibo anexado"] += 1
                        if not self.dry_run:
                            self.db.orders.update_one({"_id": existing["_id"]}, {"$push": {"receipts": ref}})
                continue

            receipt = self.file_ref(g["receipt"], "receipt") if g["receipt"] else None
            dates = [d for d in (to_date(r.get("data")) for r in g["rows"]) if d]
            doc = {
                "household_id": self.hid,
                "legacy_ids": legacy_ids,
                "kind": kind,
                "date": min(dates) if dates else self.now,
                "counterparty": g["counterparty"],
                "platform": g["platform"],
                "currency": "USD",
                "items": items,
                "total": round(sum(i["amount"] for i in items), 2),
                "original_currency": None,
                "original_total": None,
                "receipts": [receipt] if receipt else [],
                "notes": " · ".join(g["notes"]),
                "guardiola_tx_ids": [],
                "created_by": "import_appsheet",
                "created_at": self.now,
            }
            self.r.counts["pedidos criados"] += 1
            if len(items) > 1:
                self.r.counts["pedidos com vários itens"] += 1
            if kind == "gift":
                self.r.counts["pedidos de brinde"] += 1
            if not self.dry_run:
                self.db.orders.insert_one(doc)
                self.touched.update(i["equipment_id"] for i in items)

    # ---- manutenção ----

    def import_maintenance(self, rows):
        for row in rows:
            legacy_id = text(row.get("id_manutencao"))
            eid = self.equipment_by_legacy.get(text(row.get("ref_equipamento")))
            if not eid:
                self.r.warn(f"manutenção {legacy_id}: equipamento {row.get('ref_equipamento')} não encontrado")
                continue
            photo_path = text(row.get("photo"))
            existing = self.db.maintenance_logs.find_one({"household_id": self.hid, "legacy_id": legacy_id})
            if existing:
                self.r.counts["manutenções já existentes"] += 1
                if photo_path and not self.has_file(existing.get("photos", []), photo_path):
                    ref = self.file_ref(photo_path, "maintenance")
                    if ref and not self.dry_run:
                        self.db.maintenance_logs.update_one({"_id": existing["_id"]}, {"$push": {"photos": ref}})
                continue

            title = text(row.get("tipo")) or "Manutenção"
            cost = to_number(row.get("custo")) or 0
            if cost == MAINTENANCE_FAKE_COST:
                cost = 0
                self.r.counts["custos 1.0 zerados"] += 1
            condition = CONDITION.get(norm(row.get("status")))
            if not condition:
                self.r.warn(f"manutenção {legacy_id}: status “{row.get('status')}” desconhecido")
            photo = self.file_ref(photo_path, "maintenance") if photo_path else None
            doc = {
                "household_id": self.hid,
                "legacy_id": legacy_id,
                "equipment_id": eid,
                "date": to_date(row.get("data")) or self.now,
                "title": title,
                "kind": guess_maintenance_kind(title),
                "description": text(row.get("descricao")),
                "cost": round(cost, 2),
                "done_by": self.person(row.get("quem_fez")),
                "resulting_condition": condition,
                "photos": [photo] if photo else [],
                "created_by": "import_appsheet",
                "created_at": self.now,
            }
            self.r.counts["manutenções criadas"] += 1
            if not self.dry_run:
                self.db.maintenance_logs.insert_one(doc)
                self.touched.add(eid)

    # ---- pós ----

    def recompute(self):
        from app.services.equipment_costs import recompute_total_cost
        from app.services.maintenance import recompute_condition

        if self.dry_run:
            return
        for eid in self.touched:
            recompute_total_cost(self.db, eid)
            recompute_condition(self.db, eid)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx")
    parser.add_argument("--files", help="pasta do app baixada do Drive (com Equipamentos_Files_/ etc.)")
    parser.add_argument("--household", help="nome do household (se houver mais de um)")
    parser.add_argument("--apply", action="store_true", help="grava de verdade (sem isso é dry-run)")
    args = parser.parse_args()

    import openpyxl

    from app import create_app
    from app.extensions import ensure_indexes

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    app = create_app()
    with app.app_context():
        db = app.db
        query = {"name": args.household} if args.household else {}
        households = list(db.households.find(query))
        if len(households) != 1:
            names = [h["name"] for h in db.households.find({}, {"name": 1})]
            print(f"Preciso de exatamente 1 household (achei {len(households)}). Existentes: {names}")
            print("Use --household \"nome\".")
            sys.exit(1)
        household = households[0]
        print(f"Household: {household['name']}  (db: {app.config['MONGO_DB_NAME']})")
        print(f"Arquivos: {args.files or '— (sem --files: só dados; fotos externas por URL entram)'}")

        if not db.categories.count_documents({"household_id": household["_id"]}):
            print("Household sem categorias — rode antes: python scripts/seed_household.py --categories")
            sys.exit(1)

        report = Report()
        imp = Importer(db, household, args.files, dry_run=not args.apply, report=report)
        if args.apply:
            ensure_indexes(db)
        imp.import_equipment(read_sheet(wb, "Equipamentos"))
        imp.import_orders(read_sheet(wb, "Transacoes"))
        imp.import_maintenance(read_sheet(wb, "Log_Manutencao"))
        imp.recompute()
        report.print(dry_run=not args.apply)
        if not args.apply:
            print("\nPra gravar: rode de novo com --apply")


if __name__ == "__main__":
    main()
