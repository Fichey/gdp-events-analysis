"""
Performance tests using Locust.
Run headless: locust -f locustfile.py --headless -u 20 -r 5 --run-time 60s --host http://localhost:8000
"""
from locust import HttpUser, task, between


class ApiUser(HttpUser):
    wait_time = between(0.5, 2)

    @task(3)
    def health_check(self):
        self.client.get("/health", name="/health")

    @task(5)
    def list_countries(self):
        self.client.get("/api/v1/gdp/countries", name="/gdp/countries")

    @task(5)
    def list_event_types(self):
        self.client.get("/api/v1/events/types", name="/events/types")

    @task(4)
    def get_gdp_poland(self):
        self.client.get("/api/v1/gdp/POL?year_start=2015&year_end=2023", name="/gdp/{country}")

    @task(4)
    def get_gdp_usa(self):
        self.client.get("/api/v1/gdp/USA?year_start=2015&year_end=2023", name="/gdp/{country}")

    @task(3)
    def get_events_poland(self):
        self.client.get("/api/v1/events/POL?year_start=2015&year_end=2023", name="/events/{country}")

    @task(3)
    def get_events_with_filter(self):
        self.client.get(
            "/api/v1/events/DEU?event_type=PROTEST&year_start=2015&year_end=2023",
            name="/events/{country}?type=PROTEST",
        )

    @task(2)
    def get_correlations(self):
        self.client.get("/api/v1/analysis/correlations?country_code=POL", name="/analysis/correlations")

    @task(1)
    def get_summary(self):
        self.client.get("/api/v1/analysis/summary", name="/analysis/summary")
