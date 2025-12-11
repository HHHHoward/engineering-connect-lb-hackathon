from locust import HttpUser, TaskSet, task, between

class LoadBalancerUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def get_main(self):
        self.client.get("/")

    def get_health(self):
        self.client.get("/health")