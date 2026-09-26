"""Small, read-only normal-traffic baseline for the lab web app."""

from locust import HttpUser, between, task


class NormalUser(HttpUser):
    # Each simulated user pauses between requests, like a person browsing.
    wait_time = between(2, 5)

    def visit(self, path: str, name: str | None = None) -> None:
        self.client.get(
            path,
            name=name,
            headers={"X-Lab-Traffic": "normal"},
            allow_redirects=False,
            timeout=5,
        )

    @task(40)
    def home(self) -> None:
        self.visit("/")

    @task(25)
    def product(self) -> None:
        self.visit("/product/1")

    @task(20)
    def search(self) -> None:
        self.visit("/search?q=awd", name="/search")

    @task(10)
    def login_page(self) -> None:
        self.visit("/login")

    @task(3)
    def register_page(self) -> None:
        self.visit("/register")

    @task(2)
    def upload_page(self) -> None:
        self.visit("/upload")
