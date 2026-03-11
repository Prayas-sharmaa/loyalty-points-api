from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Sum, Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema

from .models import PointsBalance, PointsTransaction, PointsRule
from .services import PointsService
from .serializers import (
    UserRegistrationSerializer,
    UserProfileSerializer,
    UserLoginSerializer,
    PointsBalanceSerializer,
    PointsTransactionSerializer,
    EarnPointsSerializer,
    RedeemPointsSerializer,
    TransferPointsSerializer,
    PointsRuleSerializer,
    EarnByRuleSerializer,
)

User = get_user_model()


# ==================== HEALTH ====================

@extend_schema(tags=["System"])
@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "healthy",
        "service": "loyalty-points-api",
        "version": "2.0.0",
        "timestamp": timezone.now().isoformat(),
    })


@extend_schema(tags=["System"])
@api_view(["GET"])
def api_stats(request):
    return Response({
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(is_loyalty_active=True).count(),
        "total_transactions": PointsTransaction.objects.count(),
        "total_points_in_circulation": PointsBalance.objects.aggregate(
            total=Sum("total_points")
        )["total"] or 0,
        "total_points_ever_earned": PointsBalance.objects.aggregate(
            total=Sum("lifetime_points")
        )["total"] or 0,
    })


# ==================== AUTH ====================

@extend_schema(tags=["Authentication"], request=UserRegistrationSerializer)
@api_view(["POST"])
def register(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        return Response(
            {
                "message": "User registered successfully",
                "user_id": str(user.id),
                "username": user.username,
                "tier": user.tier,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Authentication"], request=UserLoginSerializer)
@api_view(["POST"])
def login_view(request):
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user and user.is_loyalty_active:
            return Response({
                "message": "Login successful",
                "user_id": str(user.id),
                "username": user.username,
                "tier": user.tier,
            })
        return Response(
            {"error": "Invalid credentials or account inactive"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Authentication"])
@api_view(["GET"])
def user_profile(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = UserProfileSerializer(user)
    return Response(serializer.data)


# ==================== BALANCE ====================

@extend_schema(tags=["Balance"])
@api_view(["GET"])
def get_balance(request, user_id):
    try:
        balance = PointsBalance.objects.select_related("user").get(user_id=user_id)
    except PointsBalance.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    serializer = PointsBalanceSerializer(balance)
    return Response(serializer.data)


@extend_schema(tags=["Balance"])
@api_view(["GET"])
def user_summary(request, user_id):
    try:
        summary = PointsService.get_user_summary(user_id)
    except PointsBalance.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(summary)


# ==================== TRANSACTIONS ====================

@extend_schema(tags=["Transactions"])
@api_view(["GET"])
def get_transactions(request, user_id):
    txn_type = request.query_params.get("type")
    txn_status = request.query_params.get("status")
    limit = min(int(request.query_params.get("limit", 50)), 200)

    transactions = PointsTransaction.objects.filter(user_id=user_id)

    if txn_type:
        transactions = transactions.filter(transaction_type=txn_type)
    if txn_status:
        transactions = transactions.filter(status=txn_status)

    transactions = transactions[:limit]
    serializer = PointsTransactionSerializer(transactions, many=True)
    return Response(serializer.data)


# ==================== POINTS OPERATIONS ====================

@extend_schema(tags=["Points Operations"], request=EarnPointsSerializer)
@api_view(["POST"])
def earn_points(request):
    serializer = EarnPointsSerializer(data=request.data)
    if serializer.is_valid():
        try:
            txn, balance = PointsService.earn_points(
                user_id=serializer.validated_data["user_id"],
                points=serializer.validated_data["points"],
                description=serializer.validated_data.get("description", ""),
                reference_id=serializer.validated_data.get("reference_id", ""),
                source_service=serializer.validated_data.get("source_service", ""),
                metadata=serializer.validated_data.get("metadata", {}),
            )
            return Response({
                "message": f"{serializer.validated_data['points']} points earned",
                "transaction_id": str(txn.id),
                "total_points": balance.total_points,
                "lifetime_points": balance.lifetime_points,
                "tier": balance.user.tier,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Points Operations"], request=RedeemPointsSerializer)
@api_view(["POST"])
def redeem_points(request):
    serializer = RedeemPointsSerializer(data=request.data)
    if serializer.is_valid():
        try:
            txn, balance = PointsService.redeem_points(
                user_id=serializer.validated_data["user_id"],
                points=serializer.validated_data["points"],
                description=serializer.validated_data.get("description", ""),
                reference_id=serializer.validated_data.get("reference_id", ""),
                source_service=serializer.validated_data.get("source_service", ""),
            )
            return Response({
                "message": f"{serializer.validated_data['points']} points redeemed",
                "transaction_id": str(txn.id),
                "total_points": balance.total_points,
            })
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Points Operations"], request=TransferPointsSerializer)
@api_view(["POST"])
def transfer_points(request):
    serializer = TransferPointsSerializer(data=request.data)
    if serializer.is_valid():
        try:
            txn_out, txn_in, from_bal, to_bal = PointsService.transfer_points(
                from_user_id=serializer.validated_data["from_user_id"],
                to_user_id=serializer.validated_data["to_user_id"],
                points=serializer.validated_data["points"],
                description=serializer.validated_data.get("description", "Points transfer"),
            )
            return Response({
                "message": f"{serializer.validated_data['points']} points transferred",
                "from_balance": from_bal.total_points,
                "to_balance": to_bal.total_points,
            })
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== RULES ====================

@extend_schema(tags=["Points Rules"])
@api_view(["GET"])
def list_rules(request):
    rules = PointsRule.objects.filter(is_active=True)
    serializer = PointsRuleSerializer(rules, many=True)
    return Response(serializer.data)


@extend_schema(tags=["Points Rules"], request=EarnByRuleSerializer)
@api_view(["POST"])
def earn_by_rule(request):
    serializer = EarnByRuleSerializer(data=request.data)
    if serializer.is_valid():
        try:
            txn, balance = PointsService.earn_by_rule(
                user_id=serializer.validated_data["user_id"],
                activity_code=serializer.validated_data["activity_code"],
                reference_id=serializer.validated_data.get("reference_id", ""),
                source_service=serializer.validated_data.get("source_service", ""),
                metadata=serializer.validated_data.get("metadata", {}),
            )
            return Response({
                "message": f"Points earned for activity: {serializer.validated_data['activity_code']}",
                "points_earned": txn.points,
                "transaction_id": str(txn.id),
                "total_points": balance.total_points,
                "tier": balance.user.tier,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==================== ADMIN OPERATIONS ====================

@extend_schema(tags=["Admin"])
@api_view(["POST"])
def expire_points(request):
    count = PointsService.expire_old_points()
    return Response({"message": f"{count} points expired", "points_expired": count})


@extend_schema(tags=["Admin"])
@api_view(["GET"])
def leaderboard(request):
    limit = min(int(request.query_params.get("limit", 10)), 50)
    top_users = PointsBalance.objects.select_related("user").order_by(
        "-lifetime_points"
    )[:limit]
    return Response([
        {
            "rank": idx + 1,
            "username": b.user.username,
            "full_name": b.user.full_name,
            "tier": b.user.tier,
            "total_points": b.total_points,
            "lifetime_points": b.lifetime_points,
        }
        for idx, b in enumerate(top_users)
    ])