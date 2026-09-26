from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from users.permissions import IsAdmin, IsNotBanned

from .models import Reply, Report, Review, ReviewAttachment, Vote
from .permissions import IsAuthor
from .serializers import (
    ReplySerializer,
    ReviewAttachmentSerializer,
    ReviewSerializer,
    VoteSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List or filter reviews"),
    retrieve=extend_schema(summary="Get a specific review"),
    create=extend_schema(summary="Create a new review"),
)
class ReviewViewSet(viewsets.ModelViewSet):

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsNotBanned]
    filter_backends = [filters.OrderingFilter]

    ordering_fields = ["created_at", "rating"]

    def get_queryset(self):
        qs = Review.objects.select_related("author", "business").prefetch_related(
            "votes", "replies", "attachments"
        )
        params = self.request.query_params

        # Filter by business
        business = params.get("business")
        if business:
            qs = qs.filter(business_id=business)

        # Filter by author ID
        author = params.get("author")
        if author:
            qs = qs.filter(author_id=author)

        # Keyword search
        q = params.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))

        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        review = serializer.save(author=self.request.user)
        review.clean()  # ensure rating is 1–5

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def report(self, request, pk=None):
        review = self.get_object()
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response(
                {"error": "Reason is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        Report.objects.create(review=review, reporter=request.user, reason=reason)
        return Response(
            {"detail": "Reported successfully."}, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["get"], permission_classes=[IsAdmin])
    def reports(self, request):
        reports = (
            Report.objects.filter(resolved=False)
            .select_related("review", "review__author", "review__business", "reporter")
            .values(
                "id",
                "review__id",
                "review__title",
                "review__body",
                "review__business__id",
                "review__business__name",
                "review__author__id",
                "review__author__username",
                "reporter__username",
                "reason",
                "created_at",
            )
        )
        return Response(list(reports))

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def resolve_report(self, request, pk=None):
        try:
            report = Report.objects.get(pk=pk)
        except Report.DoesNotExist:
            return Response(
                {"error": "Report not found."}, status=status.HTTP_404_NOT_FOUND
            )

        report.resolved = True
        report.save()
        return Response({"detail": "Report resolved."}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="List replies"),
    create=extend_schema(summary="Create reply"),
)
class ReplyViewSet(viewsets.ModelViewSet):
    queryset = Reply.objects.select_related("author", "review")
    serializer_class = ReplySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsNotBanned]

    def perform_create(self, serializer):
        review = serializer.validated_data["review"]
        user = self.request.user
        if not (review.business.owner == user):
            raise PermissionDenied("Only the business owner can reply to reviews.")

        reply = serializer.save(author=self.request.user)
        return reply


@extend_schema_view(
    list=extend_schema(summary="List votes"),
    create=extend_schema(summary="Create or update vote"),
)
class VoteViewSet(
    viewsets.GenericViewSet,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
):
    queryset = Vote.objects.select_related("owner", "review")
    serializer_class = VoteSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsNotBanned]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner = serializer.validated_data["owner"]
        review = serializer.validated_data["review"]

        existing_vote = Vote.objects.filter(owner=owner, review=review).first()

        if existing_vote:
            existing_vote.delete()
            return Response({"detail": "Vote removed"}, status=status.HTTP_200_OK)

        vote = Vote.objects.create(
            owner=owner,
            review=review,
            is_helpful=serializer.validated_data.get("is_helpful", True),
        )

        response_serializer = self.get_serializer(vote)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(summary="List review attachments"),
    create=extend_schema(summary="Upload review attachment"),
)
class ReviewAttachmentViewSet(viewsets.ModelViewSet):
    queryset = ReviewAttachment.objects.select_related("review")
    serializer_class = ReviewAttachmentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
