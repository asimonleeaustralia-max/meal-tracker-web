# MacrosSimple — Microservices Backend

A Python/FastAPI microservices backend that complements the **MacrosSimple iOS app**. Designed to sync with the iOS Core Data model (`Meal`, `Person`, `MealPhoto`), recognize meal contents from photos via a vision model running on **RunPod**, and resolve nutritional values from a reference database.

## Architecture overview

```
                                                    ┌──────────────────────────┐
                                                    │  RunPod Vision Endpoint  │
                                                    │  (food-recognition LLM)  │
                                                    └────────────▲─────────────┘
                                                                 │ HTTPS
                                                                 │
   iOS app  ──┐                                                  │
              │       ┌─────────────┐    ┌─────────────────┐     │
   Web UI  ───┼──►   │ api-gateway │──►│  auth-service   │     │
              │       │  (FastAPI)  │   │  (JWT + OAuth)  │     │
              │       └──────┬──────┘    └────────┬────────┘     │
              │              │                    │              │
              │              │           ┌────────▼────────┐     │
              │              ├──────────►│  meal-service   │     │
              │              │           │ (meals, photos) │     │
              │              │           └────────┬────────┘     │
              │              │                    │              │
              │              │           ┌────────▼────────┐     │
              │              ├──────────►│ vision-service  │─────┘
              │              │           │  (RunPod proxy) │
              │              │           └────────┬────────┘
              │              │                    │
              │              │           ┌────────▼────────┐
              │              └──────────►│nutrition-service│
              │                          │ (food ↔ macros) │
              │                          └────────┬────────┘
              │                                   │
              │                          ┌────────▼────────────────────┐
              └─────────────────────────►│  PostgreSQL (Flexible Srv)  │
                                         │  schemas: auth, meal,       │
                                         │  nutrition                  │
                                         └─────────────────────────────┘
```

## Services

| Service             | Port (dev) | Responsibility                                                    |
|---------------------|------------|-------------------------------------------------------------------|
| `api-gateway`       | 8080       | Single public entrypoint. Validates JWT, routes by path prefix.   |
| `auth-service`      | 8001       | Signup/login, JWT issue/verify, Google/Apple/Facebook OAuth.      |
| `meal-service`      | 8002       | Per-user meal CRUD, photo metadata, sync endpoints for iOS.       |
| `nutrition-service` | 8003       | Reference DB of foods + their macros, vitamins, minerals.         |
| `vision-service`    | 8004       | Calls RunPod inferencing endpoint, returns food predictions.      |
| `web-frontend`      | 3000       | Minimal HTML/JS shell to exercise the API in a browser.           |

Each service is an **independent FastAPI app in its own Docker container**, deployable as a separate Azure Container App.

## Database choice

The cheapest credible default is **Azure Database for PostgreSQL Flexible Server, Burstable B1ms** (1 vCore / 2 GiB RAM, ≈ US$12/month + storage). All services speak vanilla Postgres, so you can also point at:

- **Neon** — serverless Postgres, free tier (0.5 GB, scales to zero) — best for dev/hobby
- **Supabase** — free tier (500 MB, pauses after 7 days idle)
- Self-hosted Postgres in another container

Switch by changing `DATABASE_URL` — no code changes.

Each service writes to its **own schema** in the same Postgres instance (`auth`, `meal`, `nutrition`). This is the "shared database, separate schemas" microservices pattern — cheap and operationally simple, and you can split into separate DB instances later if any service outgrows it.

## Quick start (local)

```bash
cp .env.example .env          # fill in OAuth client IDs + RunPod key
docker compose up --build
```

Then:
- API gateway: <http://localhost:8080>
- Web frontend: <http://localhost:3000>
- Each service exposes Swagger UI at `/docs` (e.g. <http://localhost:8001/docs>)

## Deploying to Azure

Follow **[`docs/azure-deployment.md`](docs/azure-deployment.md)** — step-by-step, copy-pasteable Azure CLI commands. Step 15 covers pointing a GoDaddy domain at the deployed app with a free managed TLS certificate.

## Project layout

```
mealtracker-web/
├── services/
│   ├── api-gateway/          # FastAPI reverse proxy
│   ├── auth-service/         # Users, JWT, OAuth
│   ├── meal-service/         # Meal/Person/MealPhoto
│   ├── nutrition-service/    # Food reference DB
│   ├── vision-service/       # RunPod client
│   └── web-frontend/         # Static HTML/JS
├── libs/shared/              # Shared Python pkg (JWT verify, DB base)
├── infra/
│   ├── azure/                # Bicep / az CLI scripts
│   └── docker/               # Shared Docker bits
├── docs/                     # Architecture & deployment guides
├── scripts/                  # Dev helpers (seed DB etc.)
├── docker-compose.yml
└── .env.example
```

## iOS sync model

The `meal-service` mirrors the iOS Core Data entities. See `docs/ios-sync-mapping.md` for the field-by-field map between Swift `Meal`/`Person`/`MealPhoto` and the SQL tables.
