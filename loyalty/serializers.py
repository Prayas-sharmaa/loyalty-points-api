from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import PointsBalance, PointsTransaction, PointsRule

User = get_user_model()


# ===== User Serializers =====

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "date_of_birth", "password", "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        if data["password"] != data.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        if User.objects.filter(email=data["email"]).exists():
            raise serializers.ValidationError({"email": "Email already registered."})
        return data

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        PointsBalance.objects.create(user=user)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    tier = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "date_of_birth", "tier", "full_name", "balance",
            "is_loyalty_active", "created_at",
        ]
        read_only_fields = ["id", "username", "created_at"]

    def get_balance(self, obj):
        try:
            bal = obj.points_balance
            return {
                "total_points": bal.total_points,
                "lifetime_points": bal.lifetime_points,
                "points_redeemed": bal.points_redeemed,
            }
        except PointsBalance.DoesNotExist:
            return None


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


# ===== Points Serializers =====

class PointsBalanceSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    tier = serializers.CharField(source="user.tier", read_only=True)

    class Meta:
        model = PointsBalance
        fields = [
            "username", "email", "tier", "total_points", "lifetime_points",
            "points_redeemed", "points_expired", "last_earn_date",
            "last_redeem_date", "updated_at",
        ]


class PointsTransactionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = PointsTransaction
        fields = [
            "id", "username", "transaction_type", "status", "points",
            "balance_after", "description", "reference_id", "source_service",
            "metadata", "created_at", "expires_at", "is_expired",
        ]


class EarnPointsSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    points = serializers.IntegerField(min_value=1, max_value=100000)
    description = serializers.CharField(required=False, default="", max_length=500)
    reference_id = serializers.CharField(required=False, default="", max_length=200)
    source_service = serializers.CharField(required=False, default="", max_length=100)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value, is_loyalty_active=True).exists():
            raise serializers.ValidationError("Active user not found.")
        return value

    def validate_reference_id(self, value):
        if value and PointsTransaction.objects.filter(
            reference_id=value, status="completed"
        ).exists():
            raise serializers.ValidationError("Duplicate reference_id. Transaction already processed.")
        return value


class RedeemPointsSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    points = serializers.IntegerField(min_value=1, max_value=100000)
    description = serializers.CharField(required=False, default="", max_length=500)
    reference_id = serializers.CharField(required=False, default="", max_length=200)
    source_service = serializers.CharField(required=False, default="", max_length=100)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value, is_loyalty_active=True).exists():
            raise serializers.ValidationError("Active user not found.")
        return value

    def validate(self, data):
        try:
            balance = PointsBalance.objects.get(user_id=data["user_id"])
            if balance.total_points < data["points"]:
                raise serializers.ValidationError({
                    "points": f"Insufficient balance. Available: {balance.total_points}"
                })
        except PointsBalance.DoesNotExist:
            raise serializers.ValidationError({"user_id": "User balance not found."})
        return data


class TransferPointsSerializer(serializers.Serializer):
    from_user_id = serializers.UUIDField()
    to_user_id = serializers.UUIDField()
    points = serializers.IntegerField(min_value=1, max_value=50000)
    description = serializers.CharField(required=False, default="Points transfer")

    def validate(self, data):
        if data["from_user_id"] == data["to_user_id"]:
            raise serializers.ValidationError("Cannot transfer to yourself.")

        for field in ["from_user_id", "to_user_id"]:
            if not User.objects.filter(id=data[field], is_loyalty_active=True).exists():
                raise serializers.ValidationError({field: "Active user not found."})

        try:
            balance = PointsBalance.objects.get(user_id=data["from_user_id"])
            if balance.total_points < data["points"]:
                raise serializers.ValidationError({
                    "points": f"Insufficient balance. Available: {balance.total_points}"
                })
        except PointsBalance.DoesNotExist:
            raise serializers.ValidationError({"from_user_id": "Sender balance not found."})

        return data


# ===== Rules Serializers =====

class PointsRuleSerializer(serializers.ModelSerializer):
    effective_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = PointsRule
        fields = [
            "id", "activity_code", "activity_name", "points_awarded",
            "description", "is_active", "max_daily_claims", "multiplier",
            "effective_points", "created_at", "updated_at",
        ]


class EarnByRuleSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    activity_code = serializers.CharField(max_length=50)
    reference_id = serializers.CharField(required=False, default="", max_length=200)
    source_service = serializers.CharField(required=False, default="", max_length=100)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value, is_loyalty_active=True).exists():
            raise serializers.ValidationError("Active user not found.")
        return value

    def validate_activity_code(self, value):
        if not PointsRule.objects.filter(activity_code=value, is_active=True).exists():
            raise serializers.ValidationError(f"No active rule for activity: {value}")
        return value

    def validate(self, data):
        rule = PointsRule.objects.get(activity_code=data["activity_code"])
        if rule.max_daily_claims > 0:
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = PointsTransaction.objects.filter(
                user_id=data["user_id"],
                reference_id__startswith=f"rule:{data['activity_code']}",
                created_at__gte=today_start,
                status="completed",
            ).count()
            if today_count >= rule.max_daily_claims:
                raise serializers.ValidationError({
                    "activity_code": f"Daily limit ({rule.max_daily_claims}) reached for this activity."
                })
        return data