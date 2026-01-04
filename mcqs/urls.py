
from django.contrib import admin
from django.urls import path, include
from mcqs.views import cus_mcq,test,submit_quiz,save_answer,continue_test,submitted_active,cont_last_sess,analysis_by_difficulty,accuracy_vs_tests,analysis_view_sub_acc,performance_radar_view,difficulty_vs_time_view,type_vs_time,diff_corr_incorr,type_corr_incorr,rev_test_home,test_review,tea,toggle_bookmark,bookmarks_home,delete_bookmark,qod,submit_mcq_feedback,mcq2,faqs,comingsoon,plans,rev_test_pom
from .mobile_api_views import mobile_cus_mcq, mobile_test, mobile_qod, mobile_submit_mcq_feedback, mobile_toggle_bookmark, mobile_bookmarks_home, mobile_delete_bookmark,api_submit_quiz,api_save_answer,api_submitted_active,api_continue_test_mobile,api_check_current_test,get_test_sessions,get_test_session_detail,get_continue_sessions,check_mcq_access


urlpatterns = [
    path('', cus_mcq,  name='mcq' ),
    
    path('test/', test,  name='test' ),
    
    path('submit_quiz/', submit_quiz, name='submit_quiz'),
    path('save-answer/', save_answer, name='save_ans'),
    path('restest/<test_id>', continue_test, name='cont'),
    path('submitted_active/', submitted_active, name='submitted_active'),
    path('cont_last_sess/', cont_last_sess , name='cont_last_sess'),
    path('ana/', analysis_by_difficulty , name='analysis_by_difficulty'),
    path('acc_test/', accuracy_vs_tests , name='accuracy_vs_tests'),
    path('sub_acc/', analysis_view_sub_acc , name='analysis_view_sub_acc'),
    path('radar/', performance_radar_view , name='performance_radar_view'),
    path('diff_vs_time/', difficulty_vs_time_view , name='difficulty_vs_time_view'),
    path('type_vs_time/', type_vs_time , name='type_vs_time'),
    path('diff_corr_incorr/', diff_corr_incorr , name='diff_corr_incorr'),
    path('type_corr_incorr/', type_corr_incorr , name='type_corr_incorr'),
    path('rev_test_home/', rev_test_home , name='rev_test_home'),
    path('rev_test_home/rev_test/', test_review, name='test_review'),
    path('rev_test_home/rev_test/rev_test_pom/', rev_test_pom, name='rev_test_pom'),
    path('tea/', tea, name='tea'),
    path('toggle-bookmark/', toggle_bookmark, name='toggle_bookmark'),
    path('bookmarks/', bookmarks_home, name='bookmarks'),
    path('delete-bookmark/<str:bkmk_id>/', delete_bookmark, name='delete_bookmark'),
    path('qod/', qod, name='qod'),
    path('feedback/', submit_mcq_feedback, name='mcq_feedback'),
    path('mcq2/', mcq2, name='mcq2'),
    path('faqs/', faqs, name='faqs'),
    path('comingsoon/', comingsoon, name='comingsoon'),
    path('plans/', plans, name='plans'),

    # ✅ Mobile API URLs (following your pattern)
    path('api/mobile/mcqs/', mobile_cus_mcq, name='mobile_mcq'),
    path('api/mobile/test/', mobile_test, name='mobile_test'),
    path('api/mobile/qod/', mobile_qod, name='mobile_qod'),
    path('api/mobile/feedback/', mobile_submit_mcq_feedback, name='mobile_mcq_feedback'),
    path('api/mobile/bookmarks/', mobile_bookmarks_home, name='mobile_bookmarks'),
    path('api/mobile/delete-bookmark/<str:bkmk_id>/', mobile_delete_bookmark, name='mobile_delete_bookmark'),
    path('api/toggle-bookmark/', mobile_toggle_bookmark, name='api_toggle_bookmark'),

    path('api/submit_quiz/', api_submit_quiz, name='api_submit_quiz'),
    path('api/save-answer/', api_save_answer, name='api_save_ans'),
    path('api/submitted_active/', api_submitted_active, name='api_submitted_active'),
    path('api/continue-test/<str:test_id>/', api_continue_test_mobile, name='api_continue_test_mobile'),
    path('api/current-test/', api_check_current_test, name='api_check_current_test'),
    path('api/test-sessions/', get_test_sessions, name='get_test_sessions'),
    path('api/test-session/<str:test_id>/detail/', get_test_session_detail, name='get_test_session_detail'),
    path('api/continue-sessions/', get_continue_sessions, name='get_continue_sessions'),
    path('api/check-mcq-access/', check_mcq_access, name='check_mcq_access'),

]                      

