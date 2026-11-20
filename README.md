# Equipment Log

Inventário de equipamentos (câmeras, foto sub, mergulho, eletrônicos) com log de manutenção e de
compras/vendas. Substitui o AppSheet "Camera Log". Mesma stack do guardiola: Flask + PyMongo +
Flask-Login + Bootstrap 5, PWA. Plano completo em [PLANO.md](PLANO.md).

## Rodar local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # preencher MONGO_URI (mesmo cluster do guardiola) e SECRET_KEY
.venv/bin/python scripts/seed_household.py   # household + usuários + 7 categorias + índices (uma vez)
.venv/bin/python run.py     # http://localhost:5004
```

`scripts/seed_household.py --categories` só completa as categorias que faltam.

## Estado

- Fase 1 (esqueleto) feita: login, inventário com cards por categoria, categorias (só leitura),
  conta/troca de senha, PWA, storage GridFS (`/files/<id>`), stubs de integração.
- Demais páginas são placeholders que listam o que vai existir ali e em que fase.
- 🌱 Integrações (guardiola, media_logger): `app/services/integrations/`, desligadas por flag no `.env`.
