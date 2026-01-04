from django.urls import path
from . import views,mobile_api_views

app_name = 'payments'

urlpatterns = [
    # Main plans page
    path('plans/', views.payment_plans, name='plans'),
    
    # Payment initiation - Fixed the name to match JavaScript
    path('initiate/', views.initiate_payment, name='initiate'),
    
    # Payment callbacks - IMPORTANT: These must match your PayU dashboard settings
    path('success/', views.payment_success, name='success'),
    path('failure/', views.payment_failure, name='failure'),
    path('bolt-response/', views.bolt_response, name='bolt_response'),  # ADD THIS

    # Status check - Fixed the name to match JavaScript
    path('status/<str:transaction_id>/', views.check_payment_status, name='status'),

    path('api/mobile/payment/plans/', 
         mobile_api_views.get_payment_plans, 
         name='mobile_payment_plans'),
    
    path('api/mobile/payment/initiate/', 
         mobile_api_views.initiate_mobile_payment, 
         name='mobile_initiate_payment'),
    
    path('api/mobile/payment/status/<str:transaction_id>/', 
         mobile_api_views.check_mobile_payment_status, 
         name='mobile_payment_status'),
    
    path('api/mobile/payment/subscriptions/', 
         mobile_api_views.get_user_subscriptions, 
         name='mobile_user_subscriptions'),
    
    # Mobile PayU Callbacks (PayU will POST to these)
    path('mobile/success/', 
         mobile_api_views.mobile_payment_success, 
         name='mobile_payment_success'),
    
    path('mobile/failure/', 
         mobile_api_views.mobile_payment_failure, 
         name='mobile_payment_failure'),
     ]
