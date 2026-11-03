# KOL Hub - Aplikasi Digital Marketing Mitra10

Aplikasi web internal tim Digital Marketing Mitra10 untuk mengelola KOL & Portal News dari hulu ke hilir.

## Tech Stack

### Frontend
- Next.js 14 (React, TypeScript)
- Tailwind CSS + shadcn/ui
- TanStack Query & Table
- ECharts (grafik)

### Backend
- Python 3.12 + FastAPI
- SQLAlchemy 2 + Pydantic v2
- PostgreSQL 16 + pgvector
- Redis + Celery (job queue)

### Machine Learning
- LightGBM (scoring & ranking)
- statsforecast (time series)
- OR-Tools (optimasi budget)
- sentence-transformers (embedding)
- MLflow (model registry)

### Infrastructure
- Docker Compose (development)
- MinIO (file storage)
- GitHub Actions (CI/CD)

## Project Structure

```
kol-hub/
├─ apps/web/              # Next.js frontend
├─ services/api/          # FastAPI backend
├─ services/worker/      # Celery tasks
├─ ml/                    # ML models & preprocessing
├─ tests/                 # Tests (unit, integration, e2e)
├─ infra/                 # Docker compose & configs
└─ data/                  # Data & migrations
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- Python 3.12+
- PostgreSQL 16

### Development Setup

1. Clone repository
2. Copy environment files:
   ```bash
   cp .env.example .env
   cp apps/web/.env.example apps/web/.env.local
   cp services/api/.env.example services/api/.env
   ```

3. Start services:
   ```bash
   docker-compose up -d
   ```

4. Run migrations:
   ```bash
   cd services/api
   alembic upgrade head
   ```

5. Seed initial data:
   ```bash
   python scripts/seed_master_data.py
   ```

6. Start development servers:
   ```bash
   # Frontend (port 3000)
   cd apps/web && npm run dev

   # Backend (port 8000)
   cd services/api && uvicorn app.main:app --reload
   ```

## Roles

- **E-commerce**: Dashboard, database KOL, campaign, approval level 1
- **Asisten Manager**: Approval level 1
- **Manager**: Approval level 2
- **Store**: Request KOL, view reports
- **Finance**: Payments, pajak, RO verification
- **Super User**: User management, monitoring

## Key Features

1. **Social Media Listening**: Instagram & TikTok integration
2. **KOL Database**: Scoring, categorization, performance tracking
3. **Campaign Management**: Multi-level approval, budget optimization
4. **Traffic Analysis**: Online vs offline impact measurement
5. **Payment & Tax**: Automated calculations, document management
6. **Brief Management**: Creative brief with PowerPoint export

## Documentation

- [API Documentation](/services/api/docs/api.md)
- [Database Schema](/services/api/docs/database.md)
- [ML Models](/ml/docs/models.md)
- [Deployment Guide](/infra/docs/deployment.md)

## License

Internal use only - Mitra10
