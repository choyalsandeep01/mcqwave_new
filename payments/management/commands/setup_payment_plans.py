# Create this file: payments/management/commands/debug_plans.py

from django.core.management.base import BaseCommand
from payments.models import PaymentPlan

class Command(BaseCommand):
    help = 'Debug payment plans and create sample data if needed'

    def handle(self, *args, **options):
        self.stdout.write("=== Payment Plans Debug ===")
        
        # Check existing plans
        plans = PaymentPlan.objects.all()
        self.stdout.write(f"Total plans in database: {plans.count()}")
        
        for plan in plans:
            self.stdout.write(f"Plan ID: {plan.id}, Name: {plan.name}, Active: {plan.is_active}")
        
        active_plans = PaymentPlan.objects.filter(is_active=True)
        self.stdout.write(f"Active plans: {active_plans.count()}")
        
        # Create sample plans if none exist
        if not active_plans.exists():
            self.stdout.write("Creating sample payment plans...")
            
            # Basic Plan
            basic_plan = PaymentPlan.objects.create(
                name="Basic Plan",
                plan_type="basic",
                price=1.00,
                duration_days=30,
                description="Perfect for getting started",
                features=[
                    "Basic features",
                    "Email support",
                    "30-day access"
                ],
                is_active=True
            )
            
            # Premium Plan
            premium_plan = PaymentPlan.objects.create(
                name="Premium Plan",
                plan_type="premium",
                price=5.00,
                duration_days=90,
                description="Most popular choice",
                features=[
                    "All basic features",
                    "Priority support",
                    "Advanced analytics",
                    "90-day access"
                ],
                is_active=True
            )
            
            # Pro Plan
            pro_plan = PaymentPlan.objects.create(
                name="Professional Plan",
                plan_type="pro",
                price=10.00,
                duration_days=365,
                description="For serious users",
                features=[
                    "All premium features",
                    "24/7 phone support",
                    "Custom integrations",
                    "1-year access",
                    "Priority feature requests"
                ],
                is_active=True
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created 3 sample plans')
            )
            
            # Display created plans
            for plan in [basic_plan, premium_plan, pro_plan]:
                self.stdout.write(f"Created: ID={plan.id}, Name={plan.name}, Price=₹{plan.price}")
        
        self.stdout.write("=== Debug Complete ===")