from django.contrib import admin
from django.urls import path, include
from hive.views import hive_home,send_connection_request,handle_connection_request,share_bookmark,share_test,shared,start_shared_test,test_session_details,shared_test_status,get_test_status,continue_test,review_test
urlpatterns = [
    path('', hive_home,  name='hive_home' ),
    path('connect/', send_connection_request, name='send_connection_request'),
    path('handle-connection-request/', handle_connection_request, name='handle_connection_request'),
    path('share-bookmark/<str:bookmark_id>/', share_bookmark, name='share_bookmark'),
    path('share-test/<str:test_id>/', share_test, name='share_test'),
    path('shared/<str:userId>/', shared, name='shared'),
    path('start_shared_test/<str:test_id>/', start_shared_test, name='start_shared_test'),
    path('test-session-details/<str:test_id>/', test_session_details, name='test_session_details'),
    path('shared-test-status/<str:st_uid>/', shared_test_status, name='shared_test_status'),
    path('get-test-status/<str:st_uid>/', get_test_status, name='get_test_status'),
    path('review-test/<str:test_id>/', review_test, name='review_test'),
    path('continue-test/<str:test_id>/', continue_test, name='continue_test'),


]
