# Pataka (Equipment Log)

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

### Arquivos (fotos, recibos, manuais)

Só os arquivos saem do Mongo; os dados continuam lá. O app usa o primeiro backend configurado
**com credenciais** no `.env` (ver `.env.example`):

1. **Cloudinary** (recomendado — grátis, sem cartão): `CLOUDINARY_URL`, copiada de
   Dashboard → API Keys → *API environment variable*. Arquivos sobem como `authenticated`
   (link direto não abre sem assinatura), na pasta `CLOUDINARY_FOLDER` (padrão `equipment-log/`,
   uma subpasta por household) — não mistura com outros apps da mesma conta.
2. **S3-compatível** (Cloudflare R2, Backblaze B2, AWS S3): `S3_BUCKET`, `S3_ENDPOINT_URL`,
   `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. Bucket privado, link assinado de 1 h.
3. Nenhum → GridFS (dentro do Mongo).

Em todos os casos `/files/<id>` confere o household antes de entregar. Imagens são reduzidas
(1600px + thumb 400px) antes de subir. PDFs no Cloudinary grátis: se um PDF não abrir, ative
*Settings → Security → Allow delivery of PDF and ZIP files*.

Arquivos que já estejam no GridFS migram com:

```bash
.venv/bin/python scripts/migrate_files.py                           # dry-run
.venv/bin/python scripts/migrate_files.py --apply --delete-gridfs
```

### Import do AppSheet

```bash
.venv/bin/python scripts/import_appsheet.py "data/Camera Log.xlsx"                                  # dry-run
.venv/bin/python scripts/import_appsheet.py "data/Camera Log.xlsx" --files data --apply
```

Idempotente (por `legacy_id`): rodar de novo não duplica nem sobrescreve o que foi editado no app,
só cria o que falta e anexa arquivos ainda não anexados. `--files` é a pasta com os arquivos do app
baixados do Drive: as pastas `*_Files_` e `*_Images` podem estar lado a lado ou em qualquer
subpasta — o arquivo é procurado pelo nome. Normalização de lojas no topo do script.

## Marca

O app se chama **Pataka**. Logos em `app/static/img/` (os dois já trazem o nome):
`logo_horizontal.png` no navbar e no login, `logo.png` (empilhado) grande na home. Se faltar um,
usa o outro; sem nenhum, cai no `icon.svg` + "Pataka" em texto. Cores do tema (`theme.css`) tiradas
do logo: verde `#027f6c`, verde claro `#3a9b88`, roxo `#444076`.

Ícones do PWA/favicon (`icon-192/512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`,
`favicon.ico`) são gerados do `glyph.png` por `scripts/make_icons.py`. O glyph atual é
provisório: o `logo.png` sem o nome (palmeiras + telhado). Com o glifo definitivo:

```bash
python scripts/make_icons.py --glyph caminho/do/glifo.png
```

e suba o `CACHE_VERSION` em `static/service-worker.js` pro PWA instalado atualizar.

## Deploy no Raspberry Pi

1. No Pi: `git clone` (conta github-pessoal) em `~/pataka`, depois
   `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
2. Copie o `.env` (Mongo Atlas, `SECRET_KEY`, `CLOUDINARY_URL`) — ele não vai pro git. Se for
   ficar atrás de proxy HTTPS, acrescente `BEHIND_PROXY=1` e `COOKIE_SECURE=1`.
3. `deploy/pataka.service` → `/etc/systemd/system/` (ajuste `User` e caminhos), depois
   `sudo systemctl enable --now pataka`. Sobe o gunicorn em `127.0.0.1:5006`.
4. HTTPS na frente (nginx, Caddy, Cloudflare Tunnel, Tailscale Serve…). **O PWA só instala via
   HTTPS** (ou `localhost`); por `http://192.168.x.x` o celular só cria um atalho.
5. Atualizar: `git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart pataka`.

O Pi não precisa do `data/` — fotos e arquivos ficam no Cloudinary, dados no Atlas.

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
