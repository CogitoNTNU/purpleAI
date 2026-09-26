from businesses.models import Business
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Reply, Review, ReviewAttachment, Vote


class ReviewAttachmentSerializer(serializers.ModelSerializer):
    review = serializers.PrimaryKeyRelatedField(queryset=Review.objects.all())
    file_url = serializers.SerializerMethodField(read_only=True)
    file_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ReviewAttachment
        fields = ["id", "file", "file_url", "file_name", "review", "uploaded_at"]
        read_only_fields = ["uploaded_at"]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_file_name(self, obj):
        if obj.file:
            return obj.file.name.split("/")[-1]
        return None


class ReplySerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())
    author_username = serializers.SerializerMethodField(read_only=True)
    review = serializers.PrimaryKeyRelatedField(queryset=Review.objects.all())

    class Meta:
        model = Reply
        fields = ["id", "author", "author_username", "review", "body", "created_at"]
        read_only_fields = ["created_at"]

    def get_author_username(self, obj):
        return getattr(obj.author, "username", None)


class VoteSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())
    review = serializers.PrimaryKeyRelatedField(queryset=Review.objects.all())

    class Meta:
        model = Vote
        fields = ["id", "owner", "review", "is_helpful", "created_at"]
        read_only_fields = ["created_at"]


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all())
    author_username = serializers.SerializerMethodField(read_only=True)
    business = serializers.PrimaryKeyRelatedField(queryset=Business.objects.all())
    attachments = ReviewAttachmentSerializer(many=True, required=False, read_only=True)
    replies = ReplySerializer(many=True, required=False, read_only=True)
    helpful_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "author",
            "author_username",
            "business",
            "rating",
            "title",
            "body",
            "ip_address",
            "helpful_count",
            "attachments",
            "replies",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_author_username(self, obj):
        return getattr(obj.author, "username", None)

    def get_helpful_count(self, obj):
        try:
            return obj.votes.filter(is_helpful=True).count()
        except Exception:
            return 0

    def create(self, validated_data):
        attachments_data = validated_data.pop("attachments", [])
        replies_data = validated_data.pop("replies", [])
        review = Review.objects.create(**validated_data)

        for att in attachments_data:
            ReviewAttachment.objects.create(review=review, file=att.get("file"))

        for rep in replies_data:
            Reply.objects.create(
                review=review,
                author=rep.get("author"),
                body=rep.get("body", ""),
            )
        return review

    def update(self, instance, validated_data):
        instance.rating = validated_data.get("rating", instance.rating)
        instance.title = validated_data.get("title", instance.title)
        instance.body = validated_data.get("body", instance.body)
        instance.ip_address = validated_data.get("ip_address", instance.ip_address)
        instance.save()
        return instance
