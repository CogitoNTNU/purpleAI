from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BusinessClaimViewSet, BusinessViewSet

router = DefaultRouter()
router.register("claims", BusinessClaimViewSet, basename="business-claim")
router.register("", BusinessViewSet, basename="business")

urlpatterns = [path("", include(router.urls))]
