from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class Business(models.Model):
    class Category(models.TextChoices):
        ENTERTAINMENT = "entertainment", "Entertainment"
        RESTAURANTS_AND_BARS = "restaurants_bars", "Restaurants and bars"
        FASHION = "fashion", "Fashion"
        ELECTRONIC = "electronic", "Electronic"

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="owned_businesses",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.ENTERTAINMENT,
    )
    address = models.CharField(max_length=512, blank=True, default="")
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Business"
        verbose_name_plural = "Businesses"

    def __str__(self):
        return self.name


class BusinessClaim(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="claims"
    )
    claimant = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="claims"
    )
    statement = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Business Claim"
        verbose_name_plural = "Business Claims"
        constraints = [
            models.UniqueConstraint(
                fields=["business", "claimant", "status"],
                condition=models.Q(status="pending"),
                name="unique_pending_claim_per_user",
            )
        ]

    def __str__(self):
        return f"{self.claimant} → {self.business} ({self.status})"
