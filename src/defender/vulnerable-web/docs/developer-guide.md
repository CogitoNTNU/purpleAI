# SecureReview Developer Guide

This document explains the general structure of the application, both the frontend and the backend, and explains how to run it for development.

## Technology

- **database** - sqlite3
- **backend** - Django 3 with Django REST framework
- **frontend** - React.ts
- **authentication** - JSON Web Token (JWT)

---

## Installing and running the project

Before you begin, ensure you have the following prerequisites installed:

- **Python and pip**: Make sure you have Python and pip installed. You can download Python from the [official website](https://www.python.org/).
- **Node.js and npm**: Make sure you have Node.js and npm installed. You can download Node.js from the [official website](https://nodejs.org/).

It's recommended to have a look at: [https://www.djangoproject.com/start/](https://www.djangoproject.com/start/)
Just as important is the Django REST guide: [https://www.django-rest-framework.org/](https://www.django-rest-framework.org/)

### Backend Setup

#### Creating a virtual environment

A virtual environment isolates project dependencies, preventing conflicts with system-wide packages and ensuring a consistent development environment.

Navigate into the backend folder `securereview/backend`, and create a virtual environment ([create a virtual environment](https://docs.python-guide.org/dev/virtualenvs/#lower-level-virtualenv)).

#### Activate your virtual environment

To activate the virtual environment, run the following command:

```bash
source venv/bin/activate # On Windows, use `venv\Scripts\activate`
```

#### Install python requirements

```bash
pip install -r requirements.txt
```

#### Migrate database

Apply the database migrations:

```bash
python manage.py migrate
```

#### Create superuser

Create a local admin user:

```bash
python manage.py createsuperuser
```

Input the admin credentials as prompted. Only username and password is required

### Running the backend

To run the backend, use the following command:

```bash
python manage.py runserver
```

The instance will be running at [http://localhost:8000/](http://localhost:8000/) and code changes should update the running code automatically when saving.

For seeding the database (fill out with dummydata) run the command:

```bash
python manage.py populate_db
```

This will create fake businesses and reviewes. It will also create users with the following usernames and passwords:

**Admin user**

- username: admin
- password: admin

**Business owners**

- username: owner1, owner2, owner3
- password: password

**Reviewers**

- username: reviewer1, reviewer2, reviewer3, reviewer4, reviewer5
- password: password

### Set up the frontend app

#### Install dependencies

Navigate into the frontend folder `securereview/frontend` and run

```bash
npm install
```

### Running the frontend

In the same folder, run the following command to start the development server for the frontend

```bash
npm start
```

The frontend will now be running at [http://localhost:3000/](http://localhost:3000/) and code changes should update the running code automatically when saving.
