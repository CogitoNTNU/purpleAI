# Running Vulnerable-App with Defender

This setup runs the vulnerable Flask app behind the defender agent, which protects it from SQL injection attacks using an LLM.

## Architecture

```
Client → Defender (port 8080) → Vulnerable-App (port 5000, internal only)
           │
           └─ asks IDUN LLM: "Is this SQL injection?"
                YES → 403 Forbidden
                NO  → forward to vulnerable-app
```

## Prerequisites

- Docker Desktop
- NTNU VPN connection (to reach IDUN LLM API)
- IDUN API key from https://ai.hpc.ntnu.no/request-api-key

## Running

1. **Connect to NTNU VPN**

2. **Set environment variables:**
   ```bash
   export IDUNN_BASE_URL="https://llm.hpc.ntnu.no/v1"
   export IDUNN_API_KEY="your-api-key-here"
   ```

3. **Start the services:**
   ```bash
   cd src
   docker compose up --build
   ```

4. **Access the app:**
   - Through defender (protected): http://localhost:8080
   - The vulnerable-app is NOT exposed directly - defender is the only way in

## Testing

**Normal request (should pass):**
```bash
curl http://localhost:8080/
```

**SQL injection (should be blocked with 403):**
```bash
curl "http://localhost:8080/search?q=' OR 1=1--"
```

**Check logs:**
```bash
docker logs -f defender
```

You should see `[ok]` for normal requests and `[BLOCKED]` for attacks.

## Stopping

```bash
docker compose down
```
