
from django.contrib import admin
from django.urls import path, include
from home.views import home_view
from home.views import logout_view,mocktestdata
from .mobile_api_views import mobile_home_view, mobile_logout_view, mobile_mocktestdata,get_dashboard_data

urlpatterns = [
    path('', home_view,  name='home' ),
    path('logout/', logout_view, name='logout'),
    path('mocktestdata/', mocktestdata,  name='mocktestdata' ),


    # ✅ Mobile API URLs (following your pattern)
    path('api/mobile/home/', mobile_home_view, name='mobile_home'),
    path('api/mobile/home/<uuid:uuid>/', mobile_home_view, name='mobile_home_with_uuid'),
    path('api/mobile/logout/', mobile_logout_view, name='mobile_logout'),
    path('api/mobile/mocktestdata/', mobile_mocktestdata, name='mobile_mocktestdata'),
    path('api/dashboard_subs_pendind_sessions/', get_dashboard_data, name='dashboard_data'),


]

