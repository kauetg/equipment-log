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

### Import do AppSheet

```bash
.venv/bin/python scripts/import_appsheet.py "Camera Log.xlsx"                                  # dry-run
.venv/bin/python scripts/import_appsheet.py "Camera Log.xlsx" --files ~/Downloads/camera_log --apply
```

Idempotente (por `legacy_id`): rodar de novo não duplica nem sobrescreve o que foi editado no app,
só cria o que falta e anexa arquivos ainda não anexados. `--files` é a pasta do app baixada do
Drive (com `Equipamentos_Files_/`, `Equipamentos_Images/`, `Transacoes_Files_/`,
`Transacoes_Images/`, `Log_Manutencao_Images/`). Normalização de lojas no topo do script.

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
- ✅ Fase 3 — manutenção e pedidos:
  - manutenção: data, título, tipo, quem fez (usuário ou texto livre), custo, condição resultante
    (4 botões) e fotos/PDFs; a condição do item = a do log mais recente; timeline global com
    filtros e "precisam de atenção";
  - pedidos (compra, venda, upgrade, brinde) com N itens — equipamento existente ou "novo item
    rápido" —, notas fiscais/recibos (fotos e PDFs), valor original opcional na moeda da loja;
    venda marca os itens como vendidos (e desfaz se a venda sair); custo total recalculado;
  - galeria de fotos por equipamento (promover a capa) e aba Arquivos juntando documentos,
    notas fiscais e fotos de manutenção;
  - home lista itens em atenção e compras sem nota fiscal.
- ✅ Fase 4 — import do AppSheet: 57 equipamentos, 34 pedidos (45 transações), 17 manutenções
  importados. Faltam os ~78 arquivos (fotos/recibos/manuais): rodar de novo com `--files`.
- Relatórios (fase 5) ainda pendentes.
- 🌱 Integrações (guardiola, media_logger): `app/services/integrations/`, desligadas por flag no `.env`.
