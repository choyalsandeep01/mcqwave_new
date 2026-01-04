from django.contrib import admin
from django.urls import path, include
from .views import mock_tests_view, start_mock_test,take_mock_test, submit_answer,submit_test, update_timer, mock_test_result,mock_sessions_list,mark_question_visible,top_performers_view,top_performers_api,start_mock_practice
from . import  mobile_api_views

urlpatterns = [
        path('', mock_tests_view, name="mocktest_home" ),
        path('<str:test_uid>/start/', start_mock_test, name='start_mock_test'),

        path('session/<str:session_uid>/', take_mock_test, name='take_mock_test'),
        path('session/<str:session_uid>/submit/', submit_test, name='submit_test'),
        path('session/<str:session_uid>/answer/', submit_answer, name='submit_answer'),
        path('session/<str:session_uid>/timer/', update_timer, name='update_timer'),
        
        # Results path
        path('result/<str:session_uid>/', mock_test_result, name='mock_test_result'),
        path('review_mock_sessions_home/', mock_sessions_list, name='mock_sessions_list'),
        path('session/<str:session_uid>/question/visible/', mark_question_visible, name='mark_question_visible'),
        path('top_performers/', top_performers_view, name='top_performers_view'),
        path('api/top_performers/', top_performers_api, name='top_performers_api'),
        path('api/mocktest/practice/', start_mock_practice, name='mobile_mocktest_practice_api'),

        # Results path
        path('api/<str:test_uid>/start/', mobile_api_views.start_mock_test, name='start_mock_test_api'),

        path('take/<str:session_uid>/<str:email_token>/', mobile_api_views.take_mock_test, name='take_mock_test_api'),
        path('api/', mobile_api_views.mock_tests_api_view, name='mock_tests_api_view'),


         # Mobile API endpoints
        path('submit-answer/<str:session_uid>/', mobile_api_views.submit_answer, name='mobile_submit_answer'),
        path('mark-visible/<str:session_uid>/', mobile_api_views.mark_question_visible, name='mobile_mark_visible'),
        path('update-timer/<str:session_uid>/', mobile_api_views.update_timer, name='mobile_update_timer'),
        path('submit-test/<str:session_uid>/', mobile_api_views.submit_test, name='mobile_submit_test'),
        path('result/<str:session_uid>/', mobile_api_views.mock_test_result, name='mobile_mock_result'),
        path('sessions/<str:email_token>/', mobile_api_views.mock_sessions_list, name='mobile_mock_sessions'),
        path('start-practice/', mobile_api_views.mobile_start_mock_practice, name='mobile_start_practice'),
        path('api/check-current-mock-practice/', mobile_api_views.api_check_current_mock_practice, name='api_check_current_mock_practice'),
        path('api/mock-test-result/<uuid:session_uid>/', mobile_api_views.api_mock_test_result, name='api_mock_test_result'),
        path('api/mock/review/', mobile_api_views.review_mock_data, name='review_mock_data'),
        path('api/mock/session/<uuid:session_uid>/status/', mobile_api_views.check_session_status, name='check_session_status'),
        path('api/check-mock-access/', mobile_api_views.check_mock_access, name='check_mock_access'),
]      