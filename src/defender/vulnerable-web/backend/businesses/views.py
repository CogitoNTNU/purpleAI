from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from users.permissions import IsAdmin, IsNotBanned

from .models import Business, BusinessClaim
from .permissions import IsOwnerOrReadOnly
from .serializers import BusinessClaimSerializer, BusinessSerializer


@extend_schema_view(list=extend_schema(tags=["Businesses"]))
class BusinessViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessSerializer
    queryset = Business.objects.select_related("owner")
    permission_classes = [IsOwnerOrReadOnly, IsNotBanned]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        category = self.request.query_params.get("category")
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(description__icontains=q)
        if category:
            qs = qs.filter(category=category)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def categories(self, request):
        categories = [
            {"value": choice[0], "label": choice[1]}
            for choice in Business.Category.choices
        ]
        return Response(categories)


    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def my_businesses(self, request):
        qs = self.get_queryset().filter(owner=request.user)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class BusinessClaimViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessClaimSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotBanned]
    queryset = BusinessClaim.objects.select_related("business", "claimant")

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return BusinessClaim.objects.none()
        if getattr(user, "role", "") == "admin":
            return BusinessClaim.objects.all()
        return BusinessClaim.objects.filter(claimant=user)

    def perform_create(self, serializer):
        user = self.request.user
        # Anyone can claim a business (to become a business owner)
        serializer.save(claimant=user)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        new_status = request.data.get("status")

        if not request.user.is_admin():
            raise PermissionDenied("Only admins can modify claim status.")

        if new_status not in BusinessClaim.Status.values:
            raise ValidationError(
                {"status": "Invalid status. Use 'approved' or 'rejected' or 'pending'."}
            )

        with transaction.atomic():
            instance.status = new_status
            if new_status == BusinessClaim.Status.APPROVED:
                instance.business.verified = True
                instance.business.save(update_fields=["verified"])
            instance.save(update_fields=["status"])

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)
