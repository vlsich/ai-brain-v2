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
- `ContentPlannerAgent`: crea piani editoriali settimanali, idee contenuto e task di crescita multi-platform.
- `DailyReviewAgent`: genera briefing giornalieri su task, decisioni, memoria e priorita business.
- `WeeklyReviewAgent`: produce review settimanali su progressi, task completati, decisioni e allineamento agli obiettivi.
- `MemoryCuratorAgent`: dopo ogni task decide cosa salvare nella memoria a lungo termine.

## Conversational State e ruoli

AI Brain mantiene uno stato conversazionale per chat: topic attivo, task attivo, agente attivo, intent, ultimo messaggio utente, ultima risposta, ultimo contenuto generato e tipo di output. I follow-up come `continua`, `e il resto?`, `approfondisci`, `finiscilo`, `completa` e `fammi la versione completa` riprendono il contenuto precedente invece di aprire una nuova conversazione.

Il sistema assegna anche un ruolo professionale in base all'intent:

- `content_creation`: Content Director
- `strategy`: Strategy Advisor
- `business_analysis`: Research Analyst
- `tasks/priorities`: Operations Manager
- `goals`: CEO/Manager Agent
- `decisions`: Executive Advisor

## AI Brain V3 Architecture

AI Brain V3 introduce un livello di Cognitive Operating System sopra i moduli esistenti.

Layer principali:

- `BrainOS` (`app/brain_os.py`): coordinatore centrale. Riceve input, risolve contesto, chiama ToolRouter o agenti, aggiorna lo stato conversazionale e restituisce la risposta finale.
- `ToolRouter` (`app/tool_router.py`): intercetta comandi diretti prima di qualunque LLM. Esempi: `qual è il mio chat id?`, `mostra obiettivi`, `briefing di oggi`, `ricostruisci graph`.
- `RoleRouter` (`app/role_router.py`): assegna il ruolo professionale: Content Director, Strategy Advisor, CEO Agent, Operations Manager, Executive Advisor o Research Analyst.
- `CognitiveContextBuilder` (`app/context_builder.py`): costruisce il contesto prima delle chiamate cognitive usando Brain State, memorie semantiche, obiettivi, task, decisioni, stato conversazionale e insight del Knowledge Graph.
- `ResponseSynthesizer` (`app/response_synthesizer.py`): produce la risposta finale naturale, senza JSON grezzo e senza template corporate forzati.

Execution flow:

1. Telegram o API inviano un messaggio a `BrainOS`.
2. `CognitiveContextBuilder` risolve stato conversazionale, intent, ruolo e contesto.
3. `ToolRouter` prova a gestire comandi di sistema senza LLM.
4. Se non è un comando diretto, `BrainOS` delega agli agenti esistenti tramite orchestrator.
5. `ResponseSynthesizer` adatta la risposta al canale e all'intent.
6. Lo stato conversazionale viene aggiornato e la memoria resta compatibile con i sistemi esistenti.

## Obsidian Sync

AI Brain può esportare il suo Second Brain in un Obsidian Vault senza usare Telegram, OpenAI o LLM.

Configura il percorso:

```env
OBSIDIAN_VAULT_PATH=/Users/michelevalsecchii/Documents/AI Brain Vault
```

Esegui l'export da Python:

```python
from app.brain.graph_exporter import GraphExporter

GraphExporter.export_all()
```

Puoi anche attivare il sync manualmente:

```bash
curl -X POST http://127.0.0.1:8000/obsidian/export
```

Da Telegram/chat:

- `sincronizza obsidian`
- `aggiorna obsidian`
- `esporta brain su obsidian`

Il sync crea le cartelle `01 Goals`, `02 Projects`, `03 Areas`, `04 Knowledge`, `05 People`, `06 Content`, `07 Decisions`, `08 Tasks`, `09 Daily` e aggiorna solo la sezione generata da AI Brain dentro ogni nota, preservando gli appunti manuali.

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
TELEGRAM_ADMIN_CHAT_ID=123456789
TELEGRAM_MAX_RESPONSE_CHARS=2500
```

Per scoprire il tuo chat id, avvia il bot e scrivi:

```text
qual è il mio chat id?
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

## Autonomous Scheduler

Lo scheduler gira solo nel servizio Telegram bot, non nel servizio web FastAPI.

Routine automatiche:

- briefing giornaliero ogni mattina tramite `AutonomousDailyWorker`
- review settimanale la domenica sera
- refresh quotidiano del Brain State
- analisi quotidiana del Knowledge Graph

Per evitare spam:

- massimo 1 briefing giornaliero al giorno
- massimo 1 review settimanale a settimana
- Brain State refresh e Graph Analysis girano in silenzio

Configurazione:

```env
TELEGRAM_ADMIN_CHAT_ID=123456789
SCHEDULER_ENABLED=true
SCHEDULER_DAILY_BRIEFING_HOUR=8
SCHEDULER_WEEKLY_REVIEW_HOUR=18
SCHEDULER_TICK_SECONDS=60
```

Disabilitare lo scheduler:

```env
SCHEDULER_ENABLED=false
```

Trigger manuali del Daily Worker da Telegram/chat:

- `genera briefing automatico`
- `daily worker`
- `lavora per me oggi`

Il worker analizza obiettivi attivi, task pendenti, calendario editoriale, decisioni recenti, memorie recenti, Brain State e Knowledge Graph. Se `TELEGRAM_ADMIN_CHAT_ID` non è configurato, il bot non invia briefing automatici e registra un warning nei log.

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

Esempio piano editoriale via chat:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Creami il piano editoriale della settimana"}'
```

Esempio Proactive Brain Loop:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"briefing di oggi"}'
```

Altri comandi supportati:

- `cosa dovrei fare oggi?`
- `preparami la giornata`
- `dammi il focus di oggi`

Il briefing usa obiettivi attivi, task pendenti, decisioni recenti, memoria, calendario editoriale e Brain State Summary. Produce focus del giorno, top 3 priorita, idee contenuto, raccomandazioni business, rischi e prossime azioni.

Esempio Goal-to-Content Pipeline:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"trasforma i miei obiettivi in contenuti"}'
```

Comandi equivalenti:

- `creami contenuti in base agli obiettivi`
- `genera task dai miei obiettivi`
- `prepara piano operativo settimanale`

La pipeline legge gli obiettivi attivi, genera idee contenuto collegate a ogni obiettivo, crea task pratici, assegna priorita in base all'importanza dell'obiettivo e salva idee/task nel calendario editoriale.

Esempio stato conversazionale e follow-up:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"manual-test","message":"Scrivi un post LinkedIn sugli ETF per il personal brand finance di Michele"}'
```

Poi continua nella stessa conversazione:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"manual-test","message":"e il resto?"}'
```

Risultato atteso: AI Brain continua o completa il post LinkedIn precedente, invece di trattare `e il resto?` come una nuova domanda.

## Telegram Bot

Telegram puo essere usato come interfaccia principale di AI Brain. Ogni messaggio testuale viene inviato alla stessa logica di `POST /chat`, quindi usa retrieval, agenti, memoria persistente e Memory Curator.

Il bot mantiene anche uno stato conversazionale per chat Telegram: se scrivi `continua`, `e il resto?`, `approfondisci`, `finiscilo` o `fammi la versione completa`, AI Brain riprende topic, task, agente e contenuto precedente.

Prima dell'invio, `ResponseFormatter` ripulisce e adatta la risposta per Telegram:

- massimo `TELEGRAM_MAX_RESPONSE_CHARS`, default 2500
- Markdown Telegram pulito
- italiano naturale, chiaro e operativo
- niente emoji e niente simboli decorativi casuali
- struttura consigliata: risposta diretta, analisi, piano operativo, prossimo step
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
- `Creami il piano editoriale della settimana`
- `Briefing di oggi`
- `Preparami la giornata`
- `Dammi il focus di oggi`
- `Dammi idee contenuto`
- `Cosa sai di me?`
- `Mostrami il mio brain state`
- `Aggiorna il mio second brain`
- `Quali concetti sono collegati?`
- `Cosa sto costruendo?`
- `Quali task devo fare oggi?`
- `Briefing giornaliero`
- `Review settimanale`
- `Mostrami le priorita`
- `Aiutami a decidere se lanciare una newsletter`
- `Pro e contro TikTok o LinkedIn`
- `Cosa mi consigli per aumentare conversione audience?`
- `Valuta questa decisione: concentrare i contenuti sugli ETF`
- `Salva questa decisione: focus su TikTok per 30 giorni`
- `Segna task completato 3`
- `Quali sono i miei obiettivi?`
- `Crea un obiettivo aumentare fiducia audience finance`
- `Aggiorna progresso obiettivo 2 a 35%`
- `Quali task supportano i miei obiettivi?`
- `Dammi le priorita della settimana in base agli obiettivi`

## Goal Management

AI Brain gestisce obiettivi strategici e li collega a task, decisioni, review e piani contenuto. Gli obiettivi attivi vengono inclusi nel `Brain State Summary`, nel contesto degli agenti e nelle priorita operative.

Categorie supportate:

- `business`
- `personal_brand`
- `content`
- `finance`
- `audience`
- `monetization`
- `operations`

Timeframe supportati:

- `yearly`
- `quarterly`
- `monthly`
- `weekly`

Se non esistono obiettivi, AI Brain inizializza obiettivi base:

- Grow Michele's finance personal brand
- Build consistent multi-platform content system
- Improve audience trust and authority
- Convert audience into leads/customers
- Build AI Brain as business operating system

Creare un obiettivo:

```bash
curl -X POST http://127.0.0.1:8000/goals \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Aumentare lead qualificati dalla newsletter finance",
    "description":"Usare contenuti educativi e CTA per trasformare audience in lead.",
    "category":"monetization",
    "timeframe":"monthly",
    "priority":"high",
    "success_metric":"Lead qualificati generati",
    "target_value":"100 lead",
    "related_topic":"newsletter finance"
  }'
```

Leggere obiettivi:

```bash
curl http://127.0.0.1:8000/goals
curl http://127.0.0.1:8000/goals/active
```

Aggiornare progresso:

```bash
curl -X PATCH http://127.0.0.1:8000/goals/1 \
  -H "Content-Type: application/json" \
  -d '{"current_value":"35 lead"}'
```

## Proactive Productivity Layer

AI Brain include un layer produttivo per trasformare memoria, obiettivi e decisioni in azioni operative.

Componenti:

- `TaskEngine`: crea, aggiorna, completa e prioritizza task business.
- `DecisionEngine`: valuta scelte strategiche con opzioni, pro, contro, rischi, raccomandazione e prossima azione.
- `DecisionJournal`: salva decisioni strategiche di Michele.
- `DailyReviewAgent`: genera briefing giornalieri.
- `WeeklyReviewAgent`: genera review settimanali.

Ogni task, decisione e review salva metadati relazionali per il futuro Knowledge Graph:

- `related_goal`
- `related_project`
- `related_topic`

Il layer usa `Brain State Summary` e memory retrieval, con focus su finanza, investing, content creation, personal brand growth, audience building e monetizzazione.

Quando crei task o decisioni senza `related_goal`, AI Brain prova a collegarli automaticamente all'obiettivo attivo piu coerente.

Supporto decisionale via chat o Telegram:

- `aiutami a decidere`
- `cosa mi consigli?`
- `valuta questa decisione`
- `pro e contro`
- `salva questa decisione`

Il Decision Engine usa obiettivi attivi, task recenti, decisioni salvate, memoria, Brain State Summary e profilo business. Quando Michele chiede di salvare una decisione o scrive che ha deciso, il risultato viene registrato nel Decision Journal.

Creare un task:

```bash
curl -X POST http://127.0.0.1:8000/productivity/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Preparare contenuto TikTok su errore comune negli investimenti",
    "description":"Hook, struttura e CTA verso newsletter.",
    "category":"finance_content",
    "priority":"high",
    "estimated_minutes":45,
    "related_goal":"audience building",
    "related_project":"personal brand finance",
    "related_topic":"investing"
  }'
```

Leggere task pendenti:

```bash
curl http://127.0.0.1:8000/productivity/tasks/pending
```

Leggere priorita alte:

```bash
curl http://127.0.0.1:8000/productivity/tasks/high-priority
```

Completare un task:

```bash
curl -X POST http://127.0.0.1:8000/productivity/tasks/1/complete
```

Salvare una decisione:

```bash
curl -X POST http://127.0.0.1:8000/decisions \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Focus TikTok per 30 giorni",
    "decision":"Michele concentra la produzione short-form su TikTok per validare format finance.",
    "reasoning":"Serve velocita di feedback e crescita audience.",
    "expected_outcome":"Capire quali hook e format generano piu retention e lead.",
    "related_goal":"audience building",
    "related_project":"personal brand finance",
    "related_topic":"TikTok"
  }'
```

Leggere decisioni e review:

```bash
curl http://127.0.0.1:8000/decisions
curl http://127.0.0.1:8000/reviews/daily
curl http://127.0.0.1:8000/reviews/weekly
```

## Editorial Planning

Il sistema editoriale genera e salva piani, idee e task per il business finance/personal brand di Michele. Usa `Brain State Summary` e memory retrieval per mantenere coerenza con identita, obiettivi, posizionamento e strategia contenuti.

Focus operativo:

- finanza personale
- educazione finanziaria
- investimenti
- personal brand finance
- crescita multi-platform
- conversione audience

Creare un piano settimanale:

```bash
curl -X POST http://127.0.0.1:8000/editorial/plan \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Crea il piano editoriale della settimana per TikTok, Instagram e YouTube"}'
```

Leggere idee contenuto:

```bash
curl http://127.0.0.1:8000/editorial/ideas
```

Filtrare per piattaforma o stato:

```bash
curl "http://127.0.0.1:8000/editorial/ideas?platform=TikTok&status=idea"
```

Leggere task editoriali:

```bash
curl http://127.0.0.1:8000/editorial/tasks
```

## Memoria

Il database SQLite viene creato automaticamente in `./ai_brain.db`.

Tabelle principali:

- `tasks`: task ricevuti e risposta finale.
- `agent_results`: output prodotti dai singoli agenti.
- `long_term_memory`: memoria strutturata persistente.
- `goals`: obiettivi strategici e metriche di progresso.
- `editorial_plans`: contenuti pianificati.
- `content_ideas`: idee contenuto salvate.
- `content_tasks`: task operativi per produzione e crescita.
- `business_tasks`: task operativi del Productivity Layer.
- `decisions`: decision journal strategico.
- `daily_reviews`: briefing giornalieri salvati.
- `weekly_reviews`: review settimanali salvate.

Categorie di memoria a lungo termine:

- `identity`
- `business_profile`
- `goals`
- `tasks`
- `agent_instructions`
- `user_profile`
- `business_goals`
- `brand_positioning`
- `preferences`
- `decisions`
- `content_strategy`
- `lessons_learned`
- `agents_behavior`
- `project_roadmap`

## Brain Core

`BrainCore` trasforma la memoria lunga in un cervello persistente. Mantiene un `Brain State Summary` sempre aggiornato con identita, business profile, obiettivi attivi, priorita correnti, progetti, brand positioning, stile di lavoro, content pillars e decisioni strategiche.

Il Second Brain aggiunge:

- `SemanticMemory`: indicizza le memorie con embeddings OpenAI quando disponibili, con fallback locale SQLite.
- `KnowledgeGraph`: crea nodi e relazioni tra Michele, business, goal, topic, platform, content pillars, decisioni e progetti.
- retrieval prima di ogni risposta con Brain State, memorie semantiche, obiettivi, task e decisioni recenti.
- aggiornamento automatico dopo conversazioni importanti tramite Memory Curator.

Tipi memoria canonici:

- `identity`
- `business_profile`
- `goals`
- `preferences`
- `brand_positioning`
- `content_strategy`
- `decisions`
- `lessons`
- `tasks`
- `agent_instructions`

Leggere lo stato del Brain:

```bash
curl http://127.0.0.1:8000/brain/state
```

Seed manuale del Brain:

```bash
curl -X POST http://127.0.0.1:8000/brain/seed \
  -H "Content-Type: application/json" \
  -d '{
    "memories": [
      {
        "memory_type": "goals",
        "title": "Priorita corrente",
        "content": "Migliorare AI Brain come cervello operativo per business finance e personal brand.",
        "importance": 5
      }
    ]
  }'
```

Il Manager Agent riceve il `Brain State Summary` prima di rispondere. Dopo ogni task importante, il Memory Curator salva eventuali memorie utili e il Brain State viene aggiornato.

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

Cercare memorie semantiche:

```bash
curl -X POST http://127.0.0.1:8000/memory/semantic/search \
  -H "Content-Type: application/json" \
  -d '{"query":"crescita personal brand finance","limit":5}'
```

Leggere concetti collegati:

```bash
curl "http://127.0.0.1:8000/brain/concepts?query=TikTok&limit=10"
```

## Knowledge Graph API

AI Brain espone il Second Brain come grafo pronto per una futura dashboard visuale.

Endpoint disponibili:

- `GET /graph/nodes`
- `GET /graph/edges`
- `GET /graph`
- `GET /graph/search?q=...`
- `POST /graph/rebuild`
- `GET /graph/insights`
- `GET /graph/clusters`
- `GET /graph/gaps`

Export completo:

```bash
curl http://127.0.0.1:8000/graph
```

Risposta:

```json
{
  "nodes": [],
  "edges": []
}
```

Ricerca nel grafo:

```bash
curl "http://127.0.0.1:8000/graph/search?q=business"
```

Ricostruire il grafo:

```bash
curl -X POST http://127.0.0.1:8000/graph/rebuild
```

Analizzare il grafo:

```bash
curl http://127.0.0.1:8000/graph/insights
curl http://127.0.0.1:8000/graph/clusters
curl http://127.0.0.1:8000/graph/gaps
```

## Graph Visual Dashboard

AI Brain include una dashboard web V1 per visualizzare il Knowledge Graph senza React o build system.

Aprire in locale:

```text
http://127.0.0.1:8000/dashboard
```

Aprire su Railway:

```text
https://YOUR-RAILWAY-URL/dashboard
```

La pagina carica automaticamente `GET /graph`, mostra nodi e relazioni con Cytoscape.js, permette di cliccare un nodo per vedere dettagli e connessioni, e include statistiche su nodi, edge, tipi principali e connessioni piu forti.

Tipi nodo supportati: `person`, `business`, `goal`, `platform`, `content_pillar`, `project`, `task`, `decision`, `topic`, `agent`, `strategy`.

Tipi relazione supportati: `related_to`, `supports`, `depends_on`, `created_by`, `improves`, `belongs_to`, `conflicts_with`, `inspired_by`.

Comandi Telegram/Chat per il Second Brain:

- `cosa sai di me?`
- `mostrami il mio brain state`
- `aggiorna il mio second brain`
- `quali concetti sono collegati?`
- `mostrami i concetti collegati`
- `cosa e collegato al mio business?`
- `quali nodi ci sono nel mio brain?`
- `ricostruisci il knowledge graph`
- `analizza il mio brain`
- `cosa manca nel mio brain?`
- `quali sono i nodi piu importanti?`
- `quali opportunita vedi?`
- `cosa sto costruendo?`

## Memory Retrieval

Prima di eseguire un nuovo task, l'orchestrator recupera automaticamente:

- overlap di keyword tra task e memoria
- similarita testuale semplice
- memorie semantiche tramite embeddings o fallback locale
- Brain State Summary
- obiettivi attivi
- decisioni recenti
- task rilevanti
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
TELEGRAM_ADMIN_CHAT_ID=...
DATABASE_URL=...
OPENAI_MODEL=gpt-4o-mini
APP_ENV=production
TELEGRAM_MAX_RESPONSE_CHARS=2500
SCHEDULER_ENABLED=true
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

Il bot usa `python-telegram-bot` in polling. Deve avere `TELEGRAM_BOT_TOKEN` configurato. Per ricevere briefing automatici imposta anche `TELEGRAM_ADMIN_CHAT_ID`. Non serve esporre una porta pubblica per il servizio bot.

### Database

Per persistenza 24/7 usa PostgreSQL Railway o Supabase. Imposta `DATABASE_URL` con l'URL Postgres fornito dal provider. Il codice normalizza automaticamente URL `postgres://` e `postgresql://` verso il driver `psycopg`.

SQLite resta supportato in locale:

```env
DATABASE_URL=sqlite:///./ai_brain.db
```
# ai-brain-v2
# ai-brain-v2
