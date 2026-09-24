# SecureReview

SevureReview is an application for reviewing and exploring different businesses and experiences.

## Prerequisites

Before you start, make sure the following tools are installed on your system:

- **Git:** Version control system to clone the project repository [Download Git](https://git-scm.com/downloads)
- **Docker:** To containerize the application and ensure it runs consistently across different environments [Download Docker](https://www.docker.com/products/docker-desktop)

<!---
## Setup

Insert eventual instructions about environment variables etc. here
-->

## Usage

To run the project, execute the following command in the root folder:

```bash
docker compose up --build -d
```

This will build the Docker images (if necessary) and run the containers in the background. You can access the application at [http://localhost](http://localhost) and the Django backend at [http://localhost/api](http://localhost/api).
The Admin interface for the Django backend is available at [http://localhost/admin](http://localhost/admin).

To stop the containers, you can use the following command:

```bash
docker compose down
```

## Documentation

For more information on how the application is structured, and how to run it without Docker for development, see the [Developer Guide](/docs/developer-guide.md).
