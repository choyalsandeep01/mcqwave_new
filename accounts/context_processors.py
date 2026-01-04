# In accounts/context_processors.py
# In accounts/context_processors.py - add this import at the top
from payments.models import UserSubscription
from django.utils import timezone
def user_subscription_context(request):
    context = {}
    
    if request.user.is_authenticated:
        # Get user profile
        try:
            user_profile = request.user.userprofile  # Adjust field name as needed
            context['user_profile'] = user_profile
        except:
            context['user_profile'] = None
        
        # Get active subscriptions
        active_subscriptions = UserSubscription.objects.filter(
            user=request.user,
            is_active=True,
            end_date__gt=timezone.now()
        )
        context['active_subscriptions'] = active_subscriptions
    else:
        context['user_profile'] = None
        context['active_subscriptions'] = None
    
    return context