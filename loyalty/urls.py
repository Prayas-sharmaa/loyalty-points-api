from django.urls import path
from . import views

urlpatterns = [
    # System
    path("health/", views.health_check, name="health-check"),
    path("stats/", views.api_stats, name="api-stats"),

    # Auth
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("users/<uuid:user_id>/", views.user_profile, name="user-profile"),

    # Balance
    path("balance/<uuid:user_id>/", views.get_balance, name="get-balance"),
    path("summary/<uuid:user_id>/", views.user_summary, name="user-summary"),

    # Transactions
    path("transactions/<uuid:user_id>/", views.get_transactions, name="get-transactions"),

    # Points Operations
    path("earn/", views.earn_points, name="earn-points"),
    path("redeem/", views.redeem_points, name="redeem-points"),
    path("transfer/", views.transfer_points, name="transfer-points"),

    # Rules
    path("rules/", views.list_rules, name="list-rules"),
    path("earn-by-rule/", views.earn_by_rule, name="earn-by-rule"),

    # Admin
    path("admin/expire/", views.expire_points, name="expire-points"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
]