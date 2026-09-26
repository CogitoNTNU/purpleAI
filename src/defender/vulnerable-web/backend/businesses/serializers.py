from django.db.models import Avg
from rest_framework import serializers

from .models import Business, BusinessClaim


class BusinessSerializer(serializers.ModelSerializer):
    owner_username = serializers.ReadOnlyField(source="owner.username")
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id",
            "owner",
            "owner_username",
            "name",
            "description",
            "category",
            "address",
            "verified",
            "average_rating",
            "created_at",
        ]
        read_only_fields = ["created_at", "average_rating", "owner_username"]

    def get_average_rating(self, obj):
        return obj.reviews.aggregate(avg=Avg("rating"))["avg"] or 0.0


class BusinessClaimSerializer(serializers.ModelSerializer):
    business_name = serializers.ReadOnlyField(source="business.name")
    claimant_username = serializers.ReadOnlyField(source="claimant.username")

    class Meta:
        model = BusinessClaim
        fields = [
            "id",
            "business",
            "business_name",
            "claimant",
            "claimant_username",
            "statement",
            "status",
            "created_at",
        ]
        read_only_fields = ["claimant", "status", "created_at"]
