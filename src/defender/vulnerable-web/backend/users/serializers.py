from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "is_banned",
            "email",
            "role",
        ]


class UserDetailSerializer(UserSerializer):

    class Meta(UserSerializer.Meta):
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "is_banned",
            "ssn",
            "email",
            "role",
        ]


class UserUpdateSerializer(UserSerializer):

    class Meta(UserSerializer.Meta):
        fields = ["username", "first_name", "last_name", "ssn", "role"]


class UserCreateSerializer(UserSerializer):
    password = serializers.CharField(write_only=True)
    password1 = serializers.CharField(write_only=True)

    class Meta(UserSerializer.Meta):
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "ssn",
            "password",
            "password1",
        ]

    def validate(self, data):
        if data.get("password") != data.get("password1"):
            raise serializers.ValidationError({"password": "Passwords must match."})

        try:
            password_validation.validate_password(data.get("password"))
        except Exception as err:
            raise serializers.ValidationError({"password": list(err.messages)})

        return data

    def create(self, validated_data):
        validated_data.pop("password1", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
