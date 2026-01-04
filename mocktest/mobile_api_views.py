import json
import logging
import uuid
from datetime import datetime
import traceback  # ✅ ADD THIS LINE
from django.db.models import Prefetch

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q, Sum
from django.db.models.functions import Concat, Extract
from django.db.models import Value
from django.db import models
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import uuid
import logging
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication
from .models import (
    MockTestCategory, MockTest, MockSession, MockAnswer, 
    MockTestMCQ
)
from mcqs.models import TestSession, TestAnswer
from mcqs.serializers import MCQSerializer

logger = logging.getLogger(__name__)

def format_seconds_to_time(seconds):
    """Helper function to format seconds into HH:MM:SS format"""
    if not seconds:
        return "00:00:00"
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def check_user_subscription_for_mocktest(user, mock_test_category):
    """
    Smart subscription validation for mock tests
    Maps mock test categories to subscription plan categories
    
    Args:
        user: Django User object
        mock_test_category: MockTest category name from MOCK_TEST_CATEGORIES
        
    Returns:
        tuple: (is_allowed: bool, error_message: str)
    """
    from payments.models import UserSubscription
    
    try:
        # Get all active subscriptions for the user
        active_subscriptions = UserSubscription.get_all_active_subscriptions(user)
        
        if not active_subscriptions.exists():
            return False, "You don't have any active subscription. Please upgrade to access mock tests."
        
        # Get active subscription categories (not expired)
        active_categories = set()
        for sub in active_subscriptions:
            if not sub.is_expired:
                active_categories.add(sub.plan.category)
        
        if not active_categories:
            return False, "Your subscription has expired. Please renew to access mock tests."
        
        # Smart mapping between mock test categories and subscription plan categories
        category_mapping = {
            'NEET-PG Pattern': ('neet_pg_inicet', 'NEET-PG + INI-CET'),
            'INI-CET': ('neet_pg_inicet', 'NEET-PG + INI-CET'),
            'FMGE': ('fmge', 'FMGE'),
            'UPSC-CMS': ('upsc_cms', 'UPSC-CMS'),
        }

        # Get the mapping for the current mock test category
        mapping = category_mapping.get(mock_test_category)
        
        if not mapping:
            logger.warning(f"Unknown mock test category: '{mock_test_category}'")
            return False, f"Unknown mock test category: {mock_test_category}. Please contact support."
        
        required_category, category_display = mapping
        
        # Check if user has the required subscription
        if required_category not in active_categories:
            # Get user's current subscriptions for better error message
            user_categories = [
                sub.plan.get_category_display() 
                for sub in active_subscriptions 
                if not sub.is_expired
            ]
            
            if user_categories:
                current_subs = ", ".join(user_categories)
                error_msg = (f"You have {current_subs} subscription(s), but you need an active "
                           f"{category_display} subscription to access this mock test. "
                           f"Please upgrade your plan.")
            else:
                error_msg = (f"You need an active {category_display} subscription to access "
                           f"this mock test. Please upgrade your plan.")
            
            return False, error_msg
        
        logger.info(f"User {user.username} has valid {category_display} subscription for mock test category: {mock_test_category}")
        return True, ""
        
    except Exception as e:
        logger.error(f"Error checking mock test subscription: {str(e)}", exc_info=True)
        return False, "Unable to verify subscription. Please try again or contact support."

def check_user_subscription_for_mocktest_practice(user, mcq_count):
    """
    Check if user can start mock test practice based on:
    1. Available free MCQs, OR
    2. Any active subscription (regardless of category)
    
    Args:
        user: Django User object
        mcq_count: Number of MCQs in the mock test
        
    Returns:
        tuple: (is_allowed: bool, error_message: str, use_free_mcqs: bool)
    """
    from payments.models import UserSubscription
    
    try:
        profile = user.profile
        
        # Check if user has free MCQs remaining
        if hasattr(profile, 'free_mcqs_remaining') and profile.free_mcqs_remaining >= mcq_count:
            logger.info(f"User {user.username} can practice using free MCQs. "
                       f"Remaining: {profile.free_mcqs_remaining}, Required: {mcq_count}")
            return True, "", True
        
        # Check if user has ANY active subscription (regardless of category)
        active_subscriptions = UserSubscription.get_all_active_subscriptions(user)
        
        if not active_subscriptions.exists():
            remaining_mcqs = getattr(profile, 'free_mcqs_remaining', 0)
            if remaining_mcqs > 0:
                error_msg = f"You need {mcq_count} free MCQs but only have {remaining_mcqs} remaining. Please upgrade to any plan for unlimited practice."
                return False, error_msg, False
            else:
                error_msg = "You have no free attempts left and no active subscription. Please upgrade to any plan for unlimited mock test practice."
                return False, error_msg, False
        
        # Check if any subscription is not expired
        active_non_expired_subs = []
        for sub in active_subscriptions:
            if not sub.is_expired:
                active_non_expired_subs.append(sub)
        
        if not active_non_expired_subs:
            remaining_mcqs = getattr(profile, 'free_mcqs_remaining', 0)
            if remaining_mcqs >= mcq_count:
                return True, "", True
            elif remaining_mcqs > 0:
                error_msg = f"Your subscription has expired. You need {mcq_count} free MCQs but only have {remaining_mcqs} remaining."
                return False, error_msg, False
            else:
                error_msg = "Your subscription has expired and you have no free attempts left. Please renew your subscription."
                return False, error_msg, False
        
        # User has active subscription - unlimited practice
        sub_names = [sub.plan.get_category_display() for sub in active_non_expired_subs]
        logger.info(f"User {user.username} can practice with unlimited access. "
                   f"Active subscriptions: {', '.join(sub_names)}")
        return True, "", False
        
    except Exception as e:
        logger.error(f"Error checking mock test practice permission: {str(e)}", exc_info=True)
        error_msg = "Unable to verify your access. Please try again or contact support."
        return False, error_msg, False

def get_required_subscription_display(mock_test_category):
    """
    Get user-friendly subscription name for mock test category
    """
    category_mapping = {
        'NEET-PG Pattern': 'NEET-PG + INI-CET',
        'INI-CET': 'NEET-PG + INI-CET',
        'FMGE': 'FMGE',
        'UPSC-CMS': 'UPSC-CMS',
    }
    return category_mapping.get(mock_test_category, 'Unknown')

@login_required(login_url='/login')
@require_http_methods(["GET"])
def mock_tests_api_view(request):
    """
    API view to return mock test categories and tests data for React Native app
    """
    try:
        # Get all active categories with their tests
        categories = MockTestCategory.objects.prefetch_related(
            'mock_tests__subjects'
        ).all()
        
        current_time = timezone.now()
        
        categories_data = []
        for category in categories:
            # Get category icon based on name
            icon_name = 'stethoscope'
            if 'NEET' in category.get_name_display():
                icon_name = 'stethoscope'
            elif 'INI' in category.get_name_display():
                icon_name = 'hospital'
            elif 'FMGE' in category.get_name_display():
                icon_name = 'user-md'
            else:
                icon_name = 'book-medical'
            
            # Get all tests for this category
            tests_data = []
            for test in category.mock_tests.all():
                # Calculate test status
                status = 'upcoming'
                if current_time >= test.start_time and current_time <= test.end_time:
                    status = 'live'
                elif current_time > test.end_time:
                    status = 'completed'
                
                # Calculate time remaining
                time_remaining = None
                if status == 'upcoming':
                    diff = test.start_time - current_time
                    days = diff.days
                    hours = diff.seconds // 3600
                    time_remaining = f"Starts in {days}d {hours}h"
                elif status == 'live':
                    diff = test.end_time - current_time
                    hours = diff.seconds // 3600
                    minutes = (diff.seconds % 3600) // 60
                    time_remaining = f"{hours}h {minutes}m remaining"
                else:
                    time_remaining = "Test ended"
                
                # Get subjects list
                subjects_list = list(test.subjects.values_list('name', flat=True))
                
                test_data = {
                    'uid': str(test.uid),
                    'title': test.title,
                    'description': test.description or 'No description available',
                    'test_type': test.test_type,
                    'test_type_display': test.get_test_type_display(),
                    'start_time': test.start_time.isoformat(),
                    'end_time': test.end_time.isoformat(),
                    'time_limit_minutes': test.time_limit_minutes,
                    'total_mcqs': test.total_mcqs,
                    'percent_easy': test.percent_easy,
                    'percent_medium': test.percent_medium,
                    'percent_hard': test.percent_hard,
                    'total_students': test.total_students,
                    'status': status,
                    'time_remaining': time_remaining,
                    'subjects': subjects_list,
                    'is_active': test.is_active
                }
                tests_data.append(test_data)
            
            category_data = {
                'uid': str(category.uid),
                'name': category.name,
                'display_name': category.get_name_display(),
                'description': category.description or '',
                'icon': icon_name,
                'test_count': len(tests_data),
                'tests': tests_data
            }
            categories_data.append(category_data)
        
        return JsonResponse({
            'success': True,
            'categories': categories_data,
            'current_time': current_time.isoformat()
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def start_mock_test(request, test_uid):
    print("CHALLU HUA API")
    """
    Start a mock test with comprehensive subscription validation
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)
            
        try:
            profile = request.user.profile
            email_token = profile.email_token
        except:
            email_token = None
    
        # Get the mock test
        mock_test = get_object_or_404(MockTest, uid=test_uid)
        
        logger.info(f"User {request.user.username} attempting to start mock test: {mock_test.title} (Category: {mock_test.category.name})")
        
        # **SUBSCRIPTION VALIDATION - CRITICAL CHECK**
        is_allowed, subscription_error = check_user_subscription_for_mocktest(
            request.user, 
            mock_test.category.name
        )
        
        if not is_allowed:
            logger.warning(f"Mock test access denied for {request.user.username}. "
                         f"Test: {mock_test.title}, Category: {mock_test.category.name}, "
                         f"Error: {subscription_error}")
            
            return JsonResponse({
                'success': False,
                'error': subscription_error,
                'required_subscription': get_required_subscription_display(mock_test.category.name),
                'redirect_to_subscription': True
            }, status=403)
        
        logger.info(f"Subscription validation passed for {request.user.username}")
        
        # Check if the user already has a session for this test
        existing_session = MockSession.objects.filter(
            user=request.user,
            mock_test=mock_test
        ).first()
        
        if existing_session:
            logger.info(f"Found existing session for {request.user.username}: {existing_session.uid}")
            
            # If session exists but not completed, resume it
            if not existing_session.is_completed:
                # Check if time is remaining
                time_remaining = existing_session.get_time_remaining()
                
                if time_remaining <= 0:
                    # Time's up, auto-submit the test
                    logger.info(f"Auto-submitting expired session for {request.user.username}")
                    existing_session.is_completed = True
                    existing_session.terminated_by_timeout = True
                    existing_session.end_time = timezone.now()
                    existing_session.time_spent_seconds = int((existing_session.end_time - existing_session.start_time).total_seconds())
                    existing_session.save()
                    existing_session.calculate_score()
                    
                    return JsonResponse({
                        'success': True,
                        'data': {
                            'session_expired': True,
                            'message': "Your previous test session has expired and was automatically submitted.",
                            'redirect_to_results': True,
                            'session_uid': str(existing_session.uid)
                        }
                    })
                
                # Resume existing session
                return JsonResponse({
                    'success': True,
                    'data': {
                        'should_resume': True,
                        'existing_session_uid': str(existing_session.uid),
                        'message': "You have an incomplete test session.",
                        'session': {
                            'uid': str(existing_session.uid),
                            'start_time': existing_session.start_time.isoformat(),
                            'time_remaining_seconds': int(time_remaining),
                            'is_completed': existing_session.is_completed,
                            'mock_test': {
                                'uid': str(mock_test.uid),
                                'title': mock_test.title,
                                'total_mcqs': mock_test.total_mcqs,
                                'time_limit_minutes': mock_test.time_limit_minutes
                            }
                        }
                    }
                })
            else:
                # Session exists and is completed, show results
                logger.info(f"Redirecting to completed session results for {request.user.username}")
                return JsonResponse({
                    'success': True,
                    'data': {
                        'session_completed': True,
                        'message': "You have already completed this test. Viewing your results.",
                        'redirect_to_results': True,
                        'session_uid': str(existing_session.uid)
                    }
                })
        
        # Create a new session
        logger.info(f"Creating new mock test session for {request.user.username}")
        
        session = MockSession.objects.create(
            user=request.user,
            mock_test=mock_test,
            start_time=timezone.now()
        )
        
        # Get all MCQs for this test
        test_mcqs = MockTestMCQ.objects.filter(mock_test=mock_test).order_by('order')
        
        if not test_mcqs.exists():
            logger.error(f"No MCQs found for mock test: {mock_test.title}")
            session.delete()
            return JsonResponse({
                'success': False,
                'error': "This mock test has no questions. Please contact support."
            }, status=400)
        
        # Create answer objects for each MCQ
        answer_objects = []
        for test_mcq in test_mcqs:
            answer_objects.append(MockAnswer(
                session=session,
                mcq=test_mcq.mcq
            ))
        
        # Bulk create for better performance
        MockAnswer.objects.bulk_create(answer_objects)
        
        logger.info(f"Created session {session.uid} with {len(answer_objects)} questions for {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'data': {
                'message': f"Mock test started successfully! You have {mock_test.time_limit_minutes} minutes to complete {mock_test.total_mcqs} questions.",
                'session': {
                    'uid': str(session.uid),
                    'start_time': session.start_time.isoformat(),
                    'time_remaining_seconds': mock_test.time_limit_minutes * 60,
                    'is_completed': False,
                    'mock_test': {
                        'uid': str(mock_test.uid),
                        'title': mock_test.title,
                        'description': mock_test.description,
                        'time_limit_minutes': mock_test.time_limit_minutes,
                        'total_mcqs': mock_test.total_mcqs,
                        'category': {
                            'name': mock_test.category.name,
                            'name_display': mock_test.category.get_name_display()
                        }
                    }
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating mock test session for {request.user.username}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': "Failed to start the mock test. Please try again or contact support."
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def take_mock_test(request, session_uid, email_token):
    """
    Get mock test session data for taking the test
    """
    try:
        # Get the session object
        if email_token != request.user.profile.email_token:
            return JsonResponse({
                'success': False,
                'error': 'Invalid email token',
                'redirect_to': f'/{request.user.profile.email_token}/mocktest/'
            }, status=403)

        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        mock_test = session.mock_test
        
        # If session is completed, redirect to results
        if session.is_completed:
            return JsonResponse({
                'success': True,
                'data': {
                    'session_completed': True,
                    'redirect_to_results': True,
                    'session_uid': str(session.uid)
                }
            })
        
        # Check if time's up
        time_remaining = session.get_time_remaining()
        if time_remaining <= 0:
            # Time's up, auto-submit the test
            session.is_completed = True
            session.terminated_by_timeout = True
            session.end_time = timezone.now()
            session.time_spent_seconds = int((session.end_time - session.start_time).total_seconds())
            session.save()
            session.calculate_score()
            return JsonResponse({
                'success': True,
                'data': {
                    'session_completed': True,
                    'timeout': True,
                    'redirect_to_results': True,
                    'session_uid': str(session.uid)
                }
            })
        
        # Get all answers for this session
        answers = session.answers.all().select_related('mcq', 'mcq__topic', 'mcq__topic__chapter', 'mcq__topic__chapter__unit', 'mcq__topic__chapter__unit__subject')
        
        # Prepare MCQ data
        questions = []
        for i, answer in enumerate(answers):
            # ✅ Fix: Access subject through the proper relationship chain
            subject_name = None
            topic_name = None
            
            if answer.mcq.topic:
                topic_name = answer.mcq.topic.name
                if answer.mcq.topic.chapter and answer.mcq.topic.chapter.unit and answer.mcq.topic.chapter.unit.subject:
                    subject_name = answer.mcq.topic.chapter.unit.subject.name
            

            
            questions.append({
                'number': i + 1,
                'uid': str(answer.mcq.uid),
                'text': answer.mcq.text,
                'options': [
                    answer.mcq.option_1,
                    answer.mcq.option_2,
                    answer.mcq.option_3,
                    answer.mcq.option_4
                ],
                'selected_option': answer.selected_option,
                'is_marked_for_review': answer.is_marked_for_review,
                'is_skipped': answer.is_skipped,
                'answer_uid': str(answer.uid),
                'image': request.build_absolute_uri(answer.mcq.image.url) if answer.mcq.image else None,  # ✅ Fixed: Full absolute URL
                'explanation': answer.mcq.explanation,
                'subject': subject_name,  # ✅ Fixed: Use the correct subject access
                'topic': topic_name,      # ✅ Fixed: Use the correct topic access
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'session': {
                    'uid': str(session.uid),
                    'start_time': session.start_time.isoformat(),
                    'is_completed': session.is_completed,
                    'time_remaining_seconds': int(time_remaining),
                    'current_question_index': session.current_question_index or 0,
                    'mock_test': {
                        'uid': str(mock_test.uid),
                        'title': mock_test.title,
                        'description': mock_test.description,
                        'time_limit_minutes': mock_test.time_limit_minutes,
                        'total_mcqs': mock_test.total_mcqs,
                        'category': {
                            'name': mock_test.category.name,
                            'name_display': mock_test.category.get_name_display()
                        }
                    }
                },
                'questions': questions,
                'total_questions': len(questions),
                'time_remaining_seconds': int(time_remaining)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting take mock test data: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': "Failed to load session data."
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def submit_answer(request, session_uid):
    """
    Submit answer for a mock test question
    """
    try:
        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        
        if session.is_completed:
            return JsonResponse({
                'success': False,
                'error': 'Test already completed'
            }, status=400)
        
        # Parse JSON data or form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        answer_uid = data.get('answer_uid')
        selected_option = data.get('option')
        is_marked = data.get('is_marked') == 'true' or data.get('is_marked') == True
        is_skipped = data.get('is_skipped') == 'true' or data.get('is_skipped') == True
        
        answer = get_object_or_404(MockAnswer, uid=answer_uid, session=session)
        
        # Update answer
        if selected_option and not is_skipped:
            answer.select_option(selected_option)
        elif is_skipped:
            answer.selected_option = None
        
        answer.is_marked_for_review = is_marked
        answer.is_skipped = is_skipped
        answer.save()
        
        # Update current question index
        current_index = int(data.get('current_index', 0))
        session.current_question_index = current_index
        session.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Answer saved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to save answer'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def submit_test(request, session_uid):
    """
    Submit the entire mock test
    """
    try:
        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        
        if session.is_completed:
            return JsonResponse({
                'success': False,
                'error': 'Test already completed'
            }, status=400)
        
        # Parse JSON data or form data
        if request.content_type == 'application/json':
            data = json.loads(request.body) if request.body else {}
        else:
            data = request.POST
        
        if not session.is_completed:
            session.is_completed = True
            session.end_time = timezone.now()
            session.time_spent_seconds = int((session.end_time - session.start_time).total_seconds())
            session.terminated_by_user = True
            session.save()
            
            # Calculate score
            session.calculate_score()
        
        prev_answer_uid = data.get('prev_que_uid')
        if prev_answer_uid:
            try:
                prev_answer = MockAnswer.objects.get(uid=prev_answer_uid, session=session)
                prev_answer.nextqueprevtime()
            except MockAnswer.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'data': {
                'message': 'Test submitted successfully',
                'session_uid': str(session.uid),
                'redirect_to_results': True,
                'score': session.score,
                'total_correct': session.total_correct,
                'total_incorrect': session.total_incorrect,
                'total_skipped': session.total_skipped
            }
        })
        
    except Exception as e:
        logger.error(f"Error submitting test: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to submit test'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def update_timer(request, session_uid):
    """
    Endpoint to update session timer and check if test should be auto-submitted
    """
    try:
        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        
        if session.is_completed:
            return JsonResponse({
                'success': True,
                'data': {
                    'status': 'completed',
                    'redirect_url': f'/mocktest/result/{session.uid}/'
                }
            })
        
        time_remaining = session.get_time_remaining()
        
        if time_remaining <= 0:
            # Time's up, auto-submit
            session.is_completed = True
            session.terminated_by_timeout = True
            session.end_time = timezone.now()
            session.time_spent_seconds = int((session.end_time - session.start_time).total_seconds())
            session.save()
            session.calculate_score()
            
            return JsonResponse({
                'success': True,
                'data': {
                    'status': 'timeout',
                    'redirect_url': f'/mocktest/result/{session.uid}/'
                }
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'status': 'active',
                'time_remaining': int(time_remaining)
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating timer: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to update timer'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def mock_test_result(request, session_uid):
    """
    Get mock test results
    """
    try:
        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        
        if not session.is_graded:
            session.calculate_score()
        
        # Update percentile if not already calculated
        total_participants = session.update_percentile()
        
        # Get detailed answer data for review with proper select_related
        answers = session.answers.all().select_related(
            'mcq', 
            'mcq__topic', 
            'mcq__topic__chapter', 
            'mcq__topic__chapter__unit', 
            'mcq__topic__chapter__unit__subject'
        )
        questions_with_answers = []
        
        for i, answer in enumerate(answers):
            # ✅ Fix: Access subject through the proper relationship chain
            subject_name = None
            topic_name = None
            
            if answer.mcq.topic:
                topic_name = answer.mcq.topic.name
                if answer.mcq.topic.chapter and answer.mcq.topic.chapter.unit and answer.mcq.topic.chapter.unit.subject:
                    subject_name = answer.mcq.topic.chapter.unit.subject.name
            
            questions_with_answers.append({
                'number': i + 1,
                'uid': str(answer.mcq.uid),
                'text': answer.mcq.text,
                'options': [
                    answer.mcq.option_1,
                    answer.mcq.option_2,
                    answer.mcq.option_3,
                    answer.mcq.option_4
                ],
                'correct_option': answer.mcq.correct_option,
                'selected_option': answer.selected_option,
                'is_correct': answer.is_correct,
                'is_marked_for_review': answer.is_marked_for_review,
                'is_skipped': answer.is_skipped,
                'time_spent': answer.time_spent_seconds,
                'time_spent_formatted': format_seconds_to_time(answer.time_spent_seconds),
                'explanation': answer.mcq.explanation,
                'subject': subject_name,  # ✅ Fixed: Use the correct subject access
                'topic': topic_name,      # ✅ Fixed: Use the correct topic access
                'image': request.build_absolute_uri(answer.mcq.image.url) if answer.mcq.image else None,  # ✅ Fixed: Full absolute URL
            })
        
        # Calculate additional statistics
        total_questions = len(questions_with_answers)
        max_score = total_questions * 4
        accuracy = round((session.total_correct / max(session.total_correct + session.total_incorrect, 1)) * 100)
        
        return JsonResponse({
            'success': True,
            'data': {
                'session': {
                    'uid': str(session.uid),
                    'start_time': session.start_time.isoformat(),
                    'end_time': session.end_time.isoformat() if session.end_time else None,
                    'time_spent_seconds': session.time_spent_seconds,
                    'time_spent_formatted': format_seconds_to_time(session.time_spent_seconds),
                    'is_completed': session.is_completed,
                    'terminated_by_timeout': session.terminated_by_timeout,
                    'terminated_by_user': session.terminated_by_user,
                    'score': session.score,
                    'max_score': max_score,
                    'total_correct': session.total_correct,
                    'total_incorrect': session.total_incorrect,
                    'total_skipped': session.total_skipped,
                    'accuracy': accuracy,
                    'percentile': session.percentile,
                    'rank': session.rank,
                },
                'mock_test': {
                    'uid': str(session.mock_test.uid),
                    'title': session.mock_test.title,
                    'description': session.mock_test.description,
                    'time_limit_minutes': session.mock_test.time_limit_minutes,
                    'total_mcqs': session.mock_test.total_mcqs,
                    'category': {
                        'name': session.mock_test.category.name,
                        'name_display': session.mock_test.category.get_name_display()
                    }
                },
                'questions': questions_with_answers,
                'total_questions': total_questions,
                'total_participants': total_participants,
                'statistics': {
                    'average_time_per_question': round(session.time_spent_seconds / max(total_questions, 1), 2),
                    'questions_attempted': session.total_correct + session.total_incorrect,
                    'completion_rate': round((total_questions - session.total_skipped) / total_questions * 100, 1)
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting mock test result: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load test results'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def mock_sessions_list(request, email_token):
    """
    Get all mock sessions for the current user
    """
    try:
        # Get all mock sessions for the current user
        completed_sessions = MockSession.objects.filter(
            user=request.user,
            is_completed=True
        ).select_related('mock_test', 'mock_test__category').order_by('-end_time')
        
        ongoing_sessions = MockSession.objects.filter(
            user=request.user,
            is_completed=False
        ).select_related('mock_test', 'mock_test__category').order_by('-start_time')
        
        completed_sessions_data = []
        for session in completed_sessions:
            completed_sessions_data.append({
                'uid': str(session.uid),
                'mock_test': {
                    'uid': str(session.mock_test.uid),
                    'title': session.mock_test.title,
                    'category': {
                        'name': session.mock_test.category.name,
                        'name_display': session.mock_test.category.get_name_display()
                    }
                },
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat() if session.end_time else None,
                'time_spent_seconds': session.time_spent_seconds,
                'time_spent_formatted': format_seconds_to_time(session.time_spent_seconds),
                'score': session.score,
                'total_correct': session.total_correct,
                'total_incorrect': session.total_incorrect,
                'total_skipped': session.total_skipped,
                'percentile': session.percentile,
                'rank': session.rank,
                'terminated_by_timeout': session.terminated_by_timeout,
            })
        
        ongoing_sessions_data = []
        for session in ongoing_sessions:
            time_remaining = session.get_time_remaining()
            ongoing_sessions_data.append({
                'uid': str(session.uid),
                'mock_test': {
                    'uid': str(session.mock_test.uid),
                    'title': session.mock_test.title,
                    'category': {
                        'name': session.mock_test.category.name,
                        'name_display': session.mock_test.category.get_name_display()
                    }
                },
                'start_time': session.start_time.isoformat(),
                'time_remaining_seconds': max(0, int(time_remaining)),
                'current_question_index': session.current_question_index or 0,
                'total_questions': session.mock_test.total_mcqs,
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'completed_sessions': completed_sessions_data,
                'ongoing_sessions': ongoing_sessions_data,
                'current_time': timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting sessions list: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load sessions'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def mark_question_visible(request, session_uid):
    """
    Mark a question as visible and update its visible_at timestamp.
    """
    try:
        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        
        if session.is_completed:
            return JsonResponse({
                'success': False,
                'error': 'Test already completed'
            }, status=400)
        
        # Parse JSON data or form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        answer_uid = data.get('answer_uid')
        answer = get_object_or_404(MockAnswer, uid=answer_uid, session=session)
        answer.mark_visible()
        
        prev_answer_uid = data.get('prev_que_uid')
        if prev_answer_uid:
            try:
                prev_answer = MockAnswer.objects.get(uid=prev_answer_uid, session=session)
                prev_answer.nextqueprevtime()
            except MockAnswer.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'message': 'Question marked as visible successfully'
        })
        
    except Exception as e:
        logger.error(f"Error marking question visible: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to mark question as visible'
        }, status=500)

@login_required
@csrf_exempt
@require_http_methods(["GET"])
def top_performers_view(request, email_token):
    """
    View to display top performers for each mock test category
    Shows varying number of top performers based on total participants
    Includes filtering by date/month and user participation
    """
    try:
        # Get filter parameters from request
        month_year = request.GET.get('month_year', '')
        only_my_tests = request.GET.get('my_tests', '') == 'on' or request.GET.get('my_tests', '') == 'true'
        
        # Base query for completed mock tests with at least one participant
        mock_tests = MockTest.objects.filter(
            sessions__is_completed=True,
            sessions__is_graded=True
        ).annotate(
            participant_count=Count('sessions', filter=Q(sessions__is_completed=True))
        ).filter(participant_count__gt=0).distinct().order_by('-start_time')
        
        # Apply date filter if specified
        if month_year:
            try:
                # Parse the month/year string (format: YYYY-MM)
                year, month = map(int, month_year.split('-'))
                mock_tests = mock_tests.filter(
                    start_time__year=year,
                    start_time__month=month
                )
            except (ValueError, IndexError):
                # If parsing fails, ignore the filter
                pass
        
        # Apply user participation filter if specified
        if only_my_tests:
            mock_tests = mock_tests.filter(
                sessions__user=request.user,
                sessions__is_completed=True
            )
        
        # Get all available month/year combinations for the filter dropdown
        available_dates = MockTest.objects.filter(
        sessions__is_completed=True,
        sessions__is_graded=True
            ).annotate(
                month_year=Concat(
                    Extract('start_time', 'year'),
                    Value('-'),
                    Extract('start_time', 'month'),
                    output_field=models.CharField()
                )
            ).values('month_year').annotate(count=Count('uid')).order_by('-month_year')
        
        # Format the dates for display
        formatted_dates = []
        for date_obj in available_dates:
            try:
                year, month = map(int, date_obj['month_year'].split('-'))
                month_name = datetime(2000, month, 1).strftime('%B')
                formatted_dates.append({
                    'value': date_obj['month_year'],
                    'display': f"{month_name} {year}",
                    'count': date_obj['count']
                })
            except (ValueError, IndexError):
                continue
        
        # Build performers data
        categories = {}
        
        for test in mock_tests:
            # Determine how many top performers to show based on participant count
            top_count = 3  # Default
            
            total_participants = getattr(test, 'total_students', 0) or test.participant_count
            
            if total_participants >= 2500:
                top_count = 100
            elif total_participants >= 1000:
                top_count = 50
            elif total_participants >= 100:
                top_count = 10
            elif total_participants >= 50:
                top_count = 5
            
            # Get top performers for this test
            top_sessions = MockSession.objects.filter(
                mock_test=test,
                is_completed=True,
                is_graded=True
            ).select_related('user').order_by('rank')[:top_count]
            
            if not top_sessions:
                continue
            
            # Format time for each session
            formatted_sessions = []
            for session in top_sessions:
                # Create a dictionary with session data including formatted time
                total_questions = test.total_mcqs if test.total_mcqs > 0 else 1
                max_score = total_questions * 4  # Assuming +4 for correct answers
                
                # Check if current user participated in this session
                is_current_user = session.user.id == request.user.id
                
                user_name = f"{session.user.first_name} {session.user.last_name}".strip()
                if not user_name:
                    user_name = session.user.username
                
                session_data = {
                    'user_id': session.user.id,
                    'user_name': user_name,
                    'rank': session.rank,
                    'score': session.score,
                    'max_score': max_score,
                    'score_format': f"{session.score}/{max_score}",
                    'total_correct': session.total_correct,
                    'total_incorrect': session.total_incorrect,
                    'percentile': session.percentile,
                    'time_spent_formatted': format_seconds_to_time(session.time_spent_seconds),
                    'time_spent_seconds': session.time_spent_seconds,
                    'is_current_user': is_current_user
                }
                formatted_sessions.append(session_data)
            
            # Group by test category
            category_name = test.category.get_name_display()
            if category_name not in categories:
                categories[category_name] = []
            
            categories[category_name].append({
                'test': {
                    'uid': str(test.uid),
                    'title': test.title,
                    'start_time': test.start_time.isoformat() if test.start_time else None,
                    'total_mcqs': test.total_mcqs,
                },
                'sessions': formatted_sessions,
                'total_participants': total_participants,
                'top_count': top_count,
                'date': test.start_time,  # Include date for sorting within categories
                'user_participated': test.sessions.filter(user=request.user, is_completed=True).exists()
            })
        
        # Sort each category to show most recent tests first
        for category, items in categories.items():
            categories[category] = sorted(items, key=lambda x: x['date'] or timezone.now(), reverse=True)
        
        return JsonResponse({
            'success': True,
            'data': {
                'categories': categories,
                'available_dates': formatted_dates,
                'selected_month_year': month_year,
                'only_my_tests': only_my_tests
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting top performers: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load top performers'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def top_performers_api(request):
    """
    API endpoint to get the top 5 performers across all mock tests.
    Returns data formatted for the top performers display.
    """
    try:
        # Get users who have completed at least one mock test session
        user_statistics = MockSession.objects.filter(
            is_completed=True
        ).values(
            'user',
            'user__username',
            'user__first_name',
            'user__last_name'
        ).annotate(
            total_score=Sum('score'),
            total_correct=Sum('total_correct'),
            total_incorrect=Sum('total_incorrect'),
            total_skipped=Sum('total_skipped'),
            total_mcqs=Sum('mock_test__total_mcqs'),
            total_time_spent=Sum('time_spent_seconds')
        ).order_by('-total_score', 'total_time_spent')[:5]
        
        # Format the response data
        top_performers = []
        for stat in user_statistics:
            # Calculate total_actual_mcqs after the query
            total_actual_mcqs = stat['total_correct'] + stat['total_incorrect'] + stat['total_skipped']
            
            # Calculate accuracy as percentage of correct answers out of attempted
            attempted = stat['total_correct'] + stat['total_incorrect']
            accuracy = round((stat['total_correct'] / max(attempted, 1)) * 100)
            
            # Format user name
            full_name = f"{stat['user__first_name']} {stat['user__last_name']}".strip()
            if not full_name:
                full_name = stat['user__username']
            
            top_performers.append({
                'user_id': stat['user'],
                'full_name': full_name,
                'total_score': stat['total_score'],
                'actual_max_score': total_actual_mcqs * 4,
                'max_possible_score': stat['total_mcqs'] * 4,
                'accuracy': accuracy,
                'correct_answers': stat['total_correct'],
                'incorrect_answers': stat['total_incorrect'],
                'time_spent': stat['total_time_spent'],  # in seconds
                'time_spent_formatted': format_seconds_to_time(stat['total_time_spent'])
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'top_performers': top_performers
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting top performers API: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to load top performers'
        }, status=500)

# Add this new API view for mobile mock practice
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_start_mock_practice(request):
    """
    Mobile API version of start_mock_practice for React Native
    """
    try:
        test_uid = request.data.get('test_uid')
        mode = request.data.get('mode', 'test')
        
        profile = request.user.profile
        
        # Check for pending mock test
        if profile.mock_current_test:
            try:
                existing_session = TestSession.objects.get(
                    test_id=profile.mock_current_test, 
                    user=request.user,
                    submitted=False
                )
                return Response({
                    'success': False,
                    'error': 'Your previous MockTest practice was not submitted. Please submit the pending test to start a new one.',
                    'ongoing_test_id': profile.mock_current_test
                }, status=status.HTTP_400_BAD_REQUEST)
            except TestSession.DoesNotExist:
                profile.mock_current_test = ''
                profile.save()

        if not test_uid:
            return Response({
                'success': False,
                'error': 'Mock test UID is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get mock test
        try:
            mock_test = MockTest.objects.get(uid=test_uid)
        except MockTest.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Mock test not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get MCQs for this mock test
        mock_test_mcqs = MockTestMCQ.objects.filter(mock_test=mock_test).order_by('order')
        final_mcqs = [test_mcq.mcq for test_mcq in mock_test_mcqs]
        
        if not final_mcqs:
            return Response({
                'success': False,
                'error': 'No MCQs found for this mock test'
            }, status=status.HTTP_400_BAD_REQUEST)

        final_mcqs_count = len(final_mcqs)
        
        # Subscription check
        is_allowed, subscription_error, use_free_mcqs = check_user_subscription_for_mocktest_practice(
            request.user, 
            final_mcqs_count
        )
        
        if not is_allowed:
            return Response({
                'success': False, 
                'error': subscription_error,
                'error_type': 'subscription_required',
                'redirect_to_subscription': True,
                'mcqs_needed': final_mcqs_count,
                'free_mcqs_remaining': getattr(profile, 'free_mcqs_remaining', 0)
            }, status=status.HTTP_403_FORBIDDEN)

        # Consume free MCQs if needed
        if use_free_mcqs:
            if not profile.can_attempt_test(final_mcqs_count):
                return Response({
                    'success': False,
                    'error': f"Insufficient free MCQs. You need {final_mcqs_count} but only have {profile.free_mcqs_remaining} remaining.",
                    'redirect_to_subscription': True,
                    'mcqs_needed': final_mcqs_count,
                    'free_mcqs_remaining': profile.free_mcqs_remaining
                }, status=status.HTTP_403_FORBIDDEN)
            
            profile.consume_free_mcqs(final_mcqs_count)

        # Create unique test ID
        test_id = f"MOCK_{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate time
        total_time_minutes = mock_test.time_limit_minutes
        total_time_seconds = total_time_minutes * 60
        
        # Format test name and selections
        test_name = f"MOCK TEST - {mock_test.title} - {mock_test.get_test_type_display()} - {mock_test.category.get_name_display()}"
        selections = [test_name]
        
        # Create test session
        test_session = TestSession.objects.create(
            user=request.user,
            test_id=test_id,
            total_questions=len(final_mcqs),
            selections=selections,
            totaltime=total_time_seconds,
            mode=mode
        )
        
        # Set mock_current_test in profile
        profile.mock_current_test = test_id
        profile.save()
        
        # Create TestAnswer entries
        for mcq in final_mcqs:
            TestAnswer.objects.create(
                test_session=test_session,
                mcq_uid=mcq.uid
            )
        
        # Prepare MCQ data for mobile app - FIXED DATA STRUCTURE
        mcq_data = []
        for mcq in final_mcqs:
            # Use the correct relationship path: topic -> chapter -> unit -> subject
            unit_name = ''
            subject_name = ''
            
            if mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit:
                unit_name = mcq.topic.chapter.unit.name
                if mcq.topic.chapter.unit.subject:
                    subject_name = mcq.topic.chapter.unit.subject.name
            
            mcq_dict = {
                'uid': str(mcq.uid),
                'text': mcq.text,
                'option_1': mcq.option_1,
                'option_2': mcq.option_2,
                'option_3': mcq.option_3,
                'option_4': mcq.option_4,
                'image': request.build_absolute_uri(mcq.image.url) if mcq.image else None,
                'topic': mcq.topic.name if mcq.topic else '',
                'unit_name': unit_name,
                'subject_name': subject_name,
            }
            mcq_data.append(mcq_dict)
        
        response_data = {
            'success': True,
            'message': f'Mock test practice started: {mock_test.title}',
            'test_data': {
                'mcqs': mcq_data,
                'count': len(final_mcqs),
                'test_id': test_id,
                'total_time': total_time_minutes,
                'mode': mode,
                'selections': selections,
                'is_mock': True,  # Flag to identify Mock tests
                'mock_test': {
                    'uid': str(mock_test.uid),
                    'title': mock_test.title,
                    'category': mock_test.category.get_name_display(),
                    'test_type': mock_test.get_test_type_display(),
                }
            }
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error in mobile_start_mock_practice: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Add this new view after your existing views (around line 1950)

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_check_current_mock_practice(request):
    """
    Check if user has any current unsubmitted mock practice session
    Checks mock_current_test field in Profile model
    """
    try:
        profile = request.user.profile
        
        # Check specifically for mock practice session
        if hasattr(profile, 'mock_current_test') and profile.mock_current_test:
            current_test_id = profile.mock_current_test
            
            try:
                test_session = TestSession.objects.get(
                    user=request.user, 
                    test_id=current_test_id
                )
                
                if not test_session.submitted:
                    logger.info(f"✅ Found ongoing mock practice: {current_test_id}")
                    return Response({
                        'success': True,
                        'has_current_test': True,
                        'test_id': current_test_id,
                        'mode': test_session.mode,
                        'total_questions': test_session.total_questions,
                        'created_at': test_session.created_at.isoformat()
                    })
                else:
                    # Clear submitted mock test from profile
                    logger.info(f"🧹 Clearing submitted mock test: {current_test_id}")
                    profile.mock_current_test = ''
                    profile.save()
                    
            except TestSession.DoesNotExist:
                # Clear invalid mock test reference
                logger.warning(f"⚠️ Mock test not found, clearing: {current_test_id}")
                profile.mock_current_test = ''
                profile.save()
        
        return Response({
            'success': True,
            'has_current_test': False
        })
        
    except Exception as e:
        logger.error(f"❌ Error in api_check_current_mock_practice: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_mock_test_result(request, session_uid):
    """
    Get comprehensive mock test result with detailed analytics
    """
    try:
        user = request.user
        logger.info(f"🔍 Fetching result for session: {session_uid}, user: {user.username}")
        
        # Get the mock session
        try:
            mock_session = MockSession.objects.get(uid=session_uid, user=user)
            logger.info(f"✅ Found MockSession: {mock_session.uid}")
        except MockSession.DoesNotExist:
            logger.error(f"❌ MockSession not found for uid: {session_uid}")
            return Response({
                'success': False,
                'error': 'Mock session not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not mock_session.is_completed:
            logger.warning(f"⚠️ Mock session not completed: {session_uid}")
            return Response({
                'success': False,
                'error': 'Test not completed yet'
            }, status=status.HTTP_400_BAD_REQUEST)
        
                # ✅ CORRECT: Get answers in the SAME way as take_mock_test does
        # ✅ EXACT same as website - use the related manager
        answers = mock_session.answers.all().select_related(
            'mcq',
            'mcq__topic',
            'mcq__topic__chapter',
            'mcq__topic__chapter__unit',
            'mcq__topic__chapter__unit__subject',
            'mcq__difficulty',
            'mcq__types'
        )

        # Convert to list
        answers = list(answers)

        # Basic stats
        total_questions = mock_session.mock_test.total_mcqs
        total_attempted = 0
        total_correct = 0
        total_incorrect = 0
        total_skipped = 0
        
        # Calculate score with negative marking
        score = 0
        for answer in answers:
            if answer.selected_option:
                total_attempted += 1
                if answer.is_correct:
                    total_correct += 1
                    score += 4
                else:
                    total_incorrect += 1
                    score -= 1
            else:
                total_skipped += 1
        
        logger.info(f"📈 Score calculated: {score}, Correct: {total_correct}, Incorrect: {total_incorrect}")
        
        # Update mock session
        mock_session.score = score
        mock_session.total_attempted = total_attempted
        mock_session.total_correct = total_correct
        mock_session.total_incorrect = total_incorrect
        mock_session.total_skipped = total_skipped
        mock_session.save()
        
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        
        # Subject-Unit wise analysis
        unit_stats = {}
        for answer in answers:
            try:
                subject_name = answer.mcq.topic.chapter.unit.subject.name
                unit_name = answer.mcq.topic.chapter.unit.name
                unit_key = f"{subject_name}::{unit_name}"
                
                if unit_key not in unit_stats:
                    unit_stats[unit_key] = {
                        'subject': subject_name,
                        'unit': unit_name,
                        'total': 0,
                        'attempted': 0,
                        'correct': 0,
                        'incorrect': 0,
                        'skipped': 0,
                        'accuracy': 0,
                        'total_time_spent': 0,
                        'score': 0
                    }
                
                unit_stats[unit_key]['total'] += 1
                unit_stats[unit_key]['total_time_spent'] += answer.time_spent_seconds
                
                if answer.selected_option:
                    unit_stats[unit_key]['attempted'] += 1
                    if answer.is_correct:
                        unit_stats[unit_key]['correct'] += 1
                        unit_stats[unit_key]['score'] += 4
                    else:
                        unit_stats[unit_key]['incorrect'] += 1
                        unit_stats[unit_key]['score'] -= 1
                else:
                    unit_stats[unit_key]['skipped'] += 1
            except Exception as e:
                logger.error(f"❌ Error processing answer for unit stats: {e}")
                continue
        
        # Calculate accuracy for each unit
        for unit in unit_stats.values():
            if unit['attempted'] > 0:
                unit['accuracy'] = round((unit['correct'] / unit['attempted']) * 100, 2)
        
        # Difficulty-wise analysis
        difficulty_stats = {}
        for answer in answers:
            try:
                difficulty = answer.mcq.difficulty.name if answer.mcq.difficulty else 'Unknown'
                
                if difficulty not in difficulty_stats:
                    difficulty_stats[difficulty] = {
                        'difficulty': difficulty,
                        'total': 0,
                        'attempted': 0,
                        'correct': 0,
                        'incorrect': 0,
                        'skipped': 0,
                        'accuracy': 0,
                        'score': 0
                    }
                
                difficulty_stats[difficulty]['total'] += 1
                
                if answer.selected_option:
                    difficulty_stats[difficulty]['attempted'] += 1
                    if answer.is_correct:
                        difficulty_stats[difficulty]['correct'] += 1
                        difficulty_stats[difficulty]['score'] += 4
                    else:
                        difficulty_stats[difficulty]['incorrect'] += 1
                        difficulty_stats[difficulty]['score'] -= 1
                else:
                    difficulty_stats[difficulty]['skipped'] += 1
            except Exception as e:
                logger.error(f"❌ Error processing answer for difficulty stats: {e}")
                continue
        
        # Calculate accuracy for each difficulty
        for diff in difficulty_stats.values():
            if diff['attempted'] > 0:
                diff['accuracy'] = round((diff['correct'] / diff['attempted']) * 100, 2)
        
        # Question-wise details with time tracking
        question_details = []
        time_analysis = []
        
        for idx, answer in enumerate(answers, 1):
            try:
                mcq = answer.mcq
                
                if not answer.selected_option:
                    status_val = 'skipped'
                    points = 0
                elif answer.is_correct:
                    status_val = 'correct'
                    points = 4
                else:
                    status_val = 'incorrect'
                    points = -1
                
                question_data = {
                    'question_number': idx,
                    'mcq_uid': str(mcq.uid),
                    'question_text': mcq.text,
                    'option_1': mcq.option_1 or '',
                    'option_2': mcq.option_2 or '',
                    'option_3': mcq.option_3 or '',
                    'option_4': mcq.option_4 or '',
                    'correct_option': mcq.correct_option or '',
                    'selected_option': answer.selected_option,
                    'is_correct': answer.is_correct,
                    'is_skipped': not answer.selected_option,
                    'time_spent_seconds': round(answer.time_spent_seconds, 2),
                    'points': points,
                    'status': status_val,
                    'explanation': mcq.explanation or '',
                    'difficulty': mcq.difficulty.name if mcq.difficulty else 'Unknown',
                    'mcq_type': mcq.types.types if mcq.types else 'General',
                    'subject': mcq.topic.chapter.unit.subject.name,
                    'unit': mcq.topic.chapter.unit.name,
                    'chapter': mcq.topic.chapter.name,
                    'topic': mcq.topic.name,
                    'image_url': request.build_absolute_uri(mcq.image.url) if mcq.image else None,
                    'is_marked_for_review': answer.is_marked_for_review
                }
                
                question_details.append(question_data)
                time_analysis.append({
                    'question_number': idx,
                    'time_spent': round(answer.time_spent_seconds, 2),
                    'status': status_val,
                    'points': points
                })
            except Exception as e:
                logger.error(f"❌ Error processing question {idx}: {e}")
                continue
        
        # Calculate time statistics
        time_spent_list = [ans.time_spent_seconds for ans in answers if ans.time_spent_seconds]
        total_time_spent = sum(time_spent_list) if time_spent_list else 0
        max_time_question = max(time_spent_list) if time_spent_list else 0
        min_time_question = min(time_spent_list) if time_spent_list else 0
        median_time = sorted(time_spent_list)[len(time_spent_list) // 2] if time_spent_list else 0
        
        # Prepare response
        result_data = {
            'success': True,
            'session_uid': str(mock_session.uid),
            'mock_test': {
                'uid': str(mock_session.mock_test.uid),
                'title': mock_session.mock_test.title,
                'category': mock_session.mock_test.category.get_name_display(),
                'test_type': mock_session.mock_test.get_test_type_display(),
                'time_limit_minutes': mock_session.mock_test.time_limit_minutes
            },
            'overall_stats': {
                'total_questions': total_questions,
                'total_attempted': total_attempted,
                'total_correct': total_correct,
                'total_incorrect': total_incorrect,
                'total_skipped': total_skipped,
                'score': score,
                'max_score': total_questions * 4,
                'accuracy': round(accuracy, 2),
                'total_participants': mock_session.mock_test.total_students,
                'completion_date': mock_session.end_time.isoformat() if mock_session.end_time else None
            },
            'time_stats': {
                'total_time_seconds': round(total_time_spent, 2),
                'total_time_minutes': round(total_time_spent / 60, 2),
                'max_time_question': round(max_time_question, 2),
                'min_time_question': round(min_time_question, 2),
                'median_time': round(median_time, 2),
                'time_limit_minutes': mock_session.mock_test.time_limit_minutes,
                'time_remaining_minutes': round((mock_session.mock_test.time_limit_minutes * 60 - total_time_spent) / 60, 2)
            },
            'unit_analysis': sorted(
                list(unit_stats.values()),
                key=lambda x: x['score'],
                reverse=True
            ),
            'difficulty_analysis': list(difficulty_stats.values()),
            'time_analysis': time_analysis,
            'questions': question_details
        }
        
        logger.info(f"✅ Successfully generated result for session {session_uid}")
        return Response(result_data)
        
    except MockSession.DoesNotExist:
        logger.error(f"❌ MockSession.DoesNotExist: {session_uid}")
        return Response({
            'success': False,
            'error': 'Mock session not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"❌ Error in api_mock_test_result: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from mocktest.models import MockSession
from django.db.models import Q

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def review_mock_data(request):
    """
    Get ongoing and completed mock test sessions for the current user
    """
    try:
        user = request.user
        
        # ✅ FIXED: Changed 'mocktest' to 'mock_test' in both places
        # Get ongoing sessions (not completed)
        ongoing_sessions = MockSession.objects.filter(
            user=user,
            is_completed=False
        ).select_related('mock_test', 'mock_test__category').order_by('-start_time')
        
        # Get completed sessions
        completed_sessions = MockSession.objects.filter(
            user=user,
            is_completed=True
        ).select_related('mock_test', 'mock_test__category').order_by('-end_time')
        
        # Serialize ongoing sessions
        ongoing_data = []
        for session in ongoing_sessions:
            # Calculate progress
            total_questions = session.mock_test.total_mcqs
            attempted = session.total_attempted + session.total_skipped
            progress_percentage = round((attempted / total_questions * 100), 1) if total_questions > 0 else 0
            
            ongoing_data.append({
                'uid': str(session.uid),
                'mocktest': {  # Keep as 'mocktest' in response for React Native
                    'uid': str(session.mock_test.uid),
                    'title': session.mock_test.title,
                    'category': session.mock_test.category.get_name_display(),
                    'total_mcqs': session.mock_test.total_mcqs,
                    'time_limit_minutes': session.mock_test.time_limit_minutes,
                },
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat() if session.end_time else None,
                'time_spent_seconds': session.time_spent_seconds,
                'is_completed': session.is_completed,
                'total_attempted': session.total_attempted,
                'total_correct': session.total_correct,
                'total_incorrect': session.total_incorrect,
                'total_skipped': session.total_skipped,
                'score': float(session.score),
                'progress_percentage': progress_percentage,
            })
        
        # Serialize completed sessions
        completed_data = []
        for session in completed_sessions:
            completed_data.append({
                'uid': str(session.uid),
                'mocktest': {  # Keep as 'mocktest' in response for React Native
                    'uid': str(session.mock_test.uid),
                    'title': session.mock_test.title,
                    'category': session.mock_test.category.get_name_display(),
                    'total_mcqs': session.mock_test.total_mcqs,
                    'time_limit_minutes': session.mock_test.time_limit_minutes,
                },
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat() if session.end_time else None,
                'time_spent_seconds': session.time_spent_seconds,
                'is_completed': session.is_completed,
                'total_attempted': session.total_attempted,
                'total_correct': session.total_correct,
                'total_incorrect': session.total_incorrect,
                'total_skipped': session.total_skipped,
                'score': float(session.score),
                'rank': session.rank,
                'percentile': float(session.percentile) if session.percentile else None,
                'progress_percentage': 100,
            })
        
        return Response({
            'success': True,
            'ongoing_sessions': ongoing_data,
            'completed_sessions': completed_data,
        })
        
    except Exception as e:
        print(f"Error in review_mock_data: {str(e)}")
        import traceback
        traceback.print_exc()  # ✅ Added for better debugging
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_session_status(request, session_uid):
    """
    Check if a mock test session has exceeded its time limit
    """
    try:
        # ✅ FIXED: Changed 'mocktest' to 'mock_test'
        session = MockSession.objects.select_related('mock_test').get(
            uid=session_uid,
            user=request.user
        )
        
        # Check if already completed
        if session.is_completed:
            return Response({
                'success': True,
                'time_expired': False,
                'already_completed': True,
            })
        
        # Calculate time remaining
        time_limit = timedelta(minutes=session.mock_test.time_limit_minutes)
        elapsed_time = timezone.now() - session.start_time
        time_remaining = time_limit - elapsed_time
        
        # Check if time has expired
        time_expired = time_remaining.total_seconds() <= 0
        
        return Response({
            'success': True,
            'time_expired': time_expired,
            'time_remaining_seconds': max(0, int(time_remaining.total_seconds())),
            'already_completed': False,
        })
        
    except MockSession.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Session not found'
        }, status=404)
    except Exception as e:
        print(f"Error in check_session_status: {str(e)}")
        import traceback
        traceback.print_exc()  # ✅ Added for better debugging
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from payments.models import UserSubscriptionManager


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_mock_access(request):
    """
    Check if user can start MOCK test practice based on:
    0. No incomplete MOCK test session exists (mock_current_test is blank)
    1. Free attempts remaining
    2. Active subscription status
    """
    try:
        user = request.user
        profile = user.profile
        num_questions = int(request.data.get('num_questions', 0))
        
        if num_questions <= 0:
            return Response({
                'success': False,
                'error': 'Invalid number of questions requested'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        print(f"?? Checking MOCK access for {num_questions} questions")
        print(f"?? User: {user.username}, Free MCQs: {profile.free_mcqs_remaining}")
        
        # ? FIRST CHECK: Does user have an incomplete MOCK test?
        if profile.mock_current_test:
            print(f"?? User has incomplete MOCK test: {profile.mock_current_test}")
            return Response({
                'success': True,
                'access_granted': False,
                'access_type': 'blocked',
                'has_incomplete_mock_test': True,
                'mock_current_test_id': profile.mock_current_test,
                'message': 'You have an incomplete mock practice session. Please complete it before starting a new one.',
                'redirect_to': 'continue_mock_test'
            })
        
        print("? No incomplete mock test found")
        
        # Check if user has enough free attempts
        has_free_access = profile.free_mcqs_remaining >= num_questions
        
        # Check if user has any active subscription
        has_active_subscription = False
        active_subscriptions = []
        
        try:
            subscription_summary = UserSubscriptionManager.get_subscription_summary(user)
            
            for category, details in subscription_summary.items():
                if not details['is_expired']:
                    has_active_subscription = True
                    active_subscriptions.append({
                        'category': category,
                        'category_display': details['category_display'],
                        'plan_name': details['plan_name'],
                        'days_remaining': details['days_remaining'],
                        'end_date': details['end_date'].isoformat() if details['end_date'] else None
                    })
        except Exception as e:
            print(f"?? Error checking subscriptions: {e}")
            has_active_subscription = False
        
        print(f"? Free Access: {has_free_access}")
        print(f"? Subscription: {has_active_subscription}")
        
        # User has active subscription - unlimited access
        if has_active_subscription:
            return Response({
                'success': True,
                'access_granted': True,
                'access_type': 'subscription',
                'has_incomplete_mock_test': False,
                'message': 'Access granted via active subscription',
                'free_mcqs_remaining': profile.free_mcqs_remaining,
                'has_subscription': True,
                'active_subscriptions': active_subscriptions
            })
        
        # User has enough free attempts
        if has_free_access:
            return Response({
                'success': True,
                'access_granted': True,
                'access_type': 'free',
                'has_incomplete_mock_test': False,
                'message': f'Access granted via free attempts. {profile.free_mcqs_remaining - num_questions} MCQs will remain after this session.',
                'free_mcqs_remaining': profile.free_mcqs_remaining,
                'free_mcqs_after': profile.free_mcqs_remaining - num_questions,
                'has_subscription': False
            })
        
        # User doesn't have access - need subscription
        return Response({
            'success': True,
            'access_granted': False,
            'access_type': 'none',
            'has_incomplete_mock_test': False,
            'message': f'You need {num_questions} MCQs but only have {profile.free_mcqs_remaining} free attempts remaining. Subscribe to continue unlimited practice.',
            'free_mcqs_remaining': profile.free_mcqs_remaining,
            'required_mcqs': num_questions,
            'shortfall': num_questions - profile.free_mcqs_remaining,
            'has_subscription': False,
            'redirect_to': 'subscription'
        })
        
    except Exception as e:
        print(f"? Error in check_mock_access: {e}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
