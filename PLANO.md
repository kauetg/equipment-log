# Equipment Log — plano

Substituto do AppSheet "Camera Log". Mesma stack e estrutura do **guardiola**: Flask + PyMongo (sem ODM) +
Flask-Login + Bootstrap 5 + Jinja, blueprints por domínio, `app/services/` pra queries, PWA, Procfile/gunicorn.

---

## 0. O que o xlsx mostrou (`Camera Log.xlsx`)

| Aba | Linhas | Colunas |
|---|---|---|
| Equipamentos | 58 | id_equipamento, nome, categoria, sub_categoria, marca, modelo, numero_serie, foto, data_aquisicao, status, observacoes, garantia, manual, especificacoes_tecnicas, memoria_ram, storage, depth_range |
| Transacoes | 45 | id_transacao, ref_equipamento, tipo, data, valor, contraparte, observacoes, receipt_file |
| Log_Manutencao | 17 | id_manutencao, ref_equipamento, tipo, data, descricao, custo, quem_fez, status, photo |

Achados que mudam o desenho:

- **Duas camadas de categoria**: categoria (Acessório de Foto, Foto Sub, Camera, Outros Eletrônicos, Computador,
  Mergulho, Celular) → sub_categoria (Cartão SD, Bateria, Lente, Caixa Estanque, Regulador, Drone…).
- **Specs dependem da categoria**: `memoria_ram` / `storage` (computador, cartão), `depth_range` (estanque, computador
  de mergulho), `especificacoes_tecnicas` em texto livre. → `specs` como dict flexível; a categoria define quais campos
  aparecem no form. É o lugar onde o Mongo brilha.
- **3 tipos de arquivo no equipamento**: foto, garantia, manual (PDF). A foto às vezes é URL externa (gstatic).
- **Um recibo cobre vários itens**: o mesmo `receipt_file` aparece em 8 transações (pedido da Splash UW Photo, por
  exemplo). → "Compra" vira **pedido com N itens**, não 1 transação por item.
- **Sem coluna de moeda** em `valor`: **tudo já está em USD** (confirmado), mesmo as compras em Lazada PH/MY,
  Sony Store SG, El Corte Inglés, Amazon ES.
- Brindes registrados como `0.01`. Tipo `Upgrade` aparece 1 vez; **nenhuma venda ainda**.
- **No log de manutenção, `tipo` é na verdade um título livre** ("Alagamento da bateria", "Risco detectado") e
  **`status` é a condição resultante** do equipamento (Perfeito / Funcionando / Sinais de Uso / Quebrado).
- **`quem_fez` = Kauê ou Bárbara** → é um household de 2 pessoas, igual ao guardiola.
- Volume pequeno: ~58 itens, ~90 arquivos ao todo.
- Sujeira pra limpar no import: 1 linha sem nome com categoria `16.0`, "Kaue/Kauê", "Barbara/Bárbara",
  "Splash Uw Photo/Splash UW Photo/Spash…", "Adicionar Memória/Memoria", datas em serial do Excel (45000 → 2023-03-15).

---

## 1. Modelo de dados

Tudo com `household_id`; usuários Kauê e Bárbara (copiar `users`/`households` do guardiola).

### `categories`
```python
{
  "name": "Foto Sub", "icon": "bi-water", "color": "#1e88e5", "order": 2,
  "subcategories": ["Caixa Estanque", "Flash", "Filtro", "Acessórios"],
  "spec_fields": [                      # o que o form de equipamento mostra pra essa categoria
    {"key": "depth_range", "label": "Profundidade máx.", "unit": "m", "type": "number"}
  ]
}
```

### `equipment`
| campo | tipo | nota |
|---|---|---|
| legacy_id | str | `EQ001` / `9cb1eb29` do AppSheet (pra importar os refs) |
| name, brand, model, serial_number | str | |
| category_id, subcategory | ObjectId, str | |
| status | enum | `active` (Ativo), `broken` (Quebrado), `discarded` (Descartado), `sold`, `loaned` |
| condition | enum | `perfect`, `working`, `wear`, `broken` — **cache da última manutenção** |
| acquired_at | date | |
| specs | dict | `{"memoria_ram": 32, "storage": 512, "depth_range": 100}` + `specs_text` livre |
| photo | file ref | capa (aceita URL externa) |
| documents | [file ref + `kind`] | `warranty`, `manual`, `other` |
| gallery | [file ref] | fotos extras |
| notes | str | |
| total_cost | float | cache: compras + manutenções |
| exif_keys | [str] | 🌱 *semente media_logger* — ex. `["SONY - ILCE-7M4"]`; só faz sentido p/ Camera / Drone / Action Cam / Celular. Lista porque o mesmo corpo pode reportar EXIF diferente por firmware/app |

### `orders` (compras, vendas, upgrades)
```python
{
  "kind": "purchase",              # purchase | sale | upgrade | gift
  "date": ..., "counterparty": "Splash UW Photo", "platform": "Lazada",
  "currency": "USD", "total": 220.0,   # USD é o padrão; import grava tudo como USD
  # opcional: "original_currency": "PHP", "original_total": 12345.0 — só se quiser anotar o valor pago na moeda local
  "items": [{"equipment_id": ..., "amount": 800.0}, {"equipment_id": ..., "amount": 0}],  # 0 = brinde
  "receipts": [file ref], "notes": "11.11, veio com a lente e um cartão",
  "guardiola_tx_ids": []            # 🌱 semente guardiola — lista (1 pedido pode ter sido pago em 2 cartões/parcelas)
}
```
No import, transações com o mesmo `receipt_file` (ou mesma data + contraparte) viram um só pedido.
Registrar uma `sale` marca os itens como `sold`.

### `maintenance_logs`
| campo | tipo | nota |
|---|---|---|
| equipment_id | ObjectId | |
| date | date | |
| title | str | o "tipo" livre de hoje |
| kind | enum | `damage`, `repair`, `cleaning`, `upgrade`, `inspection` — novo, pra filtrar/agrupar |
| description | str | |
| cost | float | USD |
| done_by | user_id ou str | select com Kauê / Bárbara / "Assistência: ___" |
| resulting_condition | enum | Perfeito / Funcionando / Sinais de Uso / Quebrado → atualiza `equipment.condition` |
| photos | [file ref] | |

### file ref (embutido)
```python
{"id": ..., "name": "manual.pdf", "content_type": "application/pdf", "size": 123456,
 "thumb_id": ..., "external_url": None, "kind": "manual", "uploaded_at": ...}
```

---

## 2. Páginas

| Página | Rota (placeholder) | Conteúdo |
|---|---|---|
| Login | `/auth/login` | copiar do guardiola |
| **Inventário (home)** | `/` | cards das 7 categorias (qtd, valor investido) · alertas: itens com condição *Quebrado* / *Sinais de Uso*, garantias acabando |
| Categoria | `/categories/<id>` | chips de subcategoria pra filtrar + grid (foto, nome, badge status/condição) |
| Busca / lista | `/equipment?q=&status=&cat=` | tabela; busca por nome, marca, nº série |
| **Detalhe** | `/equipment/<id>` | header (foto, marca/modelo, série, badges) · abas: **Visão geral** (specs, notas, garantia/manual) · **Manutenção** (timeline) · **Compras/Vendas** · **Arquivos** |
| Form equipamento | `/equipment/new`, `/<id>/edit` | §3 |
| Form manutenção | `/equipment/<id>/maintenance/new` | modal ou página |
| Form pedido | `/orders/new?equipment=<id>` | §3 |
| Pedidos | `/orders` | lista de compras/vendas, filtro por loja/ano |
| Manutenção (global) | `/maintenance` | timeline de tudo, filtro por pessoa/tipo |
| Relatórios | `/reports` | investido por categoria/ano, custo de manutenção (*fase 2*) |
| Configurações | `/settings/categories`, `/settings/account` | categorias + subcategorias + spec_fields, senha |
| Arquivo | `/files/<id>`, `/files/<id>/thumb` | serve o binário (ver §4) |

Navbar: Inventário · Pedidos · Manutenção · Relatórios · ⚙️

---

## 3. Forms

**Equipamento**: nome*, categoria* → subcategoria (select dependente), marca (datalist com as existentes), modelo,
nº série, data de aquisição, status, **bloco de specs que muda conforme a categoria** (JS simples lendo `spec_fields`),
notas, foto de capa, garantia, manual.
Checkbox *"registrar compra agora"* → expande data/valor (USD)/loja e cria o pedido junto.

**Pedido (compra/venda)**: tipo* (compra / venda / upgrade / brinde), data*, loja/contraparte (datalist), plataforma,
total em USD* (moeda/valor original opcional, recolhido), **lista de itens** (equipamento existente *ou* "novo item rápido" só com nome+categoria) com valor de
cada, recibos (múltiplos), notas.

**Manutenção**: data*, título*, tipo (enum), descrição, custo (USD), quem fez (Kauê / Bárbara / outro), condição
resultante* (4 botões grandes com cor), fotos.

**Categoria**: nome, ícone, cor, ordem, subcategorias (lista editável), campos de spec (key, label, unidade, tipo).

Upload: `<input type="file" multiple accept="image/*,application/pdf" capture="environment">` → abre a câmera direto
no celular.

---

## 4. Storage de arquivos

Interface única em `app/services/storage.py` → `save(file) -> ref`, `open(ref)`, `delete(ref)`. Nenhuma rota sabe qual
backend está por baixo. No upload, Pillow redimensiona imagens pra ~1600px e gera thumb de 400px; PDFs passam direto.

Com ~90 arquivos hoje, o volume é baixo:

| Fase | Backend | Por quê |
|---|---|---|
| ~~MVP~~ | **GridFS** (no próprio Mongo) — continua como fallback sem credenciais | zero conta nova, zero credencial, backup junto com o banco. ~90 arquivos redimensionados ≈ 30–60 MB, cabe no Atlas free (512 MB) com folga |
| ✅ **Atual** (2026-11-21) | **Cloudinary** (grátis, sem cartão) ou **S3-compatível** (R2/B2/AWS) | Cloudinary: `CLOUDINARY_URL`, arquivos `authenticated`. S3: `boto3`, bucket privado. Escolha automática pelo `.env`; `scripts/migrate_files.py` move o que estiver no GridFS |
| — | Google Drive API | **não**: service account, quota, sem URL boa pra `<img>` |
| — | Disco local | some a cada deploy |

As rotas `/files/<id>` servem o arquivo com `Cache-Control` longo (o id nunca muda) e `@login_required`.

---

## 5. Import do AppSheet

`scripts/import_appsheet.py "Camera Log.xlsx" <pasta-dos-arquivos>`

1. Baixar do Drive a pasta do app (tem `Equipamentos_Files_/`, `Equipamentos_Images/`, `Transacoes_Files_/`,
   `Transacoes_Images/`, `Log_Manutencao_Images/`). Download manual em zip, sem API.
2. Script: categorias/subcategorias a partir dos valores distintos → equipamentos (`legacy_id`, data serial → date,
   specs) → agrupa transações em pedidos → logs → sobe cada arquivo referenciado pro storage e grava a ref.
3. Normalizações: nomes de pessoa → user, contrapartes duplicadas → mapa manual no topo do script, `0.01` → brinde,
   linha `16.0` sem nome → pula com aviso.
4. Idempotente por `legacy_id` (pode rodar de novo sem duplicar). Usa `openpyxl`.

---

## 6. Estrutura de pastas

```
app/
  __init__.py  config.py  extensions.py
  models/user.py
  routes/    auth.py  inventory.py  equipment.py  orders.py  maintenance.py  reports.py  settings.py  files.py
  services/  storage.py  images.py  inventory_queries.py
             integrations/  __init__.py  guardiola.py  media_logger.py   # 🌱 stubs
  templates/
    base.html  _macros.html   # badge status/condição, card equipamento, lista de arquivos, campo de upload
    inventory/index.html  category.html
    equipment/index.html  detail.html  form.html  _specs_fields.html
    orders/index.html  form.html
    maintenance/index.html  form.html
    reports/index.html
    settings/categories.html  account.html
    auth/login.html
  static/ css/theme.css  js/equipment_form.js  manifest.json  service-worker.js  img/
scripts/import_appsheet.py  seed_household.py
run.py  Procfile  requirements.txt   # + Pillow, openpyxl
```

---

## 7. Fases

1. ✅ **Esqueleto** (feito 2026-11-20): copiar do guardiola (auth, household, base.html, theme, PWA), seed das 7 categorias.
2. ✅ **Inventário + CRUD de equipamento** (feito 2026-11-21) com specs por categoria e foto (GridFS).
3. ✅ **Detalhe com abas** (feito 2026-11-21) + manutenção + pedidos com N itens + anexos múltiplos.
4. ✅ **Import do AppSheet** (dados importados 2026-11-21; arquivos pendentes) (xlsx + pasta de arquivos).
5. Extras: relatórios, garantias vencendo, QR code por item (etiqueta no case → abre o detalhe), R2 se o GridFS apertar.
6. **Integração guardiola** (§8.1) — a mais importante.
7. **Integração media_logger** (§8.2).

---

## 8. 🌱 Integrações futuras — terreno preparado agora, implementação depois

O que entra **já na fase 1** (custa quase nada e evita migração depois):
- `equipment.exif_keys = []` e `orders.guardiola_tx_ids = []` existem no schema desde o início (vazios).
- **Mesmo cluster Atlas do guardiola, database separado** (`equipment_log`). Fecha a pergunta em aberto: com o mesmo
  `MongoClient` dá pra ler o banco do guardiola direto, sem API.
- `config.py` já com `GUARDIOLA_DB_NAME` (default `finance_app`) e `INTEGRATIONS = {"guardiola": False, "media_logger": False}`.
- `app/services/integrations/__init__.py` vazio + stubs `guardiola.py` e `media_logger.py` com as assinaturas abaixo
  levantando `NotImplementedError` — o template já pode mostrar o bloco "Pagamento no Guardiola" escondido por flag.
- Mesmos valores em USD dos dois lados (`orders.total` ↔ `transactions.amount_usd`), o que torna o match trivial.

### 8.1 Guardiola (transações) ⭐

Princípio: **o guardiola é a fonte da verdade do dinheiro**; o Equipment Log só *aponta* pra transação. A despesa da
câmera quase sempre já existe lá (veio do import do banco/cartão), então o fluxo principal é **vincular**, não criar.

Formato de uma despesa no guardiola (lido de `routes/transactions.py`):
`household_id, wallet_id, type="expense", amount_original, currency_original, amount_usd, category, description, date,
project_id, is_refundable`.

```python
# app/services/integrations/guardiola.py
def suggest_matches(order) -> list[tx]          # expense com |amount_usd - total| < 2% e data ±5 dias
def link(order_id, tx_id)                       # grava em orders.guardiola_tx_ids
def unlink(order_id, tx_id)
def create_expense(order, wallet_id, category)  # fase posterior: cria a despesa no guardiola a partir do pedido
def get_linked(order) -> list[tx]               # mostra carteira, valor original, categoria no detalhe do pedido
```

UI (placeholder):
- Detalhe do pedido → card **"Pagamento"**: transações vinculadas (carteira, data, valor original) ou botão
  *"Vincular transação do Guardiola"* → modal com as sugestões de `suggest_matches` + busca.
- Lista de pedidos → ícone 🔗 / ⚠️ "sem pagamento vinculado" → vira uma *fila de conciliação*.
- Venda (`kind=sale`) → vincula a uma `income` do guardiola, mesma lógica.
- Do lado do guardiola (bem depois): na transação, badge "📷 Sony A7 IV" linkando de volta. Pra isso o guardiola só
  precisaria de um campo opcional `equipment_order_id` — **não mexer no guardiola agora**.

Decisões pra quando chegar a hora:
- Escrita cruzada: o Equipment Log escreve no banco do guardiola (`create_expense`) ou só lê? Começar **só lendo**.
- Household: mapear `households` dos dois apps (mesmo casal) via `guardiola_household_id` no household do Equipment Log.
- Login unificado (mesma `users`)? Tentador, mas fica pra depois.

### 8.2 media_logger (câmeras)

Hoje o media_logger é um app local que lê o EXIF (`Image Make` + `Image Model`) e procura em `cameras.json`:
`{"SONY - ILCE-7M4": {"name": "Sony a7 IV", "image": "..."}}`.

Plano:
- Equipment Log vira a **fonte dos perfis de câmera**: endpoint `GET /api/cameras.json` (token simples no header)
  devolvendo **exatamente o mesmo formato** a partir de `equipment.exif_keys` (nome + URL da foto de capa).
- media_logger: ao abrir, tenta baixar esse JSON e cai no `cameras.json` local se estiver offline — mudança mínima lá.
- Form do equipamento (categorias com câmera): campo "Chaves EXIF" + botão *"detectar de uma foto"* (sobe um JPG,
  lê o EXIF com `exifread` igual o media_logger já faz — mesma lógica de `detect_exif`).
- Depois, opcional: media_logger manda de volta estatísticas (nº de fotos/vídeos por câmera por dia) →
  aba "Uso" no detalhe do equipamento. Útil pra saber quanto cada câmera realmente é usada.
- Seed no import: casar os 5 itens do `cameras.json` atual com os equipamentos por nome.

## Em aberto
- Nada bloqueando a fase 1.
