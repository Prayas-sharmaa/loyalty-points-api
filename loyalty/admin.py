from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, PointsBalance, PointsTransaction, PointsRule


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "is_loyalty_active", "created_at"]
    list_filter = ["is_loyalty_active", "is_staff", "created_at"]
    search_fields = ["username", "email", "first_name", "last_name"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Loyalty Info", {"fields": ("phone", "date_of_birth", "is_loyalty_active")}),
    )


@admin.register(PointsBalance)
class PointsBalanceAdmin(admin.ModelAdmin):
    list_display = ["user", "total_points", "lifetime_points", "points_redeemed", "points_expired", "updated_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["updated_at"]


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ["user", "transaction_type", "status", "points", "balance_after", "created_at"]
    list_filter = ["transaction_type", "status", "created_at"]
    search_fields = ["user__username", "reference_id", "description"]
    readonly_fields = ["id", "created_at"]


@admin.register(PointsRule)
class PointsRuleAdmin(admin.ModelAdmin):
    list_display = ["activity_code", "activity_name", "points_awarded", "multiplier", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["activity_code", "activity_name"]