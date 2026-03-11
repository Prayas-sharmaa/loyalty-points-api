from django.core.management.base import BaseCommand
from loyalty.models import PointsRule


class Command(BaseCommand):
    help = "Seed default points rules"

    def handle(self, *args, **options):
        rules = [
            {"activity_code": "carbon_transport", "activity_name": "Carbon Tracking: Transport", "points_awarded": 20, "description": "Log transport emissions", "max_daily_claims": 5},
            {"activity_code": "carbon_electricity", "activity_name": "Carbon Tracking: Electricity", "points_awarded": 15, "description": "Log electricity usage", "max_daily_claims": 3},
            {"activity_code": "carbon_food", "activity_name": "Carbon Tracking: Food", "points_awarded": 10, "description": "Log food emissions", "max_daily_claims": 5},
            {"activity_code": "carbon_shopping", "activity_name": "Carbon Tracking: Shopping", "points_awarded": 10, "description": "Log shopping emissions", "max_daily_claims": 5},
            {"activity_code": "daily_login", "activity_name": "Daily Login Bonus", "points_awarded": 5, "description": "Login bonus", "max_daily_claims": 1},
            {"activity_code": "profile_complete", "activity_name": "Complete Profile", "points_awarded": 50, "description": "Fill all profile fields", "max_daily_claims": 1},
            {"activity_code": "referral", "activity_name": "Refer a Friend", "points_awarded": 100, "description": "Successful referral", "max_daily_claims": 3},
        ]

        created = 0
        for rule_data in rules:
            _, was_created = PointsRule.objects.update_or_create(
                activity_code=rule_data["activity_code"],
                defaults=rule_data,
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new rules ({len(rules)} total)"))