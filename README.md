# Financial Digital Twin

> **A personal financial decision engine that models your financial life, simulates possible futures, and helps you make better financial decisions.**

[![Status](https://img.shields.io/badge/status-in%20development-yellow)]()
[![Backend](https://img.shields.io/badge/backend-Flask-blue)]()
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-blue)]()
[![Database](https://img.shields.io/badge/database-PostgreSQL-blue)]()
[![AI](https://img.shields.io/badge/AI-LLM%20powered-purple)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

---

## Overview

**Financial Digital Twin** is an AI-enabled financial intelligence platform designed to help users understand not only their current financial position, but also the potential consequences of future decisions.

Traditional personal finance applications answer questions such as:

* How much did I spend?
* How much money do I have?
* How much debt do I have?

Financial Digital Twin asks a different question:

> **"If I make this decision today, what could my financial future look like?"**

Users can model their financial position, analyse historical behaviour, forecast future outcomes, and simulate decisions such as taking on new debt, moving home, buying a car, increasing savings, or changing their income.

---

## Core Concept

The application creates a **digital representation of a user's financial life**.

```text
                       USER
                         │
                         ▼
                 FINANCIAL DATA
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     Transactions      Income         Debt
          │              │              │
          ├──────────────┼──────────────┤
          │              │              │
        Assets         Goals          Credit
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                FINANCIAL DIGITAL TWIN
                         │
              ┌──────────┴──────────┐
              │                     │
         FORECASTING            SIMULATION
              │                     │
              └──────────┬──────────┘
                         │
                         ▼
                      AI CFO
                         │
                         ▼
                  RECOMMENDATIONS
```

---

# Key Features

## Financial Command Centre

A central dashboard providing a real-time view of the user's financial position.

### Metrics

* Net worth
* Monthly income
* Monthly expenses
* Disposable income
* Total debt
* Debt-to-income ratio
* Savings rate
* Emergency fund coverage
* Financial health score
* Credit information
* Upcoming financial obligations

---

## Financial Digital Twin

The core of the application.

The system builds a structured model of the user's financial state using:

* Income
* Expenses
* Transactions
* Assets
* Liabilities
* Debt
* Savings
* Goals
* Credit information
* Historical behaviour

This model becomes the foundation for forecasting and scenario simulation.

---

## Scenario Simulator

Users can create hypothetical financial scenarios and compare the projected outcomes.

### Example

**Scenario: Buy a new car**

```text
Current income             R28,000
Current expenses           R18,500
Current disposable income   R9,500

New car payment             R5,000
Additional insurance        R1,200
Additional fuel               R800

Projected disposable income R2,500
```

The system can then estimate how this decision affects:

* Monthly cash flow
* Savings
* Debt
* Emergency fund
* Financial health
* Net worth
* Long-term goals

### Example scenarios

* Buy a car
* Move to a new home
* Take a loan
* Pay debt faster
* Increase savings
* Start investing
* Receive a salary increase
* Change jobs
* Take a holiday
* Lose income temporarily

---

## Financial Time Machine

Historical financial analysis that goes beyond displaying transactions.

The system identifies patterns such as:

* Lifestyle inflation
* Increasing discretionary spending
* Subscription leakage
* Payday spending
* Increasing transport costs
* Debt accumulation
* Changes in savings behaviour
* Unusual transactions

Instead of simply showing:

> "You spent more this month."

the application aims to explain:

> "Your discretionary spending increased by 22% over the last six months, primarily due to increased transport and entertainment spending."

---

## Financial Behaviour Engine

The system analyses observable financial behaviour and identifies recurring patterns.

Possible classifications include:

* Conservative Saver
* Goal-Oriented Saver
* Debt Accelerator
* High Cash-Flow User
* Lifestyle Spender
* Irregular Income Manager

These classifications are based on financial behaviour rather than psychological diagnosis.

---

## AI Personal CFO

An AI assistant that understands the user's financial context.

Users can ask questions such as:

> "Can I afford a R15,000 holiday?"

> "Why do I keep running out of money before payday?"

> "What should I prioritise this month?"

> "What happens if I pay an extra R1,000 toward my debt?"

> "How long will it take me to become debt-free?"

The AI does not replace the financial calculation engine.

Instead:

```text
User Question
      │
      ▼
Intent Detection
      │
      ▼
Financial Context
      │
      ▼
Financial Calculations
      │
      ▼
Structured Results
      │
      ▼
AI Explanation
      │
      ▼
Recommendation
```

Calculations are performed by deterministic backend services wherever possible. The AI is primarily responsible for reasoning over structured financial context and communicating results clearly.

---

# Financial Health Score

A transparent score representing the user's overall financial position.

Example:

```text
Financial Health
      78 / 100

Cash Flow          82
Debt               71
Savings            64
Emergency Fund     58
Credit             84
Spending Stability 91
```

The score should be explainable, allowing users to understand exactly why their score changed.

---

# Forecasting

The platform forecasts potential financial outcomes over different time horizons.

### Forecast periods

* 30 days
* 3 months
* 6 months
* 1 year
* 3 years
* 5 years

Forecasts can incorporate:

* Historical spending
* Recurring expenses
* Income
* Debt repayments
* Interest
* Savings
* Financial goals
* User-defined assumptions

---

# Debt Intelligence

Each debt is represented as a financial model.

```text
Debt
├── Principal
├── Interest Rate
├── Monthly Payment
├── Remaining Balance
├── Due Date
└── Term
```

The system can calculate:

* Projected payoff date
* Total interest
* Interest saved through additional payments
* Debt snowball strategy
* Debt avalanche strategy
* Impact of changing monthly repayments

---

# Goals Engine

Users can define financial goals and track their progress.

Examples:

* Emergency fund
* Debt-free target
* Vehicle purchase
* Property deposit
* Education
* Travel
* Investment target
* Business capital

The system calculates:

* Required monthly contribution
* Projected completion date
* Current shortfall
* Alternative strategies

---

# Credit Intelligence

Credit information is treated as one component of the broader financial model.

Potential data includes:

* Credit score
* Credit accounts
* Outstanding balances
* Payment history
* Credit utilisation
* Credit enquiries
* Account age
* Adverse information where legally available

Future versions may integrate approved commercial credit-data providers.

The portfolio/MVP version will use synthetic or mocked credit data.

---

# Data Sources

The project is designed to support multiple financial data sources.

### MVP

* Manual financial information
* CSV transaction imports
* Synthetic banking data
* Synthetic credit data

### Future

* Banking data providers
* Open Banking infrastructure
* Credit bureau APIs
* Identity verification
* Financial data aggregation services

External integrations will be implemented through provider adapters so that the core application remains independent of a specific provider.

---

# Technology Stack

## Frontend

* React
* TypeScript
* Tailwind CSS
* Data visualisation library

## Backend

* Python
* Flask
* SQLAlchemy
* REST API
* JWT/session-based authentication
* Gunicorn

## Database

* PostgreSQL

## AI

* LLM API
* Structured prompts
* Financial context layer
* AI recommendation engine

## Infrastructure

* Docker
* Docker Compose
* Nginx
* GitHub Actions

---

# Architecture

```text
                         ┌─────────────────┐
                         │     React       │
                         │   TypeScript    │
                         └────────┬────────┘
                                  │
                               REST API
                                  │
                         ┌────────▼────────┐
                         │     Flask       │
                         │    Backend      │
                         └────────┬────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
   │ Transaction │        │ Financial   │        │   Credit    │
   │   Service   │        │   Engine    │        │   Service   │
   └─────────────┘        └─────────────┘        └─────────────┘
                                  │
                         ┌────────▼────────┐
                         │   Simulation    │
                         │     Engine      │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │   Forecasting   │
                         │     Engine      │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │     AI CFO      │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │   PostgreSQL    │
                         └─────────────────┘
```

---

# Project Structure

```text
financial-digital-twin/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── accounts/
│   │   ├── transactions/
│   │   ├── debts/
│   │   ├── goals/
│   │   ├── credit/
│   │   ├── forecasting/
│   │   ├── scenarios/
│   │   ├── recommendations/
│   │   ├── ai/
│   │   ├── analytics/
│   │   └── core/
│   │
│   ├── tests/
│   ├── migrations/
│   ├── requirements.txt
│   └── run.py
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── types/
│   │
│   └── package.json
│
├── infrastructure/
│   ├── nginx/
│   └── docker/
│
├── docs/
│
├── docker-compose.yml
├── .env.example
├── PLAN.md
└── README.md
```

---

# API

Example endpoints:

```text
POST   /api/auth/register
POST   /api/auth/login

GET    /api/dashboard

GET    /api/accounts
GET    /api/transactions
POST   /api/transactions/import

GET    /api/debts
POST   /api/debts

GET    /api/goals
POST   /api/goals

GET    /api/net-worth
GET    /api/financial-health

GET    /api/forecast

POST   /api/scenarios
GET    /api/scenarios/:id
POST   /api/scenarios/:id/run

GET    /api/recommendations

POST   /api/ai/chat
```

---

# Getting Started

## Prerequisites

Install:

* Python 3.11+
* Node.js 20+
* PostgreSQL
* Docker
* Git

---

## Clone the Repository

```bash
git clone <repository-url>

cd financial-digital-twin
```

---

## Backend Setup

```bash
cd backend

python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

### Linux/macOS

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key

DATABASE_URL=postgresql://postgres:password@localhost:5432/financial_twin

AI_API_KEY=your-api-key
```

Never commit `.env` to source control.

---

## Start the Backend

```bash
python run.py
```

The API should then be available at:

```text
http://localhost:5000
```

---

## Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

The frontend will be available through the development server.

---

# Docker

The project is intended to support local development through Docker Compose.

```bash
docker compose up --build
```

Stop the environment:

```bash
docker compose down
```

---

# Development Roadmap

## Phase 1 - Foundation

* [ ] Project setup
* [ ] Flask API
* [ ] React application
* [ ] PostgreSQL
* [ ] Docker
* [ ] Authentication
* [ ] User profiles

## Phase 2 - Financial Core

* [ ] Accounts
* [ ] Transactions
* [ ] Income
* [ ] Expenses
* [ ] Categories
* [ ] Recurring transactions
* [ ] Assets
* [ ] Liabilities
* [ ] Net worth

## Phase 3 - Financial Intelligence

* [ ] Debt engine
* [ ] Goals engine
* [ ] Financial health score
* [ ] Transaction analytics
* [ ] Spending behaviour analysis
* [ ] Risk engine

## Phase 4 - Forecasting

* [ ] Cash-flow forecasting
* [ ] Savings forecasting
* [ ] Debt payoff forecasting
* [ ] Net-worth projection

## Phase 5 - Simulation

* [ ] Scenario creation
* [ ] Scenario engine
* [ ] Scenario comparison
* [ ] What-if analysis
* [ ] Financial time machine

## Phase 6 - AI

* [ ] AI service
* [ ] Financial context builder
* [ ] AI CFO
* [ ] AI-generated insights
* [ ] AI recommendations
* [ ] Conversation history

## Phase 7 - External Integrations

* [ ] Banking data provider
* [ ] Credit bureau provider
* [ ] Identity verification
* [ ] Production financial data integrations

---

# Security & Privacy

Financial information is highly sensitive.

The application is designed around security and privacy principles including:

* Password hashing
* Secure authentication
* Input validation
* Parameterised database queries
* HTTPS
* Rate limiting
* Secure cookies
* Audit logging
* Data minimisation
* Environment-based secrets
* Access control

The system should never store:

* Banking passwords
* Card PINs
* CVVs
* Internet banking credentials

Production integrations with financial institutions or credit bureaus require appropriate contractual, regulatory, consent, and privacy controls.

---

# Responsible AI

The AI component is designed as an **assistive financial intelligence layer**, not an autonomous financial adviser.

Financial calculations should be performed by deterministic application services where possible.

The AI should:

* Use structured financial context
* Explain calculations
* Identify assumptions
* Communicate uncertainty
* Avoid inventing financial data
* Avoid making unsupported claims

AI-generated recommendations should be presented as decision support rather than guaranteed financial outcomes.

---

# Testing

The project will include multiple levels of testing.

### Unit Tests

Financial calculations, including:

* Interest
* Debt repayment
* Savings
* Forecasting
* Financial health scoring
* Scenario calculations

### Integration Tests

* Authentication
* Database
* REST APIs
* Transaction imports
* AI services

### End-to-End Tests

Example:

```text
Register
   ↓
Create Account
   ↓
Import Transactions
   ↓
Add Debt
   ↓
Create Goal
   ↓
Run Scenario
   ↓
View Forecast
   ↓
Ask AI CFO
```

---

# Why This Project?

Financial Digital Twin is intentionally designed to demonstrate engineering beyond standard CRUD development.

It combines:

### Software Engineering

* REST APIs
* Authentication
* Database architecture
* Service-oriented backend design
* Testing
* Security

### Frontend Engineering

* React
* TypeScript
* State management
* Data visualisation
* Complex financial interfaces

### Data Science

* Forecasting
* Behavioural analysis
* Risk modelling
* Statistical analysis

### Artificial Intelligence

* LLM integration
* Structured prompting
* Context management
* AI-assisted decision support

### DevOps

* Docker
* Nginx
* Gunicorn
* CI/CD
* Environment management

---

# Design Philosophy

The application should avoid becoming another generic budgeting application.

The core principle is:

> **Don't just tell users where their money went. Help them understand where their money could take them.**

The product should make financial decisions interactive.

```text
                 "What if?"
                     │
                     ▼
              Scenario Engine
                     │
                     ▼
              Future Simulation
                     │
                     ▼
              Compare Outcomes
                     │
                     ▼
             Make Better Decisions
```

---

# Disclaimer

This project is intended for educational, research, and portfolio purposes.

It is not intended to provide regulated financial advice, credit decisions, investment advice, or guaranteed financial forecasts.

Production deployment involving banking, credit bureau, identity, lending, or other regulated financial services would require appropriate legal, regulatory, contractual, security, and privacy review.

---

# License

This project is licensed under the MIT License.

See `LICENSE` for more information.

---

## Project Status

🚧 **Currently in development**

The initial objective is to build the financial modelling engine and scenario simulator using synthetic data before introducing external financial-data integrations.

The long-term goal is to evolve the project into a production-grade **personal financial decision platform**.
