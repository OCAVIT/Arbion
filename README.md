# Arbion

Automated Deal Management System with dual UI interfaces for business owners and managers.

## Overview

Arbion is a FastAPI-based system designed to:
- Monitor Telegram chats for buy/sell orders
- Automatically match orders to create deals
- Use AI to negotiate with sellers
- Manage deals through human managers
- Track all financial transactions

## Features

### Two-Panel Architecture

#### Admin Dashboard (Owner)
- Full visibility into all data including financial details
- Chat monitoring and management
- Order viewing and filtering
- Complete deal management with all financial data
- Manager creation and performance tracking
- Financial ledger access
- Full audit log of all actions
- System settings configuration

#### Manager Panel
- Limited view of assigned deals only
- No access to:
  - Buy prices
  - Profit margins
  - Buyer information
  - Other managers' deals
  - Financial data
- Chat interface with masked contact info
- Personal statistics

### Security Features

- **Role-based access control**: Strict separation between owner and manager roles
- **JWT authentication**: Tokens stored in httpOnly cookies
- **Data masking**: Phone numbers, usernames, and emails masked at serialization level
- **Audit logging**: All manager actions recorded for review
- **Contact protection**: Managers cannot see real contact information

### Deal Assignment

Two modes available:
1. **Auto-assignment**: System assigns warm leads to the least busy manager
2. **Free pool**: Managers pick deals from a shared pool

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy 2.0 (async)
- **Telegram**: Telethon
- **AI**: OpenAI
- **Vector DB**: Pinecone
- **Auth**: JWT (python-jose)
- **Templates**: Jinja2
- **Scheduler**: APScheduler
- **Deploy**: Railway

## Project Structure

```
src/
├── api/
│   ├── admin/       # Owner-only endpoints
│   ├── panel/       # Manager endpoints
│   ├── auth.py      # Authentication
│   └── health.py    # Health checks
├── auth/
│   ├── jwt.py       # Token management
│   ├── middleware.py # Role-based access
│   └── dependencies.py
├── models/          # SQLAlchemy models
├── schemas/         # Pydantic schemas
├── services/        # Business logic
├── utils/           # Helpers (masking, audit)
├── templates/       # Jinja2 templates
├── static/          # CSS/JS
├── config.py        # Settings
└── main.py          # Application entry
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd arbion
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy environment file:
```bash
cp .env.example .env
```

5. Configure `.env` with your settings.

6. Run database migrations:
```bash
alembic upgrade head
```

7. Start the application:
```bash
uvicorn src.main:app --reload
```

## Environment Variables

See `.env.example` for all required variables:

- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing key
- `OWNER_USERNAME` / `OWNER_PASSWORD` - Initial owner credentials
- `TG_API_ID` / `TG_API_HASH` / `TG_SESSION_STRING` - Telegram credentials
- `OPENAI_API_KEY` - OpenAI API key
- `PINECONE_API_KEY` / `PINECONE_INDEX` - Pinecone credentials

## Database Models

- **User** - Owner and manager accounts
- **MonitoredChat** - Telegram chats being monitored
- **Order** - Extracted buy/sell orders
- **DetectedDeal** - Matched deals between buyers and sellers
- **Negotiation** - Conversation with sellers
- **NegotiationMessage** - Individual messages
- **LedgerEntry** - Financial records
- **SystemSetting** - Application configuration
- **AuditLog** - User action history
- **RawMessage** - Incoming Telegram messages
- **OutboxMessage** - Outgoing message queue

## API Endpoints

### Authentication
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout

### Admin (Owner only)
- `GET /api/admin/metrics` - Dashboard metrics
- `GET /api/admin/chats/list` - Monitored chats
- `GET /api/admin/orders/list` - All orders
- `GET /api/admin/deals/list` - All deals with full data
- `GET /api/admin/managers/list` - Manager list
- `GET /api/admin/finance/ledger` - Financial ledger
- `GET /api/admin/audit/list` - Audit log
- `GET /api/admin/settings/data` - System settings

### Panel (Manager)
- `GET /api/panel/stats` - Personal statistics
- `GET /api/panel/deals/list` - Assigned deals (masked)
- `POST /api/panel/deals/{id}/take` - Take deal from pool
- `GET /api/panel/chat/{id}/messages` - Chat messages (masked)
- `POST /api/panel/chat/{id}/send` - Send message
- `POST /api/panel/chat/{id}/close` - Close deal

## Deployment (Railway)

1. Connect repository to Railway
2. Set environment variables
3. Deploy

The application automatically:
- Creates the owner account on first run
- Initializes default system settings
- Runs database migrations

## Security Considerations

### Manager Data Isolation
Managers NEVER see:
- Buy prices
- Profit margins
- Other managers' deals
- Real contact information (masked)
- Financial data
- System settings

### Audit Trail
All manager actions are logged:
- Login/logout
- Deal views
- Messages sent
- Deal status changes

### Data Masking
Contact information is masked at the Pydantic serialization level:
- Phone: `+7 (999) 123-45-67` → `+7 (9**) ***-**-**`
- Username: `@johndoe` → `@jo***`
- Email: `john@example.com` → `jo***@ex***.com`

## License

MIT
