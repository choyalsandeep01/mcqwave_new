from django.contrib import admin
from django.urls import path, include
from pomegranate.views import pom_home,pom_overall,analysis_by_difficulty,accuracy_vs_tests,analysis_view_sub_acc,performance_radar_view,difficulty_vs_time_view,type_vs_time,diff_corr_incorr,type_corr_incorr,pom_sub_home,performance_analysis_view,custome_ana_view,test_wise_parti,pom_cus_cus,pom_cus_top_comp
from . import mobile_api_views
urlpatterns = [
    path('', pom_home,  name='pom_home' ),
    path('pomegranate_overall/', pom_overall, name='pom_overall'),

    path('pomegranate_overall/ana/', analysis_by_difficulty , name='analysis_by_difficulty'),
    path('pomegranate_overall/acc_test/', accuracy_vs_tests , name='accuracy_vs_tests'),
    path('pomegranate_overall/sub_acc/', analysis_view_sub_acc , name='analysis_view_sub_acc'),
    path('pomegranate_overall/radar/', performance_radar_view , name='performance_radar_view'),
    path('pomegranate_overall/diff_vs_time/', difficulty_vs_time_view , name='difficulty_vs_time_view'),
    path('pomegranate_overall/type_vs_time/', type_vs_time , name='type_vs_time'),
    path('pomegranate_overall/diff_corr_incorr/', diff_corr_incorr , name='diff_corr_incorr'),
    path('pomegranate_overall/type_corr_incorr/', type_corr_incorr , name='type_corr_incorr'),
    path('pomegranate_sub/', pom_sub_home , name='pom_sub_home'),
    path('pomegranate_sub/pom_sub_ana/', performance_analysis_view , name='pom_sub_ana'),
    path('custome_ana/', custome_ana_view , name='custome_ana_view'),
    path('custome_ana/test_wise_parti/', test_wise_parti , name='test_wise_parti'),
    path('custome_ana/pom_cus_cus/', pom_cus_cus , name='pom_cus_cus'),
    path('custome_ana/pom_cus_top_comp/', pom_cus_top_comp , name='pom_cus_top_comp'),
    
    path('api/analytics/unique-questions/', mobile_api_views.analytics_unique_questions, name='analytics_unique_questions'),
    path('api/analytics/subject-hierarchy/', mobile_api_views.analytics_subject_hierarchy, name='analytics_subject_hierarchy'),
    path('api/analytics/monthly-progress/', mobile_api_views.analytics_monthly_progress, name='analytics_monthly_progress'),
    path('api/analytics/clinical-performance/', mobile_api_views.analytics_clinical_performance, name='analytics_clinical_performance'),
    path('api/analytics/weakness-detection/', mobile_api_views.analytics_weakness_detection, name='analytics_weakness_detection'),
    path('api/analytics/difficulty-performance/', mobile_api_views.analytics_difficulty_performance, name='analytics_difficulty_performance'),

    path('api/analytics/overall-stats/', mobile_api_views.analytics_overall_stats, name='analytics_overall_stats'),
    path('api/analytics/pyq-overall-stats/', mobile_api_views.analytics_pyq_overall_stats, name='analytics_pyq_overall_stats'),
    path('api/analytics/pyq-exam-progress/', mobile_api_views.analytics_pyq_exam_progress, name='analytics_pyq_exam_progress'),
    path('api/analytics/pyq-subject-hierarchy/', mobile_api_views.analytics_pyq_subject_hierarchy, name='analytics_pyq_subject_hierarchy'),
    path('api/analytics/pyq-monthly-progress/', mobile_api_views.analytics_pyq_monthly_progress, name='analytics_pyq_monthly_progress'),
    path('api/analytics/pyq-clinical-performance/', mobile_api_views.analytics_pyq_clinical_performance, name='analytics_pyq_clinical_performance'),
    path('api/analytics/pyq-weakness-detection/', mobile_api_views.analytics_pyq_weakness_detection, name='analytics_pyq_weakness_detection'),
    path('api/analytics/pyq-difficulty-performance/', mobile_api_views.analytics_pyq_difficulty_performance, name='analytics_pyq_difficulty_performance'),
]