# PurpleAI

A lab for training an AI defender agent to detect and respond to web attacks.
An attacker runs attacks against an intentionally vulnerable app, normal traffic
runs alongside it, and a defender agent reads the app's logs to tell the two
apart.

> **Warning**
> The app in `src/vulnerable-app/` contains real vulnerabilities (SQL injection,
> stored XSS, and more). Only run it on an isolated lab network. Never expose it
> to the public internet, and do not bind it to a machine that is also on school
> or home Wi-Fi.

## Project layout

```
purpleai/
├── README.md
└── src/
    ├── docker-compose.yml   
    ├── vulnerable-app/       
    │   ├── app.py
    │   ├── requirements.txt
    │   ├── Dockerfile
    │   └── .dockerignore
    ├── traffic/              
    │   └── normal-traffic.js
    ├── attacks/             
    └── defender/             
```

## Requirements

- Docker and Docker Compose
- Python 3.12+ (optional, only for running the app directly during development)

## Run the lab

All compose commands run from the `src/` folder, where `docker-compose.yml` is:

```bash
cd src
docker compose up --build
```

This starts VulnShop and, alongside it, the k6 normal-traffic generator. The app
is available at http://localhost:5000

The port is bound to `127.0.0.1`, so the app is reachable only from this
machine — the safe default. To let other lab machines reach it, see
[Exposing to the lab network](#exposing-to-the-lab-network).

## Normal traffic

`src/traffic/` holds the k6 script that simulates ordinary users (browsing,
searching, logging in correctly). This is the benign baseline the defender must
learn to leave alone. It starts automatically with `docker compose up` and runs
`traffic/normal-traffic.js`.

The `./traffic` folder is mounted read-only at `/scripts` inside the container,
so you can edit `normal-traffic.js` and rerun without rebuilding. Inside the
script, reach the app by its service name (`vulnshop:5000`), not `localhost`:

```javascript
import http from 'k6/http';
import { sleep } from 'k6';

export const options = { vus: 5, duration: '1m' };

export default function () {
  http.get('http://vulnshop:5000/');
  http.get('http://vulnshop:5000/search?q=juice');
  http.post('http://vulnshop:5000/login', { email: 'anna@lab.local', password: 'password1' });
  sleep(Math.random() * 3);
}
```

To rerun the traffic on its own without restarting the whole lab (from `src/`):

```bash
docker compose run --rm traffic run /scripts/normal-traffic.js
```

The traffic container runs for the script's `duration` and then stops, which is
normal — the app keeps running. For continuous background traffic, set a long
`duration` (e.g. `'24h'`) in the script.

## Attacks

Attacks live in `src/attacks/` and are run from the attacker machine (Kali) with
tools like curl, sqlmap, and ffuf, so the malicious traffic comes from a
different IP than the normal traffic. Keeping the source separate is what lets
the defender attribute an attack to one origin.

Example SQL injection login bypass:

```bash
curl -X POST http://192.168.50.20:5000/login \
  --data-urlencode "email=' OR 1=1--" \
  --data-urlencode "password=x"
```

## Configuration

Set with `environment:` in the compose file, or `-e NAME=value` on `docker run`.

| Variable     | Default | Description                                                                 |
|--------------|---------|-----------------------------------------------------------------------------|
| `VULNERABLE` | `true`  | `true` enables the vulnerabilities; `false` uses the hardened code paths, for before/after comparisons |

To run the hardened version, change the value in `src/docker-compose.yml`:

```yaml
    environment:
      VULNERABLE: "false"
```

## Run the app without Docker (development)

Faster for quick edits, since there is no image to rebuild:

```bash
cd src/vulnerable-app
pip install -r requirements.txt
flask run
```

## Exposing to the lab network

On the target PC, change the app's port mapping in `src/docker-compose.yml` from
`127.0.0.1:5000:5000` to:

```yaml
    ports:
      - "5000:5000"
```

Then reach it from another machine using the target's lab IP, e.g.
`http://192.168.50.20:5000`. If the connection fails, it is almost always the
target's firewall — allow inbound TCP 5000 from the lab subnet only:

```bash
sudo ufw allow from 192.168.50.0/24 to any port 5000
```

To avoid exposing the app by accident, keep this change in a separate
`docker-compose.lab.yml` used only on the target PC, and leave the default
compose file bound to localhost.

## Notes

- The app initializes its SQLite database on startup, so restarting the
  container resets it to a clean state — useful for repeatable demos.
- `.dockerignore` in `src/vulnerable-app/` keeps the database, logs, and any
  `.env` out of the built image.