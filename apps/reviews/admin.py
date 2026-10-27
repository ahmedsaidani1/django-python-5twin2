from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("carrier", "author", "rating", "sentiment", "sentiment_confidence", "created_at")
    list_filter = ("rating", "sentiment")
    search_fields = ("comment", "carrier__username", "author__username")
    list_select_related = ("carrier", "author")
