# SupportLens

AI-powered Customer Support Chatbot with Observability Dashboard

## Repository

```bash
git clone https://github.com/Forhopp-Inc/supportlens.git
cd supportlens
```

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.13+ (for local backend development)
- Google Gemini API key

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Add your Gemini API key to .env
GEMINI_API_KEY=your_key_here
DATABASE_PASSWORD=supportlens123

# 3. Start all services
docker-compose up --build
```

## Access

| Service          | URL                        |
|------------------|----------------------------|
| Chat Interface   | http://localhost:3000      |
| API              | http://localhost:8000      |
| API Docs         | http://localhost:8000/docs |

## Features

- AI chatbot powered by Google Gemini
- Automatic message classification (Billing, Refund, Cancellation, Account Access, General)
- Real-time analytics dashboard
- Conversation trace logging

## Environment Variables

| Variable             | Description            | Default          |
|----------------------|------------------------|------------------|
| `GEMINI_API_KEY`     | Google Gemini API key  | (required)       |
| `DATABASE_PASSWORD`  | Database password      | `supportlens123` |
| `DATABASE_HOST`      | Database hostname      | `localhost`      |
| `DATABASE_PORT`      | Database port          | `3306`           |
| `DATABASE_NAME`      | Database name          | `supportlens`    |
| `DATABASE_USER`      | Database username      | `root`           |
| `DATABASE_TYPE`      | `mysql` or `postgresql`| `mysql`          |

## API Endpoints

| Endpoint     | Method | Description              |
|--------------|--------|--------------------------|
| `/chat`      | POST   | Send message to chatbot  |
| `/traces`    | GET    | Get conversation traces  |
| `/analytics` | GET    | Get aggregate statistics |
| `/health`    | GET    | Health check             |

## Troubleshooting

Database issues? Reset volumes:
```bash
docker-compose down -v
docker-compose up --build
```

## Tech Stack

- Backend: FastAPI + Python
- Frontend: React + Vite
- Database: MySQL
- AI: Google Gemini
