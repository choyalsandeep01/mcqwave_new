from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout
from django.utils import timezone
from accounts.models import Profile
from mocktest.models import MockTest, MockSession
import traceback
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_home_view(request, uuid=None):
    """
    Mobile API version of home_view
    Returns user profile data as JSON
    """
    try:
        if uuid:
            user_profile = get_object_or_404(Profile, email_token=uuid)
        else:
            try:
                user_profile = request.user.profile
            except AttributeError:
                user_profile = Profile.objects.get(user=request.user)
        
        response_data = {
            'success': True,
            'user': {
                'uid': str(user_profile.user.uid) if hasattr(user_profile.user, 'uid') else str(user_profile.user.id),
                'username': user_profile.user.username,
                'email': user_profile.user.email,
                'first_name': user_profile.user.first_name,
                'last_name': user_profile.user.last_name,
                'has_profile_image': bool(user_profile.profile_image),
                'profile_image_url': user_profile.profile_image.url if user_profile.profile_image else None,
            },
            'message': 'User data retrieved successfully'
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Profile.DoesNotExist:
        return Response({
            'success': False,
            'error': 'User profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_logout_view(request):
    """
    Mobile API version of logout_view
    Returns success message instead of redirect
    """
    try:
        logout(request)
        return Response({
            'success': True,
            'message': 'User logged out successfully'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_mocktestdata(request):
    """
    Mobile API version of mocktestdata
    EXACT SAME LOGIC as your existing view - just returns JSON
    """
    try:
        # Get user profile - same logic as your existing view
        try:
            user_profile = request.user.profile
        except AttributeError:
            user_profile = Profile.objects.get(user=request.user)
        
        # Get current live mock tests - same logic as your existing view
        now = timezone.now()
        live_mock_tests = MockTest.objects.filter(
            is_active=True,
            start_time__lte=now,
            end_time__gte=now
        ).order_by('-start_time')  # Latest first
        
        mock_test_data = None
        
        def format_time_remaining(seconds):
            """Convert seconds to HH:MM format"""
            if seconds <= 0:
                return "00:00"
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours:02d}:{minutes:02d}"
        
        if live_mock_tests.exists():
            # Get the latest mock test (first in the ordered list)
            latest_mock_test = live_mock_tests.first()
            
            # Check if user has a pending session for the LATEST mock test only
            user_session = MockSession.objects.filter(
                user=user_profile.user,
                mock_test=latest_mock_test,
                is_completed=False
            ).first()
            
            if user_session:
                # User has a pending test for the latest mock test
                mock_test = user_session.mock_test
                time_remaining = user_session.get_time_remaining()
                
                if time_remaining <= 0:
                    # Test has expired, auto-complete it
                    user_session.terminated_by_timeout = True
                    user_session.calculate_score()
                    # Show completed test
                    mock_test_data = {
                        'test': {
                            'uid': str(mock_test.uid),
                            'title': mock_test.title,
                            'total_mcqs': mock_test.total_mcqs,
                            'duration': mock_test.time_limit_minutes,
                            'test_type': mock_test.category.name,
                        },
                        'session': {
                            'uid': str(user_session.uid),
                            'score': user_session.score,
                            'total_attempted': user_session.total_attempted,
                            'total_correct': user_session.total_correct,
                            'total_incorrect': user_session.total_incorrect,
                            'percentile': user_session.percentile,
                        },
                        'status': 'completed',
                        'button_text': 'View Score',
                        'button_action': 'viewScore',
                        'time_remaining': 0,
                        'time_remaining_formatted': "00:00",
                        'can_continue': False
                    }
                else:
                    # Test is still active, can continue
                    mock_test_data = {
                        'test': {
                            'uid': str(mock_test.uid),
                            'title': mock_test.title,
                            'total_mcqs': mock_test.total_mcqs,
                            'duration': mock_test.time_limit_minutes,
                            'test_type': mock_test.category.name,
                        },
                        'session': {
                            'uid': str(user_session.uid),
                            'current_question_index': user_session.current_question_index,
                        },
                        'status': 'in_progress',
                        'button_text': 'Continue',
                        'button_action': 'continueTest',
                        'time_remaining': time_remaining,
                        'time_remaining_formatted': format_time_remaining(time_remaining),
                        'can_continue': True,
                        'current_question': user_session.current_question_index + 1,
                        'total_questions': mock_test.total_mcqs
                    }
            else:
                # Check if user has completed the LATEST mock test only
                completed_session = MockSession.objects.filter(
                    user=user_profile.user,
                    mock_test=latest_mock_test,
                    is_completed=True
                ).first()
                
                if completed_session:
                    # User has completed the latest test
                    mock_test_data = {
                        'test': {
                            'uid': str(completed_session.mock_test.uid),
                            'title': completed_session.mock_test.title,
                            'total_mcqs': completed_session.mock_test.total_mcqs,
                            'duration': completed_session.mock_test.time_limit_minutes,
                            'test_type': completed_session.mock_test.category.name,
                        },
                        'session': {
                            'uid': str(completed_session.uid),
                            'score': completed_session.score,
                            'total_attempted': completed_session.total_attempted,
                            'total_correct': completed_session.total_correct,
                            'total_incorrect': completed_session.total_incorrect,
                            'percentile': completed_session.percentile,
                        },
                        'status': 'completed',
                        'button_text': 'View Score',
                        'button_action': 'viewScore',
                        'time_remaining': 0,
                        'time_remaining_formatted': "00:00",
                        'can_continue': False
                    }
                else:
                    # User can start the latest test
                    mock_test = latest_mock_test
                    time_remaining = (mock_test.end_time - now).total_seconds()
                    mock_test_data = {
                        'test': {
                            'uid': str(mock_test.uid),
                            'title': mock_test.title,
                            'total_mcqs': mock_test.total_mcqs,
                            'duration': mock_test.time_limit_minutes,
                            'test_type': mock_test.category.name,
                        },
                        'session': None,
                        'status': 'available',
                        'button_text': 'Start',
                        'button_action': 'startTest',
                        'time_remaining': time_remaining,
                        'time_remaining_formatted': format_time_remaining(time_remaining),
                        'can_continue': False
                    }
        
        response_data = {
            'success': True,
            'user': {
                'uid': str(user_profile.user.uid) if hasattr(user_profile.user, 'uid') else str(user_profile.user.id),
                'username': user_profile.user.username,
                'email': user_profile.user.email,
            },
            'mock_test_data': mock_test_data,
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Profile.DoesNotExist:
        return Response({
            'success': False,
            'error': 'User profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except AttributeError as e:
        print(f"AttributeError: {e}")
        return Response({
            'success': False,
            'error': f'Attribute error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        print(f"General error: {e}")
        print(traceback.format_exc())
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from mcqs.models import TestSession
from payments.models import UserSubscription, PaymentPlan


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_dashboard_data(request):
    """Get dashboard data including pending sessions and subscription status"""
    try:
        user = request.user
        
        # Get all unsubmitted test sessions
        all_pending_sessions = TestSession.objects.filter(
            user=user,
            submitted=False
        ).order_by('-created_at')
        
        # Categorize sessions with limit of 2 per category
        curated_sessions = []
        pyq_sessions = []
        mock_sessions = []
        
        for session in all_pending_sessions:
            session_data = {
                'test_id': session.test_id,
                'created_at': session.created_at.isoformat(),
                'total_questions': int(session.total_questions),
                'mode': session.mode,
                'pyq': session.pyq,
            }
            
            # Check if it's a mock test
            if session.selections and any('MOCK TEST' in str(sel).upper() for sel in session.selections):
                if len(mock_sessions) < 2:  # Limit to 2 mock sessions
                    session_data['type'] = 'mock'
                    mock_sessions.append(session_data)
            elif session.pyq:
                if len(pyq_sessions) < 2:  # Limit to 2 PYQ sessions
                    session_data['type'] = 'pyq'
                    pyq_sessions.append(session_data)
            else:
                if len(curated_sessions) < 2:  # Limit to 2 curated sessions
                    session_data['type'] = 'curated'
                    curated_sessions.append(session_data)
            
            # Break early if all categories have 2 sessions
            if len(curated_sessions) >= 2 and len(pyq_sessions) >= 2 and len(mock_sessions) >= 2:
                break
        
        # Get user subscriptions
        subscriptions = UserSubscription.objects.filter(
            user=user,
            is_active=True
        ).select_related('plan')
        
        active_subscriptions = []
        has_any_subscription = False
        
        for sub in subscriptions:
            if not sub.is_expired:
                has_any_subscription = True
                active_subscriptions.append({
                    'category': sub.plan.category,
                    'category_display': sub.plan.get_category_display(),
                    'plan_name': sub.plan.name,
                    'end_date': sub.end_date.isoformat(),
                    'days_remaining': sub.days_remaining,
                })
        
        return Response({
            'success': True,
            'pending_sessions': {
                'curated': curated_sessions,
                'pyq': pyq_sessions,
                'mock': mock_sessions,
            },
            'subscription_status': {
                'has_subscription': has_any_subscription,
                'subscriptions': active_subscriptions,
            }
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)
