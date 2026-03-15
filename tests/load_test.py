import random
from locust import HttpUser, task, between

POPULAR_LINKS = [f"load{i}" for i in range(100,110)]

class ShortLinkUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(6)
    def redirect_to_original(self):
        alias = random.choice(POPULAR_LINKS)
        self.client.get(f"/links/{alias}", name="/redirect", allow_redirects=False)

    @task(4)
    def create_short_link(self):
        alias = f"loadtest{random.randint(10000, 99999)}"
        self.client.post(
            "/links/shorten",
            json={"original_url": "https://example.com", "custom_alias": alias},
            name="/create")

    @task(1)
    def get_stats(self):
        alias = random.choice(POPULAR_LINKS)
        self.client.get(f"/links/{alias}/stats", name="/stats")