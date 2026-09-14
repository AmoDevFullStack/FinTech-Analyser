# API Specification

Base URL:

/api/v1

## Authentication

POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me

## Accounts

GET    /accounts
POST   /accounts
GET    /accounts/{id}
PATCH  /accounts/{id}
DELETE /accounts/{id}

## Transactions

GET  /transactions
POST /transactions
GET  /transactions/{id}
PATCH /transactions/{id}

## Scenarios

POST /scenarios
GET  /scenarios
GET  /scenarios/{id}
POST /scenarios/{id}/run

## Forecasting

GET /forecast
POST /forecast/run