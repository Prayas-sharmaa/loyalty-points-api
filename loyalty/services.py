from django.db import transaction
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.conf import settings
from .models import PointsBalance, PointsTransaction, PointsRule


class PointsService:
    """Core business logic for all points operations."""

    @staticmethod
    @transaction.atomic
    def earn_points(user_id, points, description="", reference_id="",
                    source_service="", metadata=None):
        """Award points to a user. Returns the transaction."""
        balance = PointsBalance.objects.select_for_update().get(user_id=user_id)

        balance.total_points += points
        balance.lifetime_points += points
        balance.last_earn_date = timezone.now()
        balance.save()

        expiry_months = getattr(settings, "POINTS_EXPIRY_MONTHS", 12)

        txn = PointsTransaction.objects.create(
            user_id=user_id,
            transaction_type="earn",
            status="completed",
            points=points,
            balance_after=balance.total_points,
            description=description,
            reference_id=reference_id,
            source_service=source_service,
            metadata=metadata or {},
            expires_at=timezone.now() + relativedelta(months=expiry_months),
        )
        return txn, balance

    @staticmethod
    @transaction.atomic
    def redeem_points(user_id, points, description="", reference_id="",
                      source_service=""):
        """Deduct points from a user. Returns the transaction."""
        balance = PointsBalance.objects.select_for_update().get(user_id=user_id)

        if balance.total_points < points:
            raise ValueError(f"Insufficient balance. Available: {balance.total_points}")

        balance.total_points -= points
        balance.points_redeemed += points
        balance.last_redeem_date = timezone.now()
        balance.save()

        txn = PointsTransaction.objects.create(
            user_id=user_id,
            transaction_type="redeem",
            status="completed",
            points=-points,
            balance_after=balance.total_points,
            description=description,
            reference_id=reference_id,
            source_service=source_service,
        )
        return txn, balance

    @staticmethod
    @transaction.atomic
    def transfer_points(from_user_id, to_user_id, points, description="Points transfer"):
        """Transfer points between two users. Returns both transactions."""
        from_balance = PointsBalance.objects.select_for_update().get(user_id=from_user_id)
        to_balance = PointsBalance.objects.select_for_update().get(user_id=to_user_id)

        if from_balance.total_points < points:
            raise ValueError(f"Insufficient balance. Available: {from_balance.total_points}")

        # Deduct from sender
        from_balance.total_points -= points
        from_balance.save()

        # Add to receiver
        to_balance.total_points += points
        to_balance.lifetime_points += points
        to_balance.last_earn_date = timezone.now()
        to_balance.save()

        ref = f"transfer-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        txn_out = PointsTransaction.objects.create(
            user_id=from_user_id,
            transaction_type="transfer_out",
            status="completed",
            points=-points,
            balance_after=from_balance.total_points,
            description=f"{description} (to {to_balance.user.username})",
            reference_id=ref,
        )

        txn_in = PointsTransaction.objects.create(
            user_id=to_user_id,
            transaction_type="transfer_in",
            status="completed",
            points=points,
            balance_after=to_balance.total_points,
            description=f"{description} (from {from_balance.user.username})",
            reference_id=ref,
        )

        return txn_out, txn_in, from_balance, to_balance

    @staticmethod
    @transaction.atomic
    def earn_by_rule(user_id, activity_code, reference_id="",
                     source_service="", metadata=None):
        """Earn points based on a configured rule."""
        rule = PointsRule.objects.get(activity_code=activity_code, is_active=True)
        points = rule.effective_points

        return PointsService.earn_points(
            user_id=user_id,
            points=points,
            description=f"Activity: {rule.activity_name}",
            reference_id=reference_id or f"rule:{activity_code}:{timezone.now().timestamp():.0f}",
            source_service=source_service,
            metadata={**(metadata or {}), "rule": activity_code, "multiplier": str(rule.multiplier)},
        )

    @staticmethod
    @transaction.atomic
    def expire_old_points():
        """Expire all earn transactions past their expiry date. Returns count expired."""
        now = timezone.now()
        expired_txns = PointsTransaction.objects.filter(
            transaction_type="earn",
            status="completed",
            expires_at__lte=now,
        ).exclude(
            reference_id__in=PointsTransaction.objects.filter(
                transaction_type="expire"
            ).values_list("reference_id", flat=True)
        )

        total_expired = 0
        for txn in expired_txns:
            try:
                balance = PointsBalance.objects.select_for_update().get(user_id=txn.user_id)
                expire_amount = min(txn.points, balance.total_points)
                if expire_amount <= 0:
                    continue

                balance.total_points -= expire_amount
                balance.points_expired += expire_amount
                balance.save()

                PointsTransaction.objects.create(
                    user_id=txn.user_id,
                    transaction_type="expire",
                    status="completed",
                    points=-expire_amount,
                    balance_after=balance.total_points,
                    description=f"Points expired from transaction {txn.id}",
                    reference_id=f"expire:{txn.id}",
                )
                total_expired += expire_amount
            except PointsBalance.DoesNotExist:
                continue

        return total_expired

    @staticmethod
    def get_user_summary(user_id):
        """Get complete summary for a user."""
        balance = PointsBalance.objects.select_related("user").get(user_id=user_id)
        recent_txns = PointsTransaction.objects.filter(user_id=user_id)[:10]

        return {
            "user": {
                "id": str(balance.user.id),
                "username": balance.user.username,
                "email": balance.user.email,
                "full_name": balance.user.full_name,
                "tier": balance.user.tier,
            },
            "balance": {
                "total_points": balance.total_points,
                "lifetime_points": balance.lifetime_points,
                "points_redeemed": balance.points_redeemed,
                "points_expired": balance.points_expired,
            },
            "recent_transactions": [
                {
                    "id": str(t.id),
                    "type": t.transaction_type,
                    "points": t.points,
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                }
                for t in recent_txns
            ],
        }