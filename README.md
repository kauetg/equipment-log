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

- ✅ Fase 1 — esqueleto: login, conta, PWA, storage GridFS (`/files/<id>`), stubs de integração.
- ✅ Fase 2 — inventário e equipamentos:
  - home com cards por categoria; página da categoria com chips de subcategoria e grid
    (vendidos/descartados escondidos por padrão);
  - busca por nome/marca/modelo/nº de série + filtros de categoria e status;
  - cadastro/edição com specs que mudam conforme a categoria, foto de capa (redimensionada
    pra 1600px + thumb 400px) ou link externo, garantia/manual/outros documentos, chaves EXIF;
  - "registrar compra agora" cria um pedido de 1 item e atualiza o custo total;
  - detalhe com abas (Visão geral, Manutenção, Compras/Vendas, Arquivos) e exclusão;
  - Configurações > Categorias: criar, editar, reordenar, excluir (só se vazia).
- Fase 3 (manutenção, pedidos com N itens, galeria) e o resto ainda são placeholders.
- 🌱 Integrações (guardiola, media_logger): `app/services/integrations/`, desligadas por flag no `.env`.
