from django.contrib import admin

from .models import Reply, Review, ReviewAttachment, Vote

admin.site.register(Review)
admin.site.register(Reply)
admin.site.register(Vote)
admin.site.register(ReviewAttachment)
