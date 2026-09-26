from businesses.models import Business
from django.contrib.auth import get_user_model
from django.db import models
from users.validators import FileValidator


class Review(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="reviews"
    )
    author = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.IntegerField()
    title = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField(blank=True, default="")
    ip_address = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if not 1 <= self.rating <= 5:
            raise ValidationError("Rating must be between 1 and 5")

    def __str__(self):
        return f"Review({self.rating}) for {self.business_id} by {self.author_id}"


class Reply(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="replies"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Vote(models.Model):
    owner = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="votes"
    )
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")
    is_helpful = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("owner", "review")


class Report(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    reason = models.TextField()
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


def review_attachment_path(instance, filename):
    return f"reviews/review/{instance.review.id}/{filename}"


class ReviewAttachment(models.Model):
    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(
        upload_to=review_attachment_path,
        validators=[
            FileValidator(
                allowed_mimetypes="",
                allowed_extensions="",
                max_size=1024 * 1024 * 10,
            )
        ],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
