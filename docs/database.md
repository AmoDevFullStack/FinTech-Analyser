# Database Design

## Core Entities

User
Account
Transaction
Category
Income
Expense
Debt
Asset
Goal
Scenario
Forecast
CreditProfile

## Relationships

User
 ├── Accounts
 ├── Transactions
 ├── Debts
 ├── Assets
 ├── Goals
 └── Scenarios

Account
 └── Transactions

Scenario
 └── ScenarioResults

## Rules

- Every financial record belongs to a user.
- Monetary values must use NUMERIC/Decimal.
- Never use floating-point values for monetary calculations.
- Financial records must have created_at and updated_at timestamps.
- Soft deletion should be used where historical integrity is required.