import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.conf import settings


class User(AbstractUser):
    """Extended user model with loyalty-specific fields."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_loyalty_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def tier(self):
        """Calculate user tier based on lifetime points."""
        try:
            lifetime = self.points_balance.lifetime_points
        except PointsBalance.DoesNotExist:
            lifetime = 0

        thresholds = settings.POINTS_TIER_THRESHOLDS
        current_tier = "bronze"
        for tier_name, threshold in sorted(thresholds.items(), key=lambda x: x[1]):
            if lifetime >= threshold:
                current_tier = tier_name
        return current_tier


class PointsBalance(models.Model):
    """Tracks current and lifetime points for each user."""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="points_balance"
    )
    total_points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    lifetime_points = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    points_redeemed = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    points_expired = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    last_earn_date = models.DateTimeField(null=True, blank=True)
    last_redeem_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "points_balances"
        verbose_name_plural = "Points Balances"

    def __str__(self):
        return f"{self.user.username}: {self.total_points} pts (lifetime: {self.lifetime_points})"


class PointsTransaction(models.Model):
    """Immutable log of every points operation."""
    TRANSACTION_TYPES = [
        ("earn", "Earn"),
        ("redeem", "Redeem"),
        ("expire", "Expire"),
        ("adjust", "Adjustment"),
        ("bonus", "Bonus"),
        ("transfer_in", "Transfer In"),
        ("transfer_out", "Transfer Out"),
    ]

    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("pending", "Pending"),
        ("failed", "Failed"),
        ("reversed", "Reversed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transactions"
    )
    transaction_type = models.CharField(max_length=15, choices=TRANSACTION_TYPES, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="completed")
    points = models.IntegerField(help_text="Positive for earn, negative for redeem/expire")
    balance_after = models.IntegerField(help_text="User's balance after this transaction")
    description = models.TextField(blank=True)
    reference_id = models.CharField(max_length=200, blank=True, db_index=True)
    source_service = models.CharField(max_length=100, blank=True, help_text="Which service triggered this")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "points_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["transaction_type", "status"]),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.transaction_type} {self.points:+d} pts [{self.status}]"

    @property
    def is_expired(self):
        if self.expires_at and self.transaction_type == "earn":
            return timezone.now() >= self.expires_at
        return False


class PointsRule(models.Model):
    """Configurable rules for earning points per activity."""
    activity_code = models.CharField(max_length=50, unique=True)
    activity_name = models.CharField(max_length=100)
    points_awarded = models.IntegerField(validators=[MinValueValidator(1)])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    max_daily_claims = models.IntegerField(default=0, help_text="0 = unlimited")
    multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "points_rules"
        ordering = ["activity_code"]

    def __str__(self):
        return f"{self.activity_code}: {self.points_awarded} pts (x{self.multiplier})"

    @property
    def effective_points(self):
        return int(self.points_awarded * self.multiplier)