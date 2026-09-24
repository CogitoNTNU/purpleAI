from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ReplyViewSet, ReviewAttachmentViewSet, ReviewViewSet, VoteViewSet

router = DefaultRouter()

router.register("review", ReviewViewSet, basename="review")
router.register("replies", ReplyViewSet, basename="reply")
router.register("votes", VoteViewSet, basename="vote")
router.register("attachments", ReviewAttachmentViewSet, basename="attachment")

urlpatterns = [path("", include(router.urls))]
