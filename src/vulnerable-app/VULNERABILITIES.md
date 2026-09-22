# VulnShop – oversikt over plantede sårbarheter

Denne filen er "fasiten" for dere internt (angrepslaget bør ikke få denne før øvingen er ferdig).
Kun til bruk i isolert lab-/øvingsmiljø.

| # | Sårbarhet | Hvor | OWASP-kategori | Flagg / bevis |
|---|-----------|------|-----------------|----------------|
| 1 | SQL-injection i login | `POST /login` | A03: Injection | Logg inn som `admin' --` uten passord |
| 2 | SQL-injection i søk | `GET /search?q=` | A03: Injection | `' OR '1'='1` viser alle produkter uansett søk |
| 3 | Reflektert XSS | `GET /search?q=` | A03: Injection (XSS) | `<script>alert(1)</script>` som søk |
| 4 | Stored XSS | Kommentarfelt på `/product/<id>` | A03: Injection (XSS) | Post en `<script>` som kommentar, se den kjøre for andre besøkende |
| 5 | IDOR | `GET /profile/<id>` | A01: Broken Access Control | `/profile/1` viser admin sin e-post/adresse uten autorisasjon. `bio`-feltet inneholder `FLAG{idor_admin_profile_found}` |
| 6 | Prismanipulering | `POST /checkout` (skjult felt `price`) | A04: Insecure Design | Endre `price` i devtools før innsending, betaler f.eks. 1 kr for VIP-pakke |
| 7 | Usikker filopplasting | `POST /upload` | A04/A05 | Ingen filtype-/størrelsesbegrensning, filer havner direkte i `/static/uploads/` |
| 8 | Path traversal | `GET /download?file=` | A01: Broken Access Control | `?file=../secret_flag.txt` gir `FLAG{path_traversal_outside_reports_dir}`. `?file=../app.py` lekker kildekode |
| 9 | Broken access control (admin) | `GET /admin` | A01: Broken Access Control | Tilgang styres kun av en klient-satt cookie (`role=admin`) – ikke server-side sesjon. Endre cookien i devtools |
| 10 | Command injection | `POST /admin/ping` | A03: Injection | Host-felt: `127.0.0.1; cat secret_flag.txt` (krever admin-cookie, se #9) |
| 11 | Eksponert backup-fil | `GET /static/backup/db_backup.sql` | A05: Security Misconfiguration | Lekker alle brukernavn/passord i klartekst. `FLAG{exposed_backup_file_information_disclosure}` |
| 12 | Sensitiv info i robots.txt / HTML-kommentarer | `/robots.txt`, kildekode på alle sider | A05: Security Misconfiguration | Peker rett på `/admin` og backup-mappen |
| 13 | Svak/hardkodet secret key | `app.secret_key` i `app.py` | A02: Cryptographic Failures | Gjør sesjonscookien forfalskbar hvis man har kildekoden |
| 14 | Passord i klartekst i database | `users`-tabellen | A02: Cryptographic Failures | Ingen hashing (bcrypt/argon2 mangler) |
| 15 | Debug-modus på | `app.run(debug=True)` | A05: Security Misconfiguration | Gir Werkzeug-debugger og stack traces ved feil (i verste fall RCE via debugger-pin hvis eksponert) |
| 16 | `/admin` i `robots.txt` | – | A05 | "Disallow" er ikke tilgangskontroll, kun et hint til søkemotorer – god læring for angripere om rekognosering |

## Forslag til bruk i øvingen
- Gi angrepslaget kun `FLAG{...}`-formatet og et scoreboard, ikke denne fila.
- Forsvarslaget kan bruke denne fila som sjekkliste når de skal patche.
- Reset databasen mellom runder ved å slette `vulnshop.db` og starte appen på nytt (den lages automatisk med `init_db()`).

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
