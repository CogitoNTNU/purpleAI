# SecureReview development

The backend uses Django 4.2.13, Django REST Framework, SQLite, and
Simple JWT. The frontend uses React, TypeScript, Vite, and Tailwind CSS.
Dependency versions are defined in `backend/requirements.txt` and
`frontend/package.json`.

## Backend

From the repository root:

```bash
cd src/defender/vulnerable-web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The development server listens at `http://localhost:8000/`.

The repository includes a `populate_db` management command. It **deletes
existing application records and media** before creating sample users,
businesses, and reviews:

```bash
python manage.py populate_db
```

Its sample accounts are `admin` / `admin`, `owner1` through `owner3` /
`password`, and `reviewer1` through `reviewer5` / `password`.

The container entrypoint applies migrations and invokes `populate_db`
only when the database has no users.

## Frontend

From the repository root, with Node.js and npm installed:

```bash
cd src/defender/vulnerable-web/frontend
npm install
npm run dev
```

`vite.config.ts` sets development and preview ports to 3000.

```bash
npm run build
npm run preview
npm run lint
```

The frontend Dockerfile builds `dist/` and serves it on container port
3000. The [Compose setup](../README.md) publishes Nginx on port 80 and
the defender on port 8080.
