## API

Base path: `/api/v1/`

### Auth

- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`

Login body:

```json
{
  "username": "seller",
  "password": "testpass123"
}
```

### Products

- `GET /api/v1/products/`
- Query params: `search`, `category_id`

### Categories

- `GET /api/v1/categories/`
- Faqat direktor uchun

### Clients

- `GET /api/v1/clients/`
- Query params: `search`
- Faqat direktor uchun

### Sales

- `GET /api/v1/sales/`
- `GET /api/v1/sales/<id>/`
- `POST /api/v1/sales/`

Sale create body:

```json
{
  "notes": "API orqali savdo",
  "items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 3, "quantity": 1 }
  ]
}
```

Direktor uchun `client_id` yuborish mumkin:

```json
{
  "client_id": 5,
  "notes": "Direktor savdosi",
  "items": [
    { "product_id": 1, "quantity": 1 }
  ]
}
```

### Shifts

- `GET /api/v1/shifts/`
- `GET /api/v1/shifts/current/`
- `POST /api/v1/shifts/start/`
- `POST /api/v1/shifts/end/`
- `GET /api/v1/shifts/<id>/report/`

Sotuvchi uchun sotuv yaratishdan oldin smena ochiq bo'lishi kerak.
