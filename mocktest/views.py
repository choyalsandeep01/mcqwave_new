from django.shortcuts import render
from django.http import HttpResponseRedirect,HttpResponse

# Create your views here.
from django.shortcuts import render
from django.utils import timezone
from .models import MockTestCategory, MockTest
from django.contrib.auth.decorators import login_required
import logging

logger = logging.getLogger(__name__)
@login_required(login_url='/login')
def mock_tests_view(request,email_token):
    """
    View to display all mock test categories and their associated tests.
    """
    if email_token==request.user.profile.email_token:
    # Get all active categories
        categories = MockTestCategory.objects.all()
        
        # Get current time for test status calculation
        current_time = timezone.now()
        
        # Context data for the template
        context = {
            'categories': categories,
            'current_time': current_time,
        }
        
        return render(request, 'mocktest/mock_home.html', context)
    else:
        email_token=request.user.profile.email_token
        return HttpResponseRedirect(f'/{email_token}/mocktest/')

    # mocktest/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from .models import MockTest, MockSession, MockAnswer, MockTestMCQ

@login_required(login_url='/login')
def start_mock_test(request, test_uid):
    """
    Start a mock test with comprehensive subscription validation
    """
    if not request.user.is_authenticated:
        return redirect('/login')
        
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
        mock_test.category.name  # This will be 'NEET-PG Pattern', 'INI-CET', or 'FMGE'
    )
    
    if not is_allowed:
        messages.error(request, subscription_error)
        logger.warning(f"Mock test access denied for {request.user.username}. "
                     f"Test: {mock_test.title}, Category: {mock_test.category.name}, "
                     f"Error: {subscription_error}")
        
        # Redirect back to mock test home with error message
        if email_token:
            return redirect('mocktest_home', email_token=email_token)
        else:
            return redirect('/')
    
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
                
                messages.info(request, "Your previous test session has expired and was automatically submitted.")
                return redirect('mock_test_result', session_uid=existing_session.uid)
            
            # Resume existing session
            return redirect('take_mock_test', email_token=email_token, session_uid=existing_session.uid)
        else:
            # Session exists and is completed, show results
            logger.info(f"Redirecting to completed session results for {request.user.username}")
            messages.info(request, "You have already completed this test. Viewing your results.")
            return redirect('mock_test_result', session_uid=existing_session.uid)
    
    # Create a new session
    logger.info(f"Creating new mock test session for {request.user.username}")
    
    try:
        session = MockSession.objects.create(
            user=request.user,
            mock_test=mock_test,
            start_time=timezone.now()
        )
        
        # Get all MCQs for this test
        test_mcqs = MockTestMCQ.objects.filter(mock_test=mock_test).order_by('order')
        
        if not test_mcqs.exists():
            logger.error(f"No MCQs found for mock test: {mock_test.title}")
            messages.error(request, "This mock test has no questions. Please contact support.")
            return redirect('mocktest_home', email_token=email_token)
        
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
        messages.success(request, f"Mock test started successfully! You have {mock_test.time_limit_minutes} minutes to complete {mock_test.total_mcqs} questions.")
        
        return redirect('take_mock_test', email_token=email_token, session_uid=session.uid)
        
    except Exception as e:
        logger.error(f"Error creating mock test session for {request.user.username}: {str(e)}", exc_info=True)
        messages.error(request, "Failed to start the mock test. Please try again or contact support.")
        return redirect('mocktest_home', email_token=email_token)

import json
from django.core.serializers.json import DjangoJSONEncoder

@login_required(login_url='/login')
def take_mock_test(request, session_uid, email_token):
    # Get the session object
    if email_token==request.user.profile.email_token:

        session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
        mock_test = session.mock_test
        
        # If session is completed, redirect to results
        if session.is_completed:
            return redirect('mock_test_result', session_uid=session.uid)
        
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
            return redirect('mock_test_result', session_uid=session.uid)
        
        # Get all answers for this session
        answers = session.answers.all().select_related('mcq')
        
        # Prepare MCQ data for template
        questions = []
        for i, answer in enumerate(answers):
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
                'image': answer.mcq.image.url if answer.mcq.image else '' 
            })
        questions_json = json.dumps(
            questions,
            cls=DjangoJSONEncoder,
            ensure_ascii=False  # This helps with Unicode characters
        )
        # Prepare session data for template
        # In your Django view
        context = {
            'session': session,
            'mock_test': mock_test,
            'questions_json': questions_json,  # Pre-serialize to JSON
            'total_questions': len(questions),
            'time_remaining_seconds': int(time_remaining),
            'current_index': session.current_question_index
        }
        
        return render(request, 'mocktest/mock_test.html', context)
    else:
        email_token=request.user.profile.email_token
        return HttpResponseRedirect(f'/{email_token}/mocktest/')

@login_required(login_url='/login')
def submit_answer(request, session_uid):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
    session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
    
    if session.is_completed:
        return JsonResponse({'status': 'error', 'message': 'Test already completed'})
    
    answer_uid = request.POST.get('answer_uid')
    selected_option = request.POST.get('option')
    is_marked = request.POST.get('is_marked') == 'true'
    is_skipped = request.POST.get('is_skipped') == 'true'
    
    answer = get_object_or_404(MockAnswer, uid=answer_uid, session=session)
    
    # Update answer
    if selected_option:
        answer.select_option(selected_option)
    
    answer.is_marked_for_review = is_marked
    answer.is_skipped = is_skipped
    answer.save()
    
    # Update current question index
    current_index = int(request.POST.get('current_index', 0))
    session.current_question_index = current_index
    session.save()
    
    return JsonResponse({'status': 'success'})

@login_required(login_url='/')
def submit_test(request, session_uid):

    session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
    
    if not session.is_completed:
        session.is_completed = True
        session.end_time = timezone.now()
        session.time_spent_seconds = int((session.end_time - session.start_time).total_seconds())
        session.terminated_by_user = True
        session.save()
        
        # Calculate score
        session.calculate_score()
    prev_answer_uid = request.POST.get('prev_que_uid')
    if prev_answer_uid:
        prev_answer = get_object_or_404(MockAnswer, uid=prev_answer_uid, session=session)
        prev_answer.nextqueprevtime()
    return redirect('mock_test_result', session_uid=session.uid)

@login_required(login_url='/')
def update_timer(request, session_uid):

    """Endpoint to update session timer and check if test should be auto-submitted"""
    session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
    
    if session.is_completed:
        return JsonResponse({
            'status': 'completed',
            'redirect_url': f'/mocktest/result/{session.uid}/'
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
            'status': 'timeout',
            'redirect_url': f'/mocktest/result/{session.uid}/'
        })
    
    return JsonResponse({
        'status': 'active',
        'time_remaining': int(time_remaining)
    })

@login_required(login_url='/')
def mock_test_result(request, session_uid):
    session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
    
    if not session.is_graded:
        session.calculate_score()
    
    # Get all completed sessions for this test to calculate percentile
    
    
    # Update percentile if not already calculated
    total_participants = session.update_percentile()
    
    # Get detailed answer data for review
    answers = session.answers.all().select_related('mcq')
    questions_with_answers = []
    
    for i, answer in enumerate(answers):
        questions_with_answers.append({
            'number': i + 1,
            'mcq': answer.mcq,
            'selected_option': answer.selected_option,
            'is_correct': answer.is_correct,
            'time_spent': answer.time_spent_seconds
        })
    
    context = {
        'session': session,
        'mock_test': session.mock_test,
        'questions': questions_with_answers,
        'total_questions': len(questions_with_answers),
        'percentile': session.percentile,
        'rank': session.rank,
        'total_participants': total_participants,
        
    }
    
    return render(request, 'mocktest/mock_test_result.html', context)

@login_required(login_url='/')
def mock_sessions_list(request,email_token):
    # Get all mock sessions for the current user
    completed_sessions = MockSession.objects.filter(
        user=request.user,
        is_completed=True
    ).order_by('-end_time')
    
    ongoing_sessions = MockSession.objects.filter(
        user=request.user,
        is_completed=False
    ).order_by('-start_time')
    
    context = {
        'completed_sessions': completed_sessions,
        'ongoing_sessions': ongoing_sessions,
        'current_time': timezone.now()
    }
    
    return render(request, 'mocktest/mock_sessions_list.html', context)

@login_required(login_url='/')
def mark_question_visible(request, session_uid):
    """
    Mark a question as visible and update its visible_at timestamp.
    
    """
    print(session_uid)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
    session = get_object_or_404(MockSession, uid=session_uid, user=request.user)
    
    if session.is_completed:
        return JsonResponse({'status': 'error', 'message': 'Test already completed'})
    
    answer_uid = request.POST.get('answer_uid')
    print(answer_uid)
    answer = get_object_or_404(MockAnswer, uid=answer_uid, session=session)
    answer.mark_visible()
    prev_answer_uid = request.POST.get('prev_que_uid')
    print("prev_",prev_answer_uid)
    if prev_answer_uid:
        prev_answer = get_object_or_404(MockAnswer, uid=prev_answer_uid, session=session)
        prev_answer.nextqueprevtime()
    
    
    
    return JsonResponse({'status': 'success'})



from django.shortcuts import render
from django.db.models import Count, Q
from .models import MockTest, MockSession
import datetime
from django.db.models.functions import Concat, Extract
from django.db.models import Value, Count, Q
from django.db import models
def format_seconds_to_time(seconds):
    """Helper function to format seconds into HH:MM:SS format"""
    if not seconds:
        return "00:00:00"
    
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
@login_required(login_url='/')
def top_performers_view(request, email_token):
    """
    View to display top performers for each mock test category
    Shows varying number of top performers based on total participants
    Includes filtering by date/month and user participation
    """
    # Get filter parameters from request
    month_year = request.GET.get('month_year', '')
    only_my_tests = request.GET.get('my_tests', '') == 'on'
    
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
                output_field=models.CharField()  # Specify the output field type
            )
        ).values('month_year').annotate(count=Count('uid')).order_by('-month_year')
    
    # Format the dates for display
    formatted_dates = []
    for date_obj in available_dates:
        try:
            year, month = map(int, date_obj['month_year'].split('-'))
            month_name = datetime.date(2000, month, 1).strftime('%B')
            formatted_dates.append({
                'value': date_obj['month_year'],
                'display': f"{month_name} {year}",
                'count': date_obj['count']
            })
        except (ValueError, IndexError):
            continue
    
    test_performers = []
    
    for test in mock_tests:
        # Determine how many top performers to show based on participant count
        top_count = 3  # Default
        
        if test.total_students >= 2500:
            top_count = 100
        elif test.total_students >= 1000:
            top_count = 50
        elif test.total_students >= 100:
            top_count = 10
        elif test.total_students >= 50:
            top_count = 5
        
        # Get top performers for this test
        top_sessions = MockSession.objects.filter(
            mock_test=test,
            is_completed=True,
            is_graded=True
        ).order_by('rank')[:top_count]
        
        # Format time for each session
        formatted_sessions = []
        for session in top_sessions:
            # Create a dictionary with session data including formatted time
            total_questions = test.total_mcqs if test.total_mcqs > 0 else 1
            max_score = total_questions * 4  # Assuming +4 for correct answers
            
            # Check if current user participated in this session
            is_current_user = session.user.id == request.user.id
            
            session_data = {
                'user': session.user,
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
        
        if formatted_sessions:
            test_performers.append({
                'test': test,
                'sessions': formatted_sessions,
                'total_participants': test.total_students,
                'top_count': top_count,
                'date': test.start_time,  # Include date for sorting within categories
                'user_participated': test.sessions.filter(user=request.user, is_completed=True).exists()
            })
    
    # Group by test category
    categories = {}
    for item in test_performers:
        category_name = item['test'].category.get_name_display()
        if category_name not in categories:
            categories[category_name] = []
        categories[category_name].append(item)
    
    # Sort each category to show most recent tests first
    for category, items in categories.items():
        categories[category] = sorted(items, key=lambda x: x['date'], reverse=True)
    
    context = {
        'categories': categories,
        'available_dates': formatted_dates,
        'selected_month_year': month_year,
        'only_my_tests': only_my_tests
    }
    
    return render(request, 'mocktest/top_performers.html', context)


from django.http import JsonResponse
from django.db.models import Sum
from django.contrib.auth.models import User
from mocktest.models import MockSession

def top_performers_api(request):
    """
    API endpoint to get the top 5 performers across all mock tests.
    Returns data formatted for the top performers display.
    """
    # Get users who have completed at least one mock test session
    user_statistics = MockSession.objects.filter(
        is_completed=True
    ).values(
        'user',
        'user__username'  # Keep username as fallback
    ).annotate(
        total_score=Sum('score'),
        total_correct=Sum('total_correct'),
        total_incorrect=Sum('total_incorrect'),
        total_skipped=Sum('total_skipped'),
        total_mcqs=Sum('mock_test__total_mcqs'),
        total_time_spent=Sum('time_spent_seconds')
    ).order_by('-total_score', 'total_time_spent')[:5]
    
    # Get user details separately
    user_ids = [stat['user'] for stat in user_statistics]
    users = User.objects.filter(id__in=user_ids)
    user_details = {}
    for user in users:
        user_details[user.id] = {
            'first_name': user.first_name,
            'last_name': user.last_name
        }
    
    # Format the response data
    top_performers = []
    for stat in user_statistics:
        # Calculate total_actual_mcqs after the query
        total_actual_mcqs = stat['total_correct'] + stat['total_incorrect'] + stat['total_skipped']
        
        # Calculate accuracy as percentage of correct answers out of attempted
        attempted = stat['total_correct'] + stat['total_incorrect']
        accuracy = round((stat['total_correct'] / max(attempted, 1)) * 100)
        
        # Get user details from our separate dict
        user_id = stat['user']
        user_detail = user_details.get(user_id, {})
        first_name = user_detail.get('first_name', '')
        last_name = user_detail.get('last_name', '')
        
        # Combine first and last name to get full name
        full_name = f"{first_name} {last_name}".strip()
        # If full name is empty, use username as fallback
        if not full_name:
            full_name = stat['user__username']
        
        top_performers.append({
            'user_id': user_id,
            'full_name': full_name,
            'total_score': stat['total_score'],
            'actual_max_score': total_actual_mcqs * 4,
            'max_possible_score': stat['total_mcqs'] * 4,
            'accuracy': accuracy,
            'correct_answers': stat['total_correct'],
            'incorrect_answers': stat['total_incorrect'],
            'time_spent': stat['total_time_spent'],  # in seconds
        })
    
    return JsonResponse(top_performers, safe=False)


from django.shortcuts import render
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
import json
import uuid

from mcqs.models import TestSession, TestAnswer
from mocktest.models import MockTest, MockTestMCQ
from mcqs.serializers import MCQSerializer  # Using your existing serializer

@login_required
@ensure_csrf_cookie
def start_mock_practice(request):
    """
    Start a practice session based on a mock test with flexible access control
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method is allowed'})
    
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        test_uid = data.get('test_uid')
        mode = data.get('mode', 'test')

        profile = request.user.profile
        
        profile = request.user.profile
        if profile.mock_current_test:
            messages.warning(request, "Your previous MockTest practice was not submitted. Please submit the pending test to start a new one.")

            return redirect('cont', test_id=profile.mock_current_test)
        if not test_uid:
            error_msg = 'Mock test UID is required'
            if is_ajax_request:
                return JsonResponse({'success': False, 'error': error_msg})
            else:
                messages.error(request, error_msg)
                return redirect('mock_tests_view', email_token=profile.email_token)

        try:
            mock_test = MockTest.objects.get(uid=test_uid)
        except MockTest.DoesNotExist:
            error_msg = 'Mock test not found'
            if is_ajax_request:
                return JsonResponse({'success': False, 'error': error_msg})
            else:
                messages.error(request, error_msg)
                return redirect('mock_tests_view', email_token=profile.email_token)

        mock_test_mcqs = MockTestMCQ.objects.filter(mock_test=mock_test).order_by('order')
        final_mcqs = [test_mcq.mcq for test_mcq in mock_test_mcqs]
        
        if not final_mcqs:
            error_msg = 'No MCQs found for this mock test'
            if is_ajax_request:
                return JsonResponse({'success': False, 'error': error_msg})
            else:
                messages.error(request, error_msg)
                return redirect('mock_tests_view', email_token=profile.email_token)

        final_mcqs_count = len(final_mcqs)
        
        # **SUBSCRIPTION CHECK**
        is_allowed, subscription_error, use_free_mcqs = check_user_subscription_for_mocktest_practice(
            request.user, 
            final_mcqs_count
        )
        
        if not is_allowed:
            logger.warning(f"Mock test practice access denied for {request.user.username}. "
                         f"Test: {mock_test.title}, MCQs needed: {final_mcqs_count}, "
                         f"Error: {subscription_error}")
            
            if is_ajax_request:
                return JsonResponse({
                    'success': False, 
                    'error': subscription_error,
                    'redirect_to_subscription': True,
                    'mcqs_needed': final_mcqs_count,
                    'free_mcqs_remaining': getattr(profile, 'free_mcqs_remaining', 0)
                }, status=403)
            else:
                messages.error(request, subscription_error)
                return redirect('mock_tests_view', email_token=profile.email_token)

        # Rest of your existing code for successful case...
        
        if use_free_mcqs:
            if not profile.can_attempt_test(final_mcqs_count):
                error_msg = f"Insufficient free MCQs. You need {final_mcqs_count} but only have {profile.free_mcqs_remaining} remaining."
                if is_ajax_request:
                    return JsonResponse({
                        'success': False,
                        'error': error_msg,
                        'redirect_to_subscription': True,
                        'mcqs_needed': final_mcqs_count,
                        'free_mcqs_remaining': profile.free_mcqs_remaining
                    }, status=403)
                else:
                    messages.error(request, error_msg)
                    return redirect('mock_tests_view', email_token=profile.email_token)
            
            profile.consume_free_mcqs(final_mcqs_count)
            logger.info(f"Consumed {final_mcqs_count} free MCQs for {request.user.username}")
        else:
            logger.info(f"User {request.user.username} starting unlimited mock test practice")
        
        # Create a unique test ID
        test_id = f"{request.user.id}_{uuid.uuid4()}"
        
        # Calculate time in seconds
        total_time_minutes = mock_test.time_limit_minutes
        total_time_seconds = total_time_minutes * 60
        
        # Format test name
        test_name = f"MOCK TEST - {mock_test.title}-{mock_test.get_test_type_display()}-{mock_test.category.get_name_display()}"
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
        
        mock_current_test = request.user.profile
        mock_current_test.mock_current_test = test_id
        mock_current_test.save()
        
        # Create test answers for each MCQ
        for mcq in final_mcqs:
            TestAnswer.objects.create(
                test_session=test_session,
                mcq_uid=mcq.uid
            )
        
        # Serialize MCQs for template using your existing serializer
        serializer = MCQSerializer(final_mcqs, many=True)

        # Return the appropriate template based on mode
        if mode == 'test':
            return render(request, 'mcq/mcq.html', {
                'mcqs': json.dumps(serializer.data), 
                'count': len(final_mcqs), 
                'test_id': test_id,
                'total_time': total_time_minutes,
                'mode': mode
            })
        else:
            return render(request, 'mcq/mcq2.html', {
                'mcqs': json.dumps(serializer.data), 
                'count': len(final_mcqs), 
                'test_id': test_id,
                'total_time': total_time_minutes,
                'mode': mode
            })
        
    except Exception as e:
        # Handle any exceptions
        logger.error(f"Error in start_mock_practice: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


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
    print(f"Checking subscription for category: '{mock_test_category}'")

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
            'NEET-PG Pattern': ('neet_pg_inicet', 'NEET-PG + INI-CET'),  # Correct key
            'INI-CET': ('neet_pg_inicet', 'NEET-PG + INI-CET'),
            'FMGE': ('fmge', 'FMGE'),
            'UPSC-CMS': ('upsc_cms', 'UPSC-CMS'),
        }
        print(f"Available category mappings: {list(category_mapping.keys())}")

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
            return True, "", True  # ✅ 3 values: allowed, no error, use free MCQs
        
        # Check if user has ANY active subscription (regardless of category)
        active_subscriptions = UserSubscription.get_all_active_subscriptions(user)
        
        if not active_subscriptions.exists():
            remaining_mcqs = getattr(profile, 'free_mcqs_remaining', 0)
            if remaining_mcqs > 0:
                error_msg = f"You need {mcq_count} free MCQs but only have {remaining_mcqs} remaining. Please upgrade to any plan for unlimited practice."
                return False, error_msg, False  # ✅ 3 values: not allowed, error message, don't use free MCQs
            else:
                error_msg = "You have no free attempts left and no active subscription. Please upgrade to any plan for unlimited mock test practice."
                return False, error_msg, False  # ✅ 3 values
        
        # Check if any subscription is not expired
        active_non_expired_subs = []
        for sub in active_subscriptions:
            if not sub.is_expired:
                active_non_expired_subs.append(sub)
        
        if not active_non_expired_subs:
            remaining_mcqs = getattr(profile, 'free_mcqs_remaining', 0)
            if remaining_mcqs >= mcq_count:
                return True, "", True  # ✅ 3 values: can use free MCQs
            elif remaining_mcqs > 0:
                error_msg = f"Your subscription has expired. You need {mcq_count} free MCQs but only have {remaining_mcqs} remaining."
                return False, error_msg, False  # ✅ 3 values
            else:
                error_msg = "Your subscription has expired and you have no free attempts left. Please renew your subscription."
                return False, error_msg, False  # ✅ 3 values
        
        # User has active subscription - unlimited practice
        sub_names = [sub.plan.get_category_display() for sub in active_non_expired_subs]
        logger.info(f"User {user.username} can practice with unlimited access. "
                   f"Active subscriptions: {', '.join(sub_names)}")
        return True, "", False  # ✅ 3 values: allowed, no error, don't use free MCQs (unlimited)
        
    except Exception as e:
        logger.error(f"Error checking mock test practice permission: {str(e)}", exc_info=True)
        error_msg = "Unable to verify your access. Please try again or contact support."
        return False, error_msg, False  # ✅ 3 values: not allowed, error message, don't use free MCQs


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
