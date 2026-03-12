# SupportLens

AI-powered Customer Support Chatbot with Observability Dashboard

## Quick Start

```bash
# 1. Clone and enter directory
git clone <your-repo-url>
cd SupportLens

# 2. Copy environment file and configure
cp .env.example .env
# Edit .env and add your Gemini API key (optional - app works without it)

# 3. Start all services
docker compose up --build

# 4. Access the application
# Frontend: http://localhost:3000
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Services

| Service   | URL                        | Description                    |
|-----------|----------------------------|--------------------------------|
| Frontend  | http://localhost:3000      | React dashboard & chat UI      |
| Backend   | http://localhost:8000      | FastAPI REST API               |
| API Docs  | http://localhost:8000/docs | Interactive API documentation  |
| Health    | http://localhost:8000/health | Health check endpoint        |

## Features

- **AI Chatbot**: Powered by Google Gemini for intelligent support responses
- **Auto-Classification**: Messages automatically categorized (Billing, Refund, Cancellation, Account Access, General)
- **Analytics Dashboard**: Real-time metrics, trace history grouped by session, uptime display
- **Logs Viewer**: View application logs with level filtering (Error/Warning/Info)
- **Session Tracking**: Conversations grouped by session ID with expandable chat history
- **Graceful Degradation**: Works without LLM API key (fallback classification), shows partial UI when DB is down
- **Production Ready**: Structured logging, health checks, Docker deployment, CI/CD pipeline

## Environment Variables

| Variable             | Description                | Default          | Required |
|----------------------|----------------------------|------------------|----------|
| `GEMINI_API_KEY`     | Google Gemini API key      | (empty)          | No*      |
| `DATABASE_PASSWORD`  | MySQL root password        | `supportlens123` | No       |
| `DATABASE_HOST`      | Database hostname          | `db`             | No       |
| `DATABASE_PORT`      | Database port              | `3306`           | No       |
| `DATABASE_NAME`      | Database name              | `supportlens`    | No       |
| `DATABASE_USER`      | Database username          | `root`           | No       |
| `DATABASE_TYPE`      | `mysql` or `postgresql`    | `mysql`          | No       |
| `DEBUG`              | Enable debug logging       | `false`          | No       |

*Without `GEMINI_API_KEY`, the app runs in degraded mode:
- Chat endpoint returns 503 errors
- Classification defaults to "General_Inquiry"
- All other features work normally

## API Endpoints

| Endpoint     | Method | Description                          |
|--------------|--------|--------------------------------------|
| `/health`    | GET    | Comprehensive health check           |
| `/chat`      | POST   | Send message to chatbot              |
| `/traces`    | GET    | Get conversation traces (paginated)  |
| `/traces`    | POST   | Create a trace manually              |
| `/analytics` | GET    | Get aggregate statistics             |
| `/logs`      | GET    | Get recent application logs          |

### Health Check Response

```json
{
  "status": "healthy|degraded|unhealthy",
  "can_serve_traffic": true,
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "dependencies": {
    "database": {"status": "healthy", "latency_ms": 5.2},
    "llm": {"status": "degraded", "message": "No API key configured"}
  }
}
```

## Development

### Running Tests

```bash
# Run unit tests
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx hypothesis
python -m pytest tests/ -v

# Run E2E tests (requires running services)
./scripts/e2e-test.sh

# Run Python linting
pip install ruff black
ruff check backend/
black --check backend/
```

### CI Pipeline

The project uses GitHub Actions with the following stages:
1. **Lint** - Code quality checks (Ruff, Black)
2. **Unit Tests** - Python backend tests with pytest
3. **Docker Build** - Build and verify image sizes
4. **E2E Tests** - Full integration tests with real HTTP requests

### Docker Commands

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f backend

# Rebuild after code changes
docker compose up --build -d

# Stop services (preserves data)
docker compose down

# Stop and remove all data
docker compose down -v
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│   MySQL     │
│   (React)   │     │  (FastAPI)  │     │  Database   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │  Gemini AI  │
                   │    (LLM)    │
                   └─────────────┘
```

## Troubleshooting

### Database Issues
```bash
# Reset database and volumes
docker compose down -v
docker compose up --build
```

### Seed Data Not Loading
Seed data only loads when the database is empty. To reload:
```bash
docker compose down -v
docker compose up --build
```

### LLM Not Working
1. Check if `GEMINI_API_KEY` is set in `.env`
2. Check health endpoint: `curl localhost:8000/health`
3. View logs: `docker compose logs backend`

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy, Pydantic
- **Frontend**: React 18, Vite, CSS
- **Database**: MySQL 8.0
- **AI**: Google Gemini 2.0 Flash
- **Infrastructure**: Docker, Docker Compose, Nginx
- **CI/CD**: GitHub Actions

