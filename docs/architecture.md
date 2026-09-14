# System Architecture

## Stack

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS

### Backend

- Python
- Flask
- SQLAlchemy
- Alembic

### Database

- PostgreSQL

### Infrastructure

- Docker
- Docker Compose
- Nginx
- Terraform

### Testing

- Pytest
- Vitest
- Playwright

## Architecture

The system follows a layered architecture.

Frontend
    ↓
REST API
    ↓
Application Services
    ↓
Domain Services
    ↓
Repositories
    ↓
PostgreSQL

## Backend Rules

Routes must remain thin.

Business logic belongs in services.

Database queries belong in repositories.

Financial calculations belong in domain services.

External integrations must be isolated behind integration services.