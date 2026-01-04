from django.shortcuts import render,redirect
from django.contrib.auth.models import User
from django.http import HttpResponse
from accounts.models import Profile, AppVersion
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.urls import reverse
from mocktest.models import MockTest, MockSession
from datetime import timedelta
from django.http import JsonResponse

# Create your views here.
@login_required(login_url='/')
def logout_view(request):
    logout(request)  # This logs out the user
    
    return redirect('/')
    

@login_required(login_url='/')
def home_view(request, uuid):
    user_profile = get_object_or_404(Profile, email_token=uuid)
    
    # Get Android app version info
    try:
        android_version = AppVersion.objects.get(platform='android')
    except AppVersion.DoesNotExist:
        android_version = None
    
    context = {
        'user': user_profile,
        'android_version': android_version,
    }
    
    return render(request, 'home/index.html', context)


@login_required
def mocktestdata(request):
    try:
        # Get user profile
        try:
            user_profile = request.user.profile
        except AttributeError:
            # If user doesn't have profile attribute, get it through Profile model
            user_profile = Profile.objects.get(user=request.user)
        
        # Get current live mock tests - ordered by start_time descending to get latest first
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
                mock_test=latest_mock_test,  # Only check for the latest mock test
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
                    mock_test=latest_mock_test,  # Only check for the latest mock test
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
        
        return JsonResponse(response_data)
        
    except Profile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'User profile not found'
        }, status=404)
    except AttributeError as e:
        print(f"AttributeError: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Attribute error: {str(e)}'
        }, status=500)
    except Exception as e:
        print(f"General error: {e}")
        import traceback
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)