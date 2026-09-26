from django.contrib.auth import get_user_model
from django.db import connection
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .permissions import IsAdmin, IsCurrentUser, IsReadOnly, IsNotBanned
from .serializers import (
    UserCreateSerializer,
    UserDetailSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsCurrentUser | IsReadOnly | IsAdmin,
        IsNotBanned,
    ]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        if self.action == "retrieve":
            return UserDetailSerializer
        return UserSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or (hasattr(user, "role") and user.role == "admin"):
            return get_user_model().objects.all()
        return get_user_model().objects.filter(id=user.id)

    def get_permissions(self):
        if self.action in ["create"]:
            return [permissions.AllowAny()]
        if self.action in ["toggle_active", "toggle_ban", "detail", "user_detail"]:
            return [permissions.IsAuthenticated()]
        if self.action in ["destroy"]:
            return [IsAdmin()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def toggle_active(self, request, pk=None):
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        return Response(
            {"status": "success", "is_active": user.is_active},
            status=200,
        )

    @action(detail=True, methods=["post"])
    def toggle_ban(self, request, pk=None):
        user = self.get_object()
        user.is_banned = not user.is_banned
        user.save()
        return Response(
            {"status": "success", "is_banned": user.is_banned},
            status=200,
        )

    @action(detail=False, methods=["get"], url_path=r"username/(?P<username>[^/.]+)")
    def user_detail(self, request, username=None):
        query = f"SELECT * FROM users_user WHERE username = '{username}'"
        with connection.cursor() as cursor:
            cursor.execute(query)
            cols = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        if not rows:
            return Response({"error": "User not found"}, status=404)

        objs = []
        for row in rows:
            data = dict(zip(cols, row))
            objs.append(get_user_model()(**data))

        if len(objs) == 1:
            serializer = UserDetailSerializer(objs[0], context={"request": request})
        else:
            serializer = UserDetailSerializer(
                objs, many=True, context={"request": request}
            )
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def update_password(self, request):
        user = request.user
        new_password = request.data.get("new_password")
        if not new_password:
            return Response({"error": "New password required"}, status=400)

        user.set_password(new_password)
        user.save()
        return Response({"status": "Password updated successfully"})
