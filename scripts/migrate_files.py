"""Move os arquivos que estão no GridFS (Mongo) pro backend configurado (Cloudinary ou S3) e
atualiza as refs nos documentos.

Uso:
    python scripts/migrate_files.py            # dry-run: só conta o que seria movido
    python scripts/migrate_files.py --apply    # copia e reescreve os ids nos documentos
    python scripts/migrate_files.py --apply --delete-gridfs   # …e apaga do Mongo depois

Precisa de CLOUDINARY_URL ou S3_* no .env. Idempotente: só mexe em refs cujo id ainda é do GridFS.
Ordem segura: copia → atualiza o documento → (opcional) apaga do GridFS. Se cair no meio, rodar
de novo continua de onde parou.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# coleção → campos com refs (lista ou ref única)
REF_FIELDS = {
    "equipment": {"photo": "one", "documents": "many", "gallery": "many"},
    "orders": {"receipts": "many"},
    "maintenance_logs": {"photos": "many"},
}


def main(argv=None, app=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete-gridfs", action="store_true", help="apaga do Mongo os arquivos migrados")
    args = parser.parse_args(argv)

    from app import create_app
    from app.services.storage import GridFSStorage, _backend

    app = app or create_app()
    target = app.config["STORAGE_BACKEND"]
    if target == "gridfs":
        print("Nenhum backend externo configurado (CLOUDINARY_URL ou S3_*) — nada a fazer.")
        sys.exit(1)

    with app.app_context():
        db = app.db
        gridfs_store = _backend(app, "gridfs")
        dest = _backend(app, target)
        print(f"Destino: {target}")
        stats = {"refs": 0, "arquivos": 0, "bytes": 0, "faltando": 0, "documentos": 0}
        moved_gridfs_ids = []

        def move(file_id, household_id):
            """Copia um arquivo do GridFS pro destino; devolve o id novo (ou None se não achou)."""
            try:
                stream, name, content_type = gridfs_store.open(file_id, household_id)
            except Exception:
                stats["faltando"] += 1
                print(f"  ! não achei no GridFS: {file_id}")
                return None
            data = stream.read()
            stats["arquivos"] += 1
            stats["bytes"] += len(data)
            moved_gridfs_ids.append(file_id)
            if not args.apply:
                return f"dry/{file_id}"
            return dest.save(data, name or "arquivo", content_type or "application/octet-stream", household_id)["id"]

        def migrate_ref(ref, household_id):
            if not ref or ref.get("external_url"):
                return ref, False
            changed = False
            new = dict(ref)
            for field in ("id", "thumb_id"):
                fid = ref.get(field)
                if fid and GridFSStorage.owns(fid):
                    key = move(fid, household_id)
                    if key:
                        new[field] = key
                        changed = True
            if changed:
                stats["refs"] += 1
            return new, changed

        for coll, fields in REF_FIELDS.items():
            for doc in db[coll].find({}, {**{f: 1 for f in fields}, "household_id": 1}):
                update = {}
                for field, shape in fields.items():
                    value = doc.get(field)
                    if shape == "one":
                        new, changed = migrate_ref(value, doc["household_id"])
                        if changed:
                            update[field] = new
                    else:
                        new_list, any_changed = [], False
                        for ref in value or []:
                            new, changed = migrate_ref(ref, doc["household_id"])
                            new_list.append(new)
                            any_changed |= changed
                        if any_changed:
                            update[field] = new_list
                if update:
                    stats["documentos"] += 1
                    if args.apply:
                        db[coll].update_one({"_id": doc["_id"]}, {"$set": update})

        if args.apply and args.delete_gridfs:
            for fid in moved_gridfs_ids:
                gridfs_store.delete(fid)

        mode = "APLICADO" if args.apply else "DRY-RUN (nada foi gravado)"
        print(f"\n{mode}")
        print(f"  documentos atualizados: {stats['documentos']}")
        print(f"  refs migradas: {stats['refs']}")
        print(f"  arquivos copiados: {stats['arquivos']} ({stats['bytes'] / 1024 / 1024:.1f} MB)")
        if stats["faltando"]:
            print(f"  não encontrados no GridFS: {stats['faltando']}")
        if args.apply and args.delete_gridfs:
            print(f"  apagados do GridFS: {len(moved_gridfs_ids)}")
        elif args.apply and moved_gridfs_ids:
            print("  (os originais continuam no GridFS — rode com --delete-gridfs pra liberar espaço)")


if __name__ == "__main__":
    main()
