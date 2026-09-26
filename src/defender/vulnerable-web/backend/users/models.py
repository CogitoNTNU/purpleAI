from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Roles(models.TextChoices):
        REVIEWER = "reviewer", "Reviewer"
        BUSINESS = "business_owner", "Business Owner"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=20, choices=Roles.choices, default=Roles.REVIEWER
    )
    is_banned = models.BooleanField(default=False)
    ssn = models.BigIntegerField(null=True, blank=True)

    def full_name(self):
        return super().get_full_name()

    def is_business_owner(self):
        return self.role == self.Roles.BUSINESS

    def is_admin(self):
        return self.role == self.Roles.ADMIN
