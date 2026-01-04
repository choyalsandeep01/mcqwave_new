from django.urls import path
from . import views

app_name = 'flashcards'

urlpatterns = [
    # Home Screen
    path('api/home/', views.flashcard_home, name='flashcard_home'),
    
    # Browse Screen
    path('api/browse/', views.flashcard_browse, name='flashcard_browse'),
    path('api/topic/<uuid:topic_id>/flashcards/', views.topic_flashcards, name='topic_flashcards'),
    
    # Study Screen
    path('api/study/start/', views.start_study_session, name='start_study_session'),
    path('api/flashcard/<uuid:card_id>/rate/', views.rate_flashcard, name='rate_flashcard'),
    path('api/flashcard/<uuid:card_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
    path('api/flashcard/<uuid:card_id>/note/', views.add_note, name='add_note'),
    path('api/study/session/<uuid:session_id>/end/', views.end_study_session, name='end_study_session'),
    
    # Analytics Screen
    path('api/analytics/', views.flashcard_analytics, name='flashcard_analytics'),
    path('api/bookmarks/', views.get_bookmarks_hierarchy, name='get_bookmarks'),
    path('api/flashcard-access/', views.check_flashcard_access, name='check_flashcard_access'),

]
