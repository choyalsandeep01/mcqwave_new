from django.contrib import admin
from django.urls import path, include
from accounts.views import sign_up, log_in, activate_email,password_reset_request,password_reset_confirm,resend_email,landing,get_mcq_stats,profile_settings,medical_colleges_api,update_medical_college
from home.views import home_view
from .mobile_api_views import mobile_login, mobile_signup, mobile_medical_colleges, mobile_app_stats,check_app_version,submit_contact_form,get_user_contacts

urlpatterns = [
    path('', landing, name='landing' ),

    path('signup/', sign_up, name='signup' ),
    path('login/', log_in, name='login' ),
    path('accounts/activate/<email_token>/' , activate_email , name="activate_email"),
    path('<uuid:uuid>/', home_view, name='go_to_home'),
    path('login/password-reset/', password_reset_request, name='password_reset_request'),
    path('password-reset-confirm/<str:token>/', password_reset_confirm, name='password_reset_confirm'),
    path('resend_email/', resend_email, name='resend_email'),
    path('mcq-stats/', get_mcq_stats, name='get_mcq_stats' ),
    path('/setting/', profile_settings, name='setting' ),
    path('api/medical-colleges/', medical_colleges_api, name='medical_colleges_api'),
    path('update-medical-college/', update_medical_college, name='update_medical_college'),


    path('api/mobile/login/', mobile_login, name='mobile_login'),
    path('api/mobile/signup/', mobile_signup, name='mobile_signup'),
    path('api/mobile/medical-colleges/', mobile_medical_colleges, name='mobile_medical_colleges'),
    path('api/mobile/app-stats/', mobile_app_stats, name='mobile_app_stats'),
    path('api/check-version/', check_app_version, name='check_app_version'),
    path('api/mobile/contact/', submit_contact_form, name='mobile_contact'),
    path('api/mobile/contact/history/', get_user_contacts, name='contact_history'),
]
