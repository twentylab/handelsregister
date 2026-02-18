# Handelsregister API Documentation

REST API for searching German company register (Handelsregister).

## Base URL

```
http://localhost:5000
```

## Authentication

Most endpoints require JWT authentication via Bearer token in the Authorization header.

```
Authorization: Bearer <token>
```

## Configuration

Environment variables:

- `JWT_SECRET_KEY` - Secret key for JWT signing (default: `default-secret-key-change-in-production`)
- `RATE_LIMIT_DEFAULT` - Rate limit per IP (default: `100 per hour`)
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: `30`)

## Endpoints

### 1. Generate Token

Generate JWT token for authentication.

**Endpoint:** `POST /api/token`

**Authentication:** None

**Request Body:**
```json
{
  "service_name": "my-service"
}
```

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "service": "my-service"
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/token \
  -H "Content-Type: application/json" \
  -d '{"service_name": "my-service"}'
```

---

### 2. Search Companies

Search for companies by keywords.

**Endpoint:** `GET /api/search`

**Authentication:** Required

**Rate Limited:** Yes

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| keywords | string | Yes | - | Search keywords |
| mode | string | No | all | Search mode: `all`, `min`, `exact` |
| bundesland | string | No | - | Filter by state codes (comma-separated): `BW,BY,BE` |
| force | boolean | No | false | Skip cache and force fresh pull |
| debug | boolean | No | false | Enable debug mode |

**Search Modes:**
- `all` - Contains all keywords
- `min` - Contains at least one keyword
- `exact` - Exact company name match

**Response:**
```json
[
  {
    "court": "Amtsgericht Charlottenburg (Berlin) HRB 12345 B",
    "register_num": "HRB 12345 B",
    "name": "Example GmbH",
    "state": "Berlin",
    "status": "currently registered",
    "statusCurrent": "CURRENTLY_REGISTERED",
    "documents": "...",
    "history": []
  }
]
```

**Example:**
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:5000/api/search?keywords=Gasag%20AG&mode=all&bundesland=BE"
```

---

### 3. Get Bundesland Code

Convert district name (German or English) to bundesland code.

**Endpoint:** `GET /api/bundesland`

**Authentication:** None

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| name | string | Yes | District name in German or English |

**Response:**
```json
{
  "code": "BE",
  "name_de": "Berlin",
  "input": "Berlin",
  "form_field": "bundeslandBE"
}
```

**Examples:**
```bash
# German name
curl "http://localhost:5000/api/bundesland?name=Berlin"

# English name
curl "http://localhost:5000/api/bundesland?name=North%20Rhine-Westphalia"

# Alternative spelling
curl "http://localhost:5000/api/bundesland?name=Nordrhein-Westfalen"
```

---

### 4. List All Bundesländer

List all available German states with their codes.

**Endpoint:** `GET /api/bundesland/list`

**Authentication:** None

**Response:**
```json
[
  {
    "code": "BW",
    "name_de": "Baden-Württemberg",
    "form_field": "bundeslandBW"
  },
  {
    "code": "BY",
    "name_de": "Bayern",
    "form_field": "bundeslandBY"
  }
]
```

**Example:**
```bash
curl "http://localhost:5000/api/bundesland/list"
```

---

### 5. Health Check

Check API health and configuration.

**Endpoint:** `GET /api/health`

**Authentication:** None

**Response:**
```json
{
  "status": "ok",
  "service": "handelsregister-api",
  "config": {
    "rate_limit": "100 per hour",
    "request_timeout": 30
  }
}
```

**Example:**
```bash
curl "http://localhost:5000/api/health"
```

---

### 6. API Documentation

Get API documentation in JSON format.

**Endpoint:** `GET /api/docs`

**Authentication:** None

**Response:** Complete API documentation in JSON format

**Example:**
```bash
curl "http://localhost:5000/api/docs"
```

---

## Bundesland Codes

| Code | German Name | English Name |
|------|-------------|--------------|
| BW | Baden-Württemberg | Baden-Württemberg |
| BY | Bayern | Bavaria |
| BE | Berlin | Berlin |
| BR | Brandenburg | Brandenburg |
| HB | Bremen | Bremen |
| HH | Hamburg | Hamburg |
| HE | Hessen | Hesse |
| MV | Mecklenburg-Vorpommern | Mecklenburg-Western Pomerania |
| NI | Niedersachsen | Lower Saxony |
| NW | Nordrhein-Westfalen | North Rhine-Westphalia |
| RP | Rheinland-Pfalz | Rhineland-Palatinate |
| SL | Saarland | Saarland |
| SN | Sachsen | Saxony |
| ST | Sachsen-Anhalt | Saxony-Anhalt |
| SH | Schleswig-Holstein | Schleswig-Holstein |
| TH | Thüringen | Thuringia |

---

## Error Responses

**400 Bad Request**
```json
{
  "error": "Missing required parameter: keywords"
}
```

**401 Unauthorized**
```json
{
  "error": "Missing authentication token"
}
```

**404 Not Found**
```json
{
  "error": "Unknown district name: XYZ"
}
```

**429 Too Many Requests**
```json
{
  "error": "Rate limit exceeded",
  "message": "100 per 1 hour"
}
```

**500 Internal Server Error**
```json
{
  "error": "Error message"
}
```

**504 Gateway Timeout**
```json
{
  "error": "Request exceeded timeout of 30 seconds"
}
```

---

## Running the API

**Install dependencies:**
```bash
poetry install
```

**Set environment variables:**
```bash
export JWT_SECRET_KEY="your-secret-key"
export RATE_LIMIT_DEFAULT="100 per hour"
export REQUEST_TIMEOUT="30"
```

**Run the server:**
```bash
python api.py --port 5000 --host 0.0.0.0
```

**Using Docker:**
```bash
docker build -t handelsregister-api .
docker run -d -p 5000:5000 \
  -e JWT_SECRET_KEY="your-secret-key" \
  handelsregister-api
```

**Using Docker Compose:**
```bash
docker-compose up -d
```
