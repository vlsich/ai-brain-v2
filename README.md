# AI Brain V2

Sistema multi-agente con memoria persistente locale.

## Stack

- Python 3.11+
- FastAPI
- OpenAI SDK
- SQLite locale tramite SQLAlchemy
- Struttura modulare pronta per passaggio futuro a PostgreSQL/Supabase

## Agenti

- `ManagerAgent`: riceve il task, decide quali agenti usare e sintetizza la risposta finale.
- `ResearchAgent`: produce analisi, punti chiave e sintesi operative.
- `ContentAgent`: produce script, post e contenuti social.
- `FinanceContentStrategist`: crea strategie contenuto e crescita per il business finance/personal brand di Michele.
- `MemoryCuratorAgent`: dopo ogni task decide cosa salvare nella memoria a lungo termine.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Se vuoi usare OpenAI, inserisci `OPENAI_API_KEY` in `.env`. Senza chiave, il progetto usa risposte locali deterministicamente generate, utili per sviluppo e test.

Per usare Telegram, crea un bot con BotFather e inserisci il token:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_MAX_RESPONSE_CHARS=1200
```

## Avvio

```bash
uvicorn app.main:app --reload
```

API disponibile su:

```text
http://127.0.0.1:8000
```

Avvio Telegram Bot:

```bash
python -m app.telegram_bot
```

Avvio con script production-like:

```bash
./scripts/start_web.sh
./scripts/start_bot.sh
```

## Uso

```bash
curl -X POST http://127.0.0.1:8000/task \
  -H "Content-Type: application/json" \
  -d '{"task":"Analizza il mercato AI per creator e crea 3 post LinkedIn"}'
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Risposta attesa:

```json
{
  "task_id": 1,
  "agents_used": ["research", "content"],
  "final_answer": "...",
  "results": {
    "research": "...",
    "content": "..."
  }
}
```

## Chat

`POST /chat` e l'interfaccia conversazionale principale. Recupera memorie rilevanti, lascia decidere al Manager se rispondere direttamente o attivare altri agenti, poi salva conversazione e output.

Domanda semplice:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Chi sono?"}'
```

Task complesso:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Creami una strategia TikTok per AI Brain"}'
```

Risposta:

```json
{
  "reply": "...",
  "agents_used": ["research", "content"],
  "memories_used": [],
  "task_id": 1
}
```

Esempio finance strategist:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Crea una content strategy TikTok finance per il personal brand di Michele"}'
```

## Telegram Bot

Telegram puo essere usato come interfaccia principale di AI Brain. Ogni messaggio testuale viene inviato alla stessa logica di `POST /chat`, quindi usa retrieval, agenti, memoria persistente e Memory Curator.

Prima dell'invio, `ResponseFormatter` ripulisce e adatta la risposta per Telegram:

- massimo `TELEGRAM_MAX_RESPONSE_CHARS`, default 1200
- italiano naturale e operativo
- niente emoji o markdown decorativo casuale
- struttura semplice: risposta diretta, punti chiave, prossimo passo
- se chiedi esplicitamente dettagli o approfondimento, il limite viene rilassato
- logging qualita: agenti usati, memorie usate, lunghezza risposta e score finale

Comandi supportati:

- `/start`: messaggio di benvenuto
- `/help`: esempi di utilizzo

Esempi di messaggi:

- `Chi sono?`
- `Cosa ricordi di me?`
- `Creami una strategia TikTok per AI Brain`
- `Proponi 5 contenuti LinkedIn coerenti con la mia strategia`

## Memoria

Il database SQLite viene creato automaticamente in `./ai_brain.db`.

Tabelle principali:

- `tasks`: task ricevuti e risposta finale.
- `agent_results`: output prodotti dai singoli agenti.
- `long_term_memory`: memoria strutturata persistente.

Categorie di memoria a lungo termine:

- `user_profile`
- `business_goals`
- `brand_positioning`
- `preferences`
- `decisions`
- `content_strategy`
- `lessons_learned`
- `agents_behavior`
- `project_roadmap`

Leggere tutte le memorie:

```bash
curl http://127.0.0.1:8000/memory
```

Cercare memorie rilevanti:

```bash
curl -X POST http://127.0.0.1:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query":"TikTok","limit":5}'
```

## Memory Retrieval

Prima di eseguire un nuovo task, l'orchestrator recupera automaticamente fino a 7 memorie rilevanti usando:

- overlap di keyword tra task e memoria
- similarita testuale semplice
- piccolo boost basato su `importance`
- priorita per `user_profile`, `business_goals`, `brand_positioning`, `preferences` e `content_strategy`
- deduplica leggera per ridurre memoria ridondante

Le memorie recuperate vengono trasformate da `build_context_from_memory()` in un contesto ordinato per categoria, poi passate nel system prompt di Research, Content e Manager. La risposta di `POST /task` include:

- `memories_used`: memorie recuperate con score
- `agents_used_memory`: agenti che hanno ricevuto il contesto memoria
- `matched_keywords`: keyword che hanno contribuito al retrieval

Nei log dell'app vengono mostrati ID, tipo, titolo e score delle memorie recuperate.

Per PostgreSQL/Supabase in futuro basta cambiare `DATABASE_URL` in `.env`, ad esempio:

```env
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

## Deploy Railway

Il progetto e pronto per Railway con due processi separati:

- `web`: backend FastAPI
- `bot`: Telegram bot in polling

File utili per il deploy:

- `Procfile`
- `railway.json`
- `runtime.txt`
- `scripts/start_web.sh`
- `scripts/start_bot.sh`

Variabili ambiente richieste su Railway:

```env
OPENAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=...
OPENAI_MODEL=gpt-4o-mini
APP_ENV=production
TELEGRAM_MAX_RESPONSE_CHARS=1200
```

Railway imposta automaticamente `PORT` per il servizio web. Lo script `start_web.sh` usa quel valore.

### Servizio backend FastAPI

1. Crea un nuovo servizio Railway collegato al repo.
2. Aggiungi le variabili ambiente.
3. Usa questo start command:

```bash
./scripts/start_web.sh
```

Health check:

```text
/health
```

### Servizio Telegram Bot

Crea un secondo servizio Railway dallo stesso repo e usa:

```bash
./scripts/start_bot.sh
```

Il bot usa `python-telegram-bot` in polling. Deve avere `TELEGRAM_BOT_TOKEN` configurato. Non serve esporre una porta pubblica per il servizio bot.

### Database

Per persistenza 24/7 usa PostgreSQL Railway o Supabase. Imposta `DATABASE_URL` con l'URL Postgres fornito dal provider. Il codice normalizza automaticamente URL `postgres://` e `postgresql://` verso il driver `psycopg`.

SQLite resta supportato in locale:

```env
DATABASE_URL=sqlite:///./ai_brain.db
```
