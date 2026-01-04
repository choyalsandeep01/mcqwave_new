
from django.contrib import admin
from django.urls import path, include
from . import views
from . import mobile_api_views
urlpatterns = [
    path('', views.pyq_selection_view, name='pyq_selection'),
    path('get-filtered-mcqs/', views.get_filtered_mcqs, name='get_filtered_mcqs'),
    path('pyq-count/', views.get_pyq_count, name='get_pyq_count'),
    path('continue-test/<str:test_id>/', views.pyq_continue_test, name='pyq_continue_test'),
    path('analytics-report/', views.generate_mcq_analytics_report, name='mcq_analytics_report'),
    path('test-filtering/', views.test_filtering_accuracy, name='test_filtering_accuracy'),
    path('analytics/', views.pyq_analytics, name='pyq_analytics'),
    path('analytics-data/', views.analytics_data, name='analytics_data'),

    path('api/selection-data/', mobile_api_views.pyq_selection_data, name='pyq_selection_data'),
    path('api/start-practice/', mobile_api_views.start_pyq_practice, name='start_pyq_practice'),
    path('api/count/', mobile_api_views.get_pyq_count_api, name='get_pyq_count_api'),
    path('api/continue/<str:test_id>/', mobile_api_views.continue_pyq_test_api, name='continue_pyq_test_api'),
    path('api/check-current-test/', mobile_api_views.check_current_pyq_test, name='check_current_pyq_test'),
    path('api/validate-exam-selection/', mobile_api_views.validate_exam_selection, name='validate_exam_selection'),


    
]
