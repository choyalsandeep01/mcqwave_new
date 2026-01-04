from django.db import models
from django.contrib.auth.models import User
from base.models import BaseModel
import uuid
from decimal import Decimal
import logging

# Add logger at the module level
logger = logging.getLogger(__name__)
class PaymentPlan(BaseModel):
    """Different subscription plans for various exam categories"""
    
    # Plan Categories
    PLAN_CATEGORIES = [
        ('neet_pg_inicet', 'NEET PG + INICET'),
        ('fmge', 'FMGE'),
        ('upsc_cms', 'UPSC CMS'),
    ]
    
    # Plan Duration Types
    PLAN_TYPES = [
        ('monthly', '1 Month Plan'),
        ('quarterly', '3 Months Plan'),
        ('half_yearly', '6 Months Plan'),
        ('yearly', '12 Months Plan'),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=PLAN_CATEGORIES, default='neet_pg_inicet')
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField()  # Plan duration in days
    description = models.TextField()
    features = models.JSONField(default=list)  # List of features
    is_active = models.BooleanField(default=True)
    is_most_popular = models.BooleanField(default=False)  # Mark most popular plans
    is_best_value = models.BooleanField(default=False)    # Mark best value plans
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # Discount %
    
    class Meta:
        unique_together = ['category', 'plan_type']  # Ensure unique combination
        ordering = ['category', 'duration_days']
    
    def __str__(self):
        return f"{self.get_category_display()} - {self.get_plan_type_display()} - ₹{self.price}"
    
    @property
    def monthly_price(self):
        """Calculate monthly price based on duration"""
        # Add null safety checks
        if self.price is None or self.duration_days is None:
            return 0
        
        try:
            price = float(self.price)
            duration_days = int(self.duration_days)
            
            if duration_days <= 0:
                return 0
            
            if duration_days <= 30:
                return price
            elif duration_days <= 90:  # 3 months
                return price / 3
            elif duration_days <= 180:  # 6 months
                return price / 6
            else:  # 12 months
                return price / 12
        except (TypeError, ValueError, ZeroDivisionError):
            return 0
    
    @property
    def savings_text(self):
        """Generate savings text for display"""
        # Add null safety check
        if self.discount_percentage is None:
            return ""
        
        try:
            discount = float(self.discount_percentage)
            if discount > 0:
                return f"save ~{discount}%"
            return ""
        except (TypeError, ValueError):
            return ""

class PaymentTransaction(BaseModel):
    """Store all payment transactions"""
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHODS = [
        ('card', 'Credit/Debit Card'),
        ('netbanking', 'Net Banking'),
        ('upi', 'UPI'),
        ('wallet', 'Digital Wallet'),
        ('emi', 'EMI'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    payu_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    gateway_response = models.JSONField(default=dict)  # Store gateway response
    failure_reason = models.TextField(blank=True, null=True)
    
    # PayU specific fields
    mihpayid = models.CharField(max_length=100, blank=True, null=True)
    mode = models.CharField(max_length=50, blank=True, null=True)
    bank_ref_num = models.CharField(max_length=100, blank=True, null=True)
    bankcode = models.CharField(max_length=10, blank=True, null=True)
    payment_initiated = models.BooleanField(default=False)  # Track if payment was initiated
    payment_url_accessed = models.BooleanField(default=False)  # Track if URL was accessed
    payment_session_id = models.CharField(max_length=100, blank=True, null=True)  # Session tracking
    one_time_token = models.CharField(max_length=100, blank=True, null=True)  # One-time use token
    expires_at = models.DateTimeField(blank=True, null=True)  # Payment URL expiry
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['mihpayid'], 
                condition=models.Q(status='success'),
                name='unique_successful_mihpayid'
            )
    ]
    def is_payment_allowed(self):
        """Check if payment is allowed for this transaction"""
        from django.utils import timezone
        
        # Don't allow if already completed
        if self.status in ['success', 'failed', 'cancelled']:
            return False
            
        # Don't allow if expired
        if self.expires_at and timezone.now() > self.expires_at:
            return False
            
        # Don't allow if URL was already accessed and failed/cancelled
        if self.payment_url_accessed and self.status in ['failed', 'cancelled']:
            return False
            
        return True
    
    def mark_payment_initiated(self, session_id=None):
        """Mark payment as initiated"""
        self.payment_initiated = True
        self.payment_session_id = session_id
        self.save()
    
    def mark_url_accessed(self):
        """Mark payment URL as accessed"""
        self.payment_url_accessed = True
        self.save()
    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.status}"
    


class UserSubscription(BaseModel):
    """Track user subscriptions - now supports multiple subscriptions per user"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE)
    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    auto_renewal = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['user', 'plan']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save to ensure only one active subscription per user per category"""
        if self.is_active:
            # Deactivate other subscriptions for the same user and category
            UserSubscription.objects.filter(
                user=self.user,
                plan__category=self.plan.category,
                is_active=True
            ).exclude(uid=self.uid if hasattr(self, 'uid') else None).update(is_active=False)
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name} ({self.plan.get_category_display()})"
    
    @property
    def is_expired(self):
        from django.utils import timezone
        if self.end_date is None:
            return True
        try:
            return timezone.now() > self.end_date
        except TypeError:
            return True
    
    @property
    def days_remaining(self):
        from django.utils import timezone
        
        if self.end_date is None:
            return 0
            
        try:
            if self.is_expired:
                return 0
            
            current_time = timezone.now()
            # Handle timezone-aware comparison
            if hasattr(self.end_date, 'date'):
                end_date = self.end_date.date()
                current_date = current_time.date()
            else:
                end_date = self.end_date
                current_date = current_time.date()
            
            delta = end_date - current_date
            return max(0, delta.days)
        except (TypeError, AttributeError):
            return 0
    
    @classmethod
    def get_user_subscription_for_category(cls, user, category):
        """Get active subscription for a specific category"""
        try:
            return cls.objects.get(
                user=user,
                plan__category=category,
                is_active=True
            )
        except cls.DoesNotExist:
            return None
        except cls.MultipleObjectsReturned:
            # In case of multiple active subscriptions for same category (shouldn't happen with unique constraint)
            return cls.objects.filter(
                user=user,
                plan__category=category,
                is_active=True
            ).order_by('-end_date').first()
    
    @classmethod
    def get_all_active_subscriptions(cls, user):
        """Get all active subscriptions for a user"""
        return cls.objects.filter(
            user=user,
            is_active=True
        ).select_related('plan')
    
        
    @classmethod
    def create_or_extend_subscription(cls, user, new_transaction):
        """
        ENHANCED: Create new subscription or extend existing one ONLY if same category
        Different categories will create separate subscriptions
        """
        from django.utils import timezone
        from datetime import timedelta
        from django.db import transaction
        
        new_plan = new_transaction.plan
        category = new_plan.category
        
        logger.info(f"Processing subscription for user: {user.username}, category: {category}")
        logger.info(f"New plan: {new_plan.name} ({new_plan.get_plan_type_display()})")
        
        # Use database transaction to ensure consistency
        with transaction.atomic():
            # Try to get existing active subscription for THIS SPECIFIC CATEGORY
            existing_subscription = cls.get_user_subscription_for_category(user, category)
            
            if existing_subscription:
                logger.info(f"Found existing subscription for category {category}")
                logger.info(f"Existing subscription ends: {existing_subscription.end_date}, "
                        f"Days remaining: {existing_subscription.days_remaining}, "
                        f"Is expired: {existing_subscription.is_expired}")
                
                # Extend existing subscription for the SAME CATEGORY
                existing_subscription.extend_subscription(new_transaction)
                return existing_subscription
            else:
                logger.info(f"No existing subscription found for category {category}, creating new one")
                
                # Create NEW subscription for this category
                current_time = timezone.now()
                new_subscription = cls.objects.create(
                    user=user,
                    plan=new_plan,
                    transaction=new_transaction,
                    start_date=current_time,
                    end_date=current_time + timedelta(days=new_plan.duration_days),
                    is_active=True
                )
                
                logger.info(f"Created new subscription for {category}: "
                        f"Start: {new_subscription.start_date}, "
                        f"End: {new_subscription.end_date}, "
                        f"Duration: {new_plan.duration_days} days")
                
                return new_subscription

    def extend_subscription(self, new_transaction):
        """ENHANCED: Extend current subscription with new transaction - ONLY if same category"""
        from django.utils import timezone
        from datetime import timedelta
        
        # Safety check: Only extend if categories match
        if self.plan.category != new_transaction.plan.category:
            error_msg = (f"Category mismatch! Current subscription category: {self.plan.category}, "
                        f"New transaction category: {new_transaction.plan.category}. "
                        f"Cannot extend subscription across different categories.")
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Extending subscription {getattr(self, 'uid', 'unknown')} for category: {self.plan.category}")
        logger.info(f"Current subscription: {self.plan.name} -> New plan: {new_transaction.plan.name}")
        
        # Store original details for logging
        original_end_date = self.end_date
        original_plan = self.plan.name
        
        # Update transaction reference to the latest one
        self.transaction = new_transaction
        
        # Calculate new end date
        current_time = timezone.now()
        
        if self.end_date and self.end_date > current_time:
            # Subscription is still active, extend from current end_date
            logger.info(f"Extending active subscription. Current end date: {self.end_date}")
            new_end_date = self.end_date + timedelta(days=new_transaction.plan.duration_days)
            # Keep the original start_date
        else:
            # Subscription has expired, start fresh from now
            logger.info(f"Renewing expired subscription. Previous end date: {self.end_date}")
            self.start_date = current_time
            new_end_date = current_time + timedelta(days=new_transaction.plan.duration_days)
        
        # Update subscription details (but keep the same category plan)
        self.plan = new_transaction.plan  # Update to new plan (same category)
        self.end_date = new_end_date
        self.is_active = True
        
        logger.info(f"Subscription extended successfully:")
        logger.info(f"  Original plan: {original_plan} -> New plan: {self.plan.name}")
        logger.info(f"  Original end date: {original_end_date} -> New end date: {self.end_date}")
        logger.info(f"  Total days added: {new_transaction.plan.duration_days}")
        logger.info(f"  New days remaining: {self.days_remaining}")
        
        self.save()
        return self
    
    def renew_subscription(self, new_transaction):
        """
        Deprecated: Use extend_subscription instead
        Keeping for backward compatibility
        """
        return self.extend_subscription(new_transaction)

class ActivePlanConfiguration(BaseModel):
    """Configuration to control which plans are actively shown to users"""
    plan = models.OneToOneField(PaymentPlan, on_delete=models.CASCADE, related_name='active_config')
    is_visible = models.BooleanField(default=True)  # Show/hide plan from users
    display_order = models.PositiveIntegerField(default=0)  # Order in which plans appear
    custom_badge_text = models.CharField(max_length=50, blank=True, null=True)  # Custom badge like "Limited Time"
    promotional_text = models.CharField(max_length=200, blank=True, null=True)  # Additional promotional text
    
    class Meta:
        ordering = ['plan__category', 'display_order']
    
    def __str__(self):
        return f"{self.plan.name} - {'Visible' if self.is_visible else 'Hidden'}"

# Helper class for managing user subscriptions
class UserSubscriptionManager:
    """Helper class to manage user subscriptions across different categories"""
    
    @staticmethod
    def get_subscription_summary(user):
        """Get summary of all user subscriptions"""
        subscriptions = UserSubscription.get_all_active_subscriptions(user)
        
        summary = {}
        for subscription in subscriptions:
            category = subscription.plan.category
            summary[category] = {
                'subscription': subscription,
                'plan_name': subscription.plan.name,
                'category_display': subscription.plan.get_category_display(),
                'end_date': subscription.end_date,
                'days_remaining': subscription.days_remaining,
                'is_expired': subscription.is_expired,
            }
        
        return summary
    
    @staticmethod
    def has_active_subscription_for_category(user, category):
        """Check if user has active subscription for specific category"""
        subscription = UserSubscription.get_user_subscription_for_category(user, category)
        return subscription and subscription.is_active and not subscription.is_expired
    
    @staticmethod
    def process_new_subscription(user, transaction):
        """Process new subscription - either create or extend based on category"""
        return UserSubscription.create_or_extend_subscription(user, transaction)