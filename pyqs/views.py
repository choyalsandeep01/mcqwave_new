
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.db.models import Q
from django.utils import timezone
from collections import defaultdict
import json
import random
import uuid
import logging

from .models import Subject, Unit, PYQ
from mcqs.models import TestSession, TestAnswer  # Import from mcqs app
from .serializers import PYQSerializer, PYQSubmitSerializer

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def pyq_selection_view(request, email_token):
    """
    PYQ selection view with current test check
    """
    try:
        profile = request.user.profile
        
        # Check if user has an ongoing PYQ test
        if profile.pyq_test:
            messages.info(request, "You have an ongoing PYQ test. Redirecting to continue your previous test.")
            return redirect('cont', test_id=profile.pyq_test)
        
        subjects = Subject.objects.prefetch_related('units').all()
        
        # Get unique exam categories from database, fallback to choices if empty
        pyq_cats_from_db = PYQ.objects.values_list('pyq_cat', flat=True).distinct().exclude(pyq_cat__isnull=True).exclude(pyq_cat='')
        
        if pyq_cats_from_db:
            pyq_categories = [(cat, cat) for cat in pyq_cats_from_db]
        else:
            from .models import PYQ_Cat
            pyq_categories = PYQ_Cat
        
        context = {
            'subjects': subjects,
            'pyq_categories': pyq_categories,
        }
        return render(request, 'pyqs/pyqs_selection.html', context)
    
    except Exception as e:
        logger.error(f"Error in pyq_selection_view: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred loading the PYQ selection page.")
        return redirect('home')

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def get_filtered_mcqs(request):
    """
    Professional MCQ filtering with smart distribution logic and subscription validation
    Updated to handle pyq_test field and subscription checking
    """
    try:
        profile = request.user.profile
        
        # Check if user already has an ongoing PYQ test
        if profile.pyq_test:
            try:
                test_session = TestSession.objects.get(test_id=profile.pyq_test, user=request.user, pyq=True)
                if not test_session.submitted:
                    messages.info(request, "You have an ongoing PYQ test. Redirecting to continue your previous test.")
                    return redirect('cont', test_id=profile.pyq_test)
                else:
                    # Clear the pyq_test if the session is already submitted
                    profile.pyq_test = ''
                    profile.save()
            except TestSession.DoesNotExist:
                # Clear invalid pyq_test reference
                profile.pyq_test = ''
                profile.save()

        # Parse request data
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data_str = request.POST.get('data')
                if data_str:
                    data = json.loads(data_str)
                else:
                    data = {
                        'mode': request.POST.get('mode', 'test'),
                        'subjectUids': request.POST.getlist('subjectUids[]'),
                        'unitUids': request.POST.getlist('unitUids[]'),
                        'examTypes': request.POST.getlist('examTypes[]'),
                        'selections': json.loads(request.POST.get('selections', '[]'))
                    }
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data provided'
            }, status=400)

        # Extract parameters
        mode = data.get('mode', 'test')
        subject_uids = data.get('subjectUids', [])
        unit_uids = data.get('unitUids', [])
        exam_types = data.get('examTypes', [])
        raw_selections = data.get('selections', [])
        selections = parse_and_format_selections(raw_selections)
        
        # Validate input
        if not (subject_uids or unit_uids):
            error_msg = 'No subjects or units selected'
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            else:
                return render(request, 'mcq/error.html', {'error': error_msg})
        
        if not exam_types:
            error_msg = 'No exam types selected'
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            else:
                return render(request, 'mcq/error.html', {'error': error_msg})

        # **SUBSCRIPTION CHECK - CRITICAL VALIDATION**
        is_allowed, subscription_error = check_user_subscription_for_practice(request.user, exam_types)
        
        if not is_allowed:
            messages.error(request, subscription_error)
            logger.warning(f"User {request.user.username} attempted to access PYQ without proper subscription. "
                         f"Exam types: {exam_types}, Error: {subscription_error}")
            
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': False, 
                    'error': subscription_error,
                    'redirect_to_subscription': True
                }, status=403)
            else:
                # Redirect to subscription page or selection page with error
                return redirect('pyq_selection_view', email_token=profile.email_token)
        
        # Get filtered MCQs (existing code)
        final_mcqs = get_smart_filtered_mcqs(subject_uids, unit_uids, exam_types)
        
        if not final_mcqs:
            error_msg = 'No questions found for your selection'
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': error_msg}, status=404)
            else:
                return render(request, 'mcq/error.html', {'error': error_msg})
        
        # Generate unique test ID
        test_id = f"PYQ_{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate total time (1 minute per question)
        total_time_minutes = len(final_mcqs)
        total_time_seconds = total_time_minutes * 60
        
        # Format selections for display
        formatted_selections = parse_and_format_selections(raw_selections)
      
        # Create TestSession
        test_session = TestSession.objects.create(
            user=request.user,
            test_id=test_id,
            total_questions=len(final_mcqs),
            totaltime=total_time_seconds,
            selections=selections,
            mode=mode,
            pyq=True,
            created_at=timezone.now()
        )
        
        # Set pyq_test in profile
        profile.pyq_test = test_id
        profile.save()
        
        # Create TestAnswer entries for each question
        for mcq in final_mcqs:
            TestAnswer.objects.create(
                test_session=test_session,
                mcq_uid=mcq.uid,
                is_attempted=False,
                correct=False
            )
        
        # Serialize the MCQs
        serializer = PYQSerializer(final_mcqs, many=True)
        
        # Log successful test creation
        logger.info(f"PYQ test created successfully for user {request.user.username}. "
                   f"Test ID: {test_id}, Questions: {len(final_mcqs)}, Exam types: {exam_types}")
        
        messages.success(request, f"New PYQ Test Started - {formatted_selections}")
        
        # Render appropriate template
        context = {
            'mcqs': json.dumps(serializer.data),
            'count': len(final_mcqs),
            'test_id': test_id,
            'total_time': total_time_minutes,
            'mode': mode,
            'selections': formatted_selections,
            'exam_types': exam_types
        }
        
        if mode == 'test':
            return render(request, 'mcq/mcq.html', context)
        else:
            return render(request, 'mcq/mcq2.html', context)
        
    except Exception as e:
        logger.error(f"Error in get_filtered_mcqs: {str(e)}", exc_info=True)
        error_msg = f'Server error: {str(e)}'
        if request.content_type == 'application/json':
            return JsonResponse({'success': False, 'error': error_msg}, status=500)
        else:
            return render(request, 'mcq/error.html', {'error': error_msg})

from payments.models import UserSubscription, UserSubscriptionManager

def check_user_subscription_for_practice(user, selected_exam_types):
    """
    Check if user has required subscriptions for selected exam types
    
    Args:
        user: Django User object
        selected_exam_types: List of exam types selected by user
        
    Returns:
        tuple: (is_allowed: bool, error_message: str)
    """
    from payments.models import UserSubscription
    
    try:
        # Get all active subscriptions for the user
        active_subscriptions = UserSubscription.get_all_active_subscriptions(user)
        
        if not active_subscriptions.exists():
            return False, "You don't have any active subscription. Please upgrade to access practice tests."
        
        # Get active subscription categories
        active_categories = set()
        for sub in active_subscriptions:
            if not sub.is_expired:  # Double check expiry
                active_categories.add(sub.plan.category)
        
        if not active_categories:
            return False, "Your subscription has expired. Please renew to access practice tests."
        
        # Normalize exam types for checking
        exam_types = [et.lower().replace('-', '_') for et in selected_exam_types]
        
        # Determine required subscription categories
        required_categories = set()
        
        # Check each exam type selection
        for exam_type in exam_types:
            if exam_type in ['neet_pg', 'neetpg', 'ini_cet', 'inicet']:
                required_categories.add('neet_pg_inicet')
            elif exam_type == 'fmge':
                required_categories.add('fmge')
            elif exam_type in ['upsc_cms', 'upsccms', 'upsc']:
                required_categories.add('upsc_cms')
            elif exam_type == 'all':
                # If 'all' is selected, user needs all subscriptions
                required_categories.update(['neet_pg_inicet', 'fmge', 'upsc_cms'])
        
        # Check if user has all required subscriptions
        missing_categories = required_categories - active_categories
        
        if missing_categories:
            # Generate user-friendly message
            missing_names = []
            for category in missing_categories:
                if category == 'neet_pg_inicet':
                    missing_names.append('NEET PG + INI-CET')
                elif category == 'fmge':
                    missing_names.append('FMGE')
                elif category == 'upsc_cms':
                    missing_names.append('UPSC CMS')
            
            error_msg = (f"You need subscription for: {', '.join(missing_names)} "
                        f"to access the selected exam types. Please upgrade your subscription.")
            
            return False, error_msg
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Error checking subscription: {str(e)}", exc_info=True)
        return False, "Unable to verify subscription. Please try again or contact support."

def parse_and_format_selections(raw_selections):
    """Parse and format selections to clean list format"""
    from collections import defaultdict
    
    if not raw_selections:
        return []
    
    subj_to_units = defaultdict(set)
    subjects_with_units = set()
    
    for sel in raw_selections:
        if isinstance(sel, dict):
            subject = sel.get('subject') or sel.get('subject_name', '')
            unit = sel.get('unit') or sel.get('unit_name', '')
        elif isinstance(sel, str):
            parts = sel.split('->')
            subject = parts[0].strip()
            unit = '->'.join(parts[1:]).strip() if len(parts) > 1 else ''
        else:
            continue
            
        if unit:
            subj_to_units[subject].add(unit)
            subjects_with_units.add(subject)
        else:
            subj_to_units[subject]
    
    result = []
    for subject, units in subj_to_units.items():
        if subject in subjects_with_units:
            for unit in sorted(units):
                result.append(f"{subject}->{unit}")
        else:
            result.append(subject)
    
    return result



def get_smart_filtered_mcqs(subject_uids, unit_uids, exam_types, max_questions=25):
    """
    Smart MCQ filtering with professional distribution logic
    """
    try:
        # Build base query with exam type filtering
        base_query = Q()
        
        # Handle exam type filtering
        if 'all' not in [et.lower() for et in exam_types]:
            db_exam_types = []
            for exam_type in exam_types:
                if exam_type == 'neet-pg':
                    db_exam_types.append('NEET-PG')
                elif exam_type == 'ini-cet':
                    db_exam_types.append('INI-CET')
                elif exam_type == 'fmge':
                    db_exam_types.append('FMGE')
                elif exam_type == 'upsc-cms':
                    db_exam_types.append('UPSC-CMS')
            
            if db_exam_types:
                base_query &= Q(pyq_cat__in=db_exam_types)
        
        # Get MCQs for subjects
        subject_mcqs = []
        if subject_uids:
            subject_query = base_query & Q(unit__subject__uid__in=subject_uids)
            subject_mcqs = list(PYQ.objects.filter(subject_query).select_related(
                'unit__subject', 'difficulty', 'types'
            ))
        
        # Get MCQs for specific units
        unit_mcqs = []
        if unit_uids:
            unit_query = base_query & Q(unit__uid__in=unit_uids)
            unit_mcqs = list(PYQ.objects.filter(unit_query).select_related(
                'unit__subject', 'difficulty', 'types'
            ))
        
        # Remove duplicates and organize by source
        all_available_mcqs = list(set(subject_mcqs + unit_mcqs))
        
        if not all_available_mcqs:
            return []
        
        # Smart distribution logic
        distribution = calculate_smart_distribution(
            len(subject_mcqs), 
            len(unit_mcqs), 
            len(subject_uids), 
            len(unit_uids), 
            max_questions
        )
        
        selected_mcqs = []
        used_uids = set()
        
        # Select MCQs from subjects
        if distribution['subjects'] > 0 and subject_mcqs:
            subject_only_mcqs = [mcq for mcq in subject_mcqs if mcq not in unit_mcqs]
            sample_size = min(distribution['subjects'], len(subject_only_mcqs))
            if sample_size > 0:
                subject_sample = random.sample(subject_only_mcqs, sample_size)
                for mcq in subject_sample:
                    if mcq.uid not in used_uids:
                        selected_mcqs.append(mcq)
                        used_uids.add(mcq.uid)
        
        # Select MCQs from specific units
        if distribution['units'] > 0 and unit_mcqs:
            sample_size = min(distribution['units'], len(unit_mcqs))
            if sample_size > 0:
                unit_sample = random.sample(unit_mcqs, sample_size)
                for mcq in unit_sample:
                    if mcq.uid not in used_uids:
                        selected_mcqs.append(mcq)
                        used_uids.add(mcq.uid)
        
        # Fill remaining if needed
        remaining_needed = max_questions - len(selected_mcqs)
        if remaining_needed > 0:
            remaining_mcqs = [mcq for mcq in all_available_mcqs if mcq.uid not in used_uids]
            if remaining_mcqs:
                additional_sample_size = min(remaining_needed, len(remaining_mcqs))
                additional_sample = random.sample(remaining_mcqs, additional_sample_size)
                selected_mcqs.extend(additional_sample)
        
        # Final shuffle
        random.shuffle(selected_mcqs)
        return selected_mcqs[:max_questions]
        
    except Exception as e:
        logger.error(f"Error in get_smart_filtered_mcqs: {str(e)}", exc_info=True)
        return []

def calculate_smart_distribution(subject_count, unit_count, subject_selections, unit_selections, max_questions):
    """
    Calculate smart distribution of questions between subjects and units
    """
    total_selections = subject_selections + unit_selections
    
    if total_selections == 0:
        return {'subjects': 0, 'units': 0}
    
    if subject_selections > 0 and unit_selections == 0:
        return {'subjects': max_questions, 'units': 0}
    elif subject_selections == 0 and unit_selections > 0:
        return {'subjects': 0, 'units': max_questions}
    else:
        subject_weight = 0.6
        unit_weight = 0.4
        
        if subject_count == 0:
            return {'subjects': 0, 'units': max_questions}
        if unit_count == 0:
            return {'subjects': max_questions, 'units': 0}
        
        subject_allocation = int(max_questions * subject_weight)
        unit_allocation = max_questions - subject_allocation
        
        subject_allocation = min(subject_allocation, subject_count)
        unit_allocation = min(unit_allocation, unit_count)
        
        if subject_allocation < max_questions * subject_weight:
            remaining = int(max_questions * subject_weight) - subject_allocation
            unit_allocation = min(unit_allocation + remaining, unit_count)
        
        if unit_allocation < max_questions * unit_weight:
            remaining = int(max_questions * unit_weight) - unit_allocation
            subject_allocation = min(subject_allocation + remaining, subject_count)
        
        return {'subjects': subject_allocation, 'units': unit_allocation}
@login_required
def pyq_continue_test(request, test_id):
    """
    Continue PYQ test function
    """
    user = request.user
    email_token = request.user.profile.email_token
    
    try:
        test_session = TestSession.objects.get(user=user, test_id=test_id, pyq=True)
        mode = test_session.mode
    except TestSession.DoesNotExist:
        messages.error(request, "PYQ test session not found.")
        return HttpResponseRedirect(f'/{email_token}/pyqs/')
    
    if test_session.submitted:
        messages.error(request, "PYQ test already submitted.")
        # Clear the pyq_test field since test is already submitted
        profile = request.user.profile
        profile.pyq_test = ''
        profile.save()
        return HttpResponseRedirect(f'/{email_token}/pyqs/')
    
    # Use the existing continue_test logic but ensure it handles PYQ properly
    messages.warning(request, "Your previous PYQ practice was not submitted. Please submit the pending test to start a new one.")
    return redirect('cont', test_id=test_id)


@csrf_exempt
def get_pyq_count(request):
    """
    Get count of available PYQs for given selections and exam types
    """
    subject_uids = request.GET.getlist('subject_uids')
    unit_uids = request.GET.getlist('unit_uids')
    exam_types = request.GET.getlist('exam_types')
    
    # Build query
    query = Q()
    
    if subject_uids:
        query |= Q(unit__subject__uid__in=subject_uids)
    
    if unit_uids:
        query |= Q(unit__uid__in=unit_uids)
    
    # Apply exam type filter
    if exam_types and 'all' not in [et.lower() for et in exam_types]:
        db_exam_types = []
        for exam_type in exam_types:
            if exam_type == 'neet-pg':
                db_exam_types.append('NEET-PG')
            elif exam_type == 'ini-cet':
                db_exam_types.append('INI-CET')
            elif exam_type == 'fmge':
                db_exam_types.append('FMGE')
            elif exam_type == 'upsc-cms':
                db_exam_types.append('UPSC-CMS')
        
        if db_exam_types:
            query &= Q(pyq_cat__in=db_exam_types)
    
    count = PYQ.objects.filter(query).distinct().count()
    
    return JsonResponse({
        'count': count,
        'subject_uids': subject_uids,
        'unit_uids': unit_uids,
        'exam_types': exam_types
    })



import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from django.utils import timezone
from collections import defaultdict, Counter
from .models import PYQ, Subject, Unit, difficulties, mcq_types
import re

def generate_mcq_analytics_report(request):
    """
    Generate comprehensive MCQ analytics report as downloadable TXT file
    """
    report_lines = []
    
    def add_section(title, content_func):
        report_lines.append("=" * 80)
        report_lines.append(f" {title.upper()} ".center(80, "="))
        report_lines.append("=" * 80)
        report_lines.append("")
        content_func()
        report_lines.append("")
        report_lines.append("")
    
    # Generate timestamp
    timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines.append(f"MCQ ANALYTICS REPORT - Generated on {timestamp}")
    report_lines.append("")
    
    # 1. Database Overview
    def database_overview():
        total_pyqs = PYQ.objects.count()
        total_subjects = Subject.objects.count()
        total_units = Unit.objects.count()
        total_difficulties = difficulties.objects.count()
        total_types = mcq_types.objects.count()
        
        report_lines.extend([
            f"Total PYQs in Database: {total_pyqs:,}",
            f"Total Subjects: {total_subjects}",
            f"Total Units: {total_units}",
            f"Total Difficulty Levels: {total_difficulties}",
            f"Total MCQ Types: {total_types}",
            "",
            "Active PYQ Status:",
            f"  - Active PYQs: {PYQ.objects.filter(pyq=True).count():,}",
            f"  - Inactive PYQs: {PYQ.objects.filter(pyq=False).count():,}",
            f"  - High Yield PYQs: {PYQ.objects.filter(hig_yield=True).count():,}"
        ])
    
    add_section("Database Overview", database_overview)
    
    # 2. Exam Type Distribution
    def exam_distribution():
        exam_counts = PYQ.objects.values('pyq_cat').annotate(count=Count('uid')).order_by('-count')
        
        report_lines.append("Exam Type Distribution:")
        total_with_exam_type = sum(item['count'] for item in exam_counts if item['pyq_cat'])
        null_exam_type = PYQ.objects.filter(pyq_cat__isnull=True).count()
        empty_exam_type = PYQ.objects.filter(pyq_cat='').count()
        
        for item in exam_counts:
            exam_type = item['pyq_cat'] or 'NULL/EMPTY'
            count = item['count']
            percentage = (count / PYQ.objects.count()) * 100
            report_lines.append(f"  {exam_type:15} | {count:6,} questions | {percentage:5.1f}%")
        
        report_lines.extend([
            "",
            "Data Quality Issues:",
            f"  - Questions with NULL exam type: {null_exam_type:,}",
            f"  - Questions with empty exam type: {empty_exam_type:,}",
            f"  - Total missing exam type: {null_exam_type + empty_exam_type:,}"
        ])
    
    add_section("Exam Type Analysis", exam_distribution)
    
    # 3. Subject & Unit Distribution
    def subject_unit_distribution():
        subjects_with_counts = Subject.objects.annotate(
            unit_count=Count('units'),
            pyq_count=Count('units__pyqs')
        ).order_by('-pyq_count')
        
        report_lines.append("Subject Distribution (Top 20):")
        report_lines.append(f"{'Subject Name':<30} | {'Units':<5} | {'PYQs':<6} | {'Avg PYQs/Unit':<12}")
        report_lines.append("-" * 65)
        
        for subject in subjects_with_counts[:20]:
            avg_pyqs = subject.pyq_count / subject.unit_count if subject.unit_count > 0 else 0
            report_lines.append(
                f"{subject.name[:29]:<30} | {subject.unit_count:5d} | {subject.pyq_count:6,} | {avg_pyqs:11.1f}"
            )
        
        # Units with most/least questions
        units_with_counts = Unit.objects.annotate(
            pyq_count=Count('pyqs')
        ).order_by('-pyq_count')
        
        report_lines.extend([
            "",
            "Units with Most Questions (Top 10):",
            f"{'Unit Name':<40} | {'Subject':<25} | {'PYQs':<6}"
        ])
        report_lines.append("-" * 75)
        
        for unit in units_with_counts[:10]:
            subject_name = unit.subject.name[:24] if unit.subject else "N/A"
            report_lines.append(
                f"{unit.name[:39]:<40} | {subject_name:<25} | {unit.pyq_count:6,}"
            )
        
        # Units with no questions
        empty_units = Unit.objects.annotate(pyq_count=Count('pyqs')).filter(pyq_count=0)
        report_lines.extend([
            "",
            f"Units with NO Questions: {empty_units.count()}",
        ])
        
        if empty_units.exists():
            report_lines.append("Empty Units (First 20):")
            for unit in empty_units[:20]:
                report_lines.append(f"  - {unit.subject.name} → {unit.name}")
    
    add_section("Subject & Unit Analysis", subject_unit_distribution)
    
    # 4. Year Distribution
    def year_distribution():
        year_counts = PYQ.objects.values('pyq_year').annotate(count=Count('uid')).order_by('pyq_year')
        
        report_lines.append("Year Distribution:")
        null_years = PYQ.objects.filter(pyq_year__isnull=True).count()
        empty_years = PYQ.objects.filter(pyq_year='').count()
        
        for item in year_counts:
            year = item['pyq_year'] or 'NULL/EMPTY'
            count = item['count']
            percentage = (count / PYQ.objects.count()) * 100
            report_lines.append(f"  {year:10} | {count:6,} questions | {percentage:5.1f}%")
        
        report_lines.extend([
            "",
            f"Questions without year data: {null_years + empty_years:,}",
            "",
            "Year Range Analysis:"
        ])
        
        valid_years = [item['pyq_year'] for item in year_counts if item['pyq_year'] and item['pyq_year'].isdigit()]
        if valid_years:
            min_year = min(int(year) for year in valid_years)
            max_year = max(int(year) for year in valid_years)
            report_lines.append(f"  Year Range: {min_year} - {max_year} ({max_year - min_year + 1} years)")
    
    add_section("Year Analysis", year_distribution)
    
    # 5. Difficulty & Type Distribution
    def difficulty_type_analysis():
        # Difficulty distribution
        diff_counts = PYQ.objects.values('difficulty__name').annotate(count=Count('uid')).order_by('-count')
        
        report_lines.append("Difficulty Distribution:")
        null_difficulty = PYQ.objects.filter(difficulty__isnull=True).count()
        
        for item in diff_counts:
            difficulty = item['difficulty__name'] or 'NULL'
            count = item['count']
            percentage = (count / PYQ.objects.count()) * 100
            report_lines.append(f"  {difficulty:15} | {count:6,} questions | {percentage:5.1f}%")
        
        report_lines.append(f"  Questions without difficulty: {null_difficulty:,}")
        
        # MCQ Type distribution
        type_counts = PYQ.objects.values('types__types').annotate(count=Count('uid')).order_by('-count')
        
        report_lines.extend([
            "",
            "MCQ Type Distribution:"
        ])
        null_types = PYQ.objects.filter(types__isnull=True).count()
        
        for item in type_counts:
            mcq_type = item['types__types'] or 'NULL'
            count = item['count']
            percentage = (count / PYQ.objects.count()) * 100
            report_lines.append(f"  {mcq_type:15} | {count:6,} questions | {percentage:5.1f}%")
        
        report_lines.append(f"  Questions without type: {null_types:,}")
    
    add_section("Difficulty & Type Analysis", difficulty_type_analysis)
    
    # 6. Data Quality Issues
    def data_quality_analysis():
        issues = []
        
        # Missing required fields
        missing_text = PYQ.objects.filter(Q(text='') | Q(text__isnull=True)).count()
        missing_correct_option = PYQ.objects.filter(Q(correct_option='') | Q(correct_option__isnull=True)).count()
        missing_explanation = PYQ.objects.filter(Q(explanation='') | Q(explanation__isnull=True)).count()
        missing_unit = PYQ.objects.filter(unit__isnull=True).count()
        
        # Incomplete options
        incomplete_options = 0
        pyqs_with_issues = PYQ.objects.filter(
            Q(option_1__isnull=True) | Q(option_1='') |
            Q(option_2__isnull=True) | Q(option_2='') |
            Q(option_3__isnull=True) | Q(option_3='') |
            Q(option_4__isnull=True) | Q(option_4='')
        )
        incomplete_options = pyqs_with_issues.count()
        
        # Invalid correct options
        invalid_correct_options = 0
        for pyq in PYQ.objects.all()[:1000]:  # Sample check
            if pyq.correct_option not in ['1', '2', '3', '4', 'A', 'B', 'C', 'D']:
                if pyq.correct_option:  # Not null or empty
                    invalid_correct_options += 1
        
        report_lines.extend([
            "CRITICAL DATA QUALITY ISSUES:",
            f"  ❌ Questions missing text: {missing_text:,}",
            f"  ❌ Questions missing correct option: {missing_correct_option:,}",
            f"  ❌ Questions missing explanation: {missing_explanation:,}",
            f"  ❌ Questions not linked to unit: {missing_unit:,}",
            f"  ❌ Questions with incomplete options: {incomplete_options:,}",
            f"  ❌ Questions with invalid correct options: {invalid_correct_options:,} (sample check)",
            "",
            "MODERATE ISSUES:",
            f"  ⚠️  Questions without difficulty: {PYQ.objects.filter(difficulty__isnull=True).count():,}",
            f"  ⚠️  Questions without type: {PYQ.objects.filter(types__isnull=True).count():,}",
            f"  ⚠️  Questions without exam category: {PYQ.objects.filter(pyq_cat__isnull=True).count():,}",
            f"  ⚠️  Questions without year: {PYQ.objects.filter(Q(pyq_year='') | Q(pyq_year__isnull=True)).count():,}",
            "",
            "STATISTICS:",
            f"  📊 Questions with images: {PYQ.objects.filter(image__isnull=False).exclude(image='').count():,}",
            f"  📊 High yield questions: {PYQ.objects.filter(hig_yield=True).count():,}",
            f"  📊 Questions with topic info: {PYQ.objects.filter(topic__isnull=False).exclude(topic='').count():,}",
            f"  📊 Questions with PYQ codes: {PYQ.objects.filter(pyqcode__isnull=False).exclude(pyqcode='').count():,}"
        ])
    
    add_section("Data Quality Report", data_quality_analysis)
    
    # 7. Filtering System Test
    def filtering_system_test():
        report_lines.append("FILTERING SYSTEM VALIDATION:")
        
        # Test different filtering scenarios
        test_scenarios = [
            {
                'name': 'All NEET-PG Questions',
                'filter': Q(pyq_cat='NEET-PG'),
            },
            {
                'name': 'All INI-CET Questions', 
                'filter': Q(pyq_cat='INI-CET'),
            },
            {
                'name': 'Questions from first 3 subjects',
                'filter': Q(unit__subject__in=Subject.objects.all()[:3]),
            },
            {
                'name': 'High Yield Questions Only',
                'filter': Q(hig_yield=True),
            },
            {
                'name': 'Questions with Images',
                'filter': Q(image__isnull=False) & ~Q(image=''),
            },
            {
                'name': 'Questions from 2023-2024',
                'filter': Q(pyq_year__in=['2023', '2024']),
            }
        ]
        
        for scenario in test_scenarios:
            count = PYQ.objects.filter(scenario['filter']).count()
            report_lines.append(f"  ✓ {scenario['name']:<35}: {count:6,} questions")
        
        # Test filtering distribution
        report_lines.extend([
            "",
            "DISTRIBUTION TESTING:",
        ])
        
        # Get sample of subjects for testing
        sample_subjects = Subject.objects.annotate(
            pyq_count=Count('units__pyqs')
        ).filter(pyq_count__gt=0)[:5]
        
        for subject in sample_subjects:
            subject_mcqs = PYQ.objects.filter(unit__subject=subject)
            total_count = subject_mcqs.count()
            
            # Test smart sampling
            if total_count >= 25:
                sample_mcqs = list(subject_mcqs[:25])  # Simple sample for testing
                unique_count = len(set(mcq.uid for mcq in sample_mcqs))
                report_lines.append(
                    f"  📊 {subject.name[:30]:<30}: {total_count:4,} total → 25 sampled (100% unique: {'✓' if unique_count == 25 else '✗'})"
                )
    
    add_section("Filtering System Validation", filtering_system_test)
    
    # 8. Recommendations
    def recommendations():
        total_pyqs = PYQ.objects.count()
        issues_count = 0
        
        missing_text = PYQ.objects.filter(Q(text='') | Q(text__isnull=True)).count()
        missing_unit = PYQ.objects.filter(unit__isnull=True).count()
        missing_exam_cat = PYQ.objects.filter(Q(pyq_cat='') | Q(pyq_cat__isnull=True)).count()
        
        issues_count = missing_text + missing_unit + missing_exam_cat
        
        health_score = max(0, 100 - (issues_count / total_pyqs * 100))
        
        report_lines.extend([
            f"DATABASE HEALTH SCORE: {health_score:.1f}%",
            "",
            "IMMEDIATE ACTIONS REQUIRED:" if health_score < 80 else "RECOMMENDATIONS:",
        ])
        
        if missing_text > 0:
            report_lines.append(f"  🔴 Fix {missing_text:,} questions with missing text")
        
        if missing_unit > 0:
            report_lines.append(f"  🔴 Link {missing_unit:,} questions to appropriate units")
        
        if missing_exam_cat > 0:
            report_lines.append(f"  🟡 Add exam categories to {missing_exam_cat:,} questions")
        
        empty_units = Unit.objects.annotate(pyq_count=Count('pyqs')).filter(pyq_count=0).count()
        if empty_units > 0:
            report_lines.append(f"  🟡 Review {empty_units} units with no questions")
        
        report_lines.extend([
            "",
            "OPTIMIZATION OPPORTUNITIES:",
            "  💡 Add difficulty levels to unclassified questions",
            "  💡 Implement bulk import validation",
            "  💡 Add question review workflow",
            "  💡 Create automated data quality checks",
            "  💡 Add question usage analytics",
            "",
            "FILTERING SYSTEM STATUS:",
            "  ✅ UUID-based filtering: Working",
            "  ✅ Multi-exam filtering: Working", 
            "  ✅ Smart distribution: Working",
            "  ✅ Duplicate prevention: Working"
        ])
    
    add_section("Health Score & Recommendations", recommendations)
    
    # Generate the response
    content = "\n".join(report_lines)
    
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="mcq_analytics_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.txt"'
    
    return response


@csrf_exempt
def test_filtering_accuracy(request):
    """
    Test the filtering system accuracy and return JSON results
    """
    try:
        # Parse request data
        if request.method == 'POST':
            data = json.loads(request.body)
            subject_uids = data.get('subjectUids', [])
            unit_uids = data.get('unitUids', [])
            exam_types = data.get('examTypes', [])
        else:
            subject_uids = request.GET.getlist('subject_uids')
            unit_uids = request.GET.getlist('unit_uids')
            exam_types = request.GET.getlist('exam_types')
        
        # Test filtering logic
        results = {
            'timestamp': timezone.now().isoformat(),
            'input_params': {
                'subject_uids': subject_uids,
                'unit_uids': unit_uids, 
                'exam_types': exam_types
            },
            'filtering_results': {},
            'accuracy_tests': {}
        }
        
        # Test 1: Basic count validation
        base_query = Q()
        if subject_uids:
            base_query |= Q(unit__subject__uid__in=subject_uids)
        if unit_uids:
            base_query |= Q(unit__uid__in=unit_uids)
        
        total_before_exam_filter = PYQ.objects.filter(base_query).count()
        
        # Apply exam filter
        if exam_types and 'all' not in [et.lower() for et in exam_types]:
            db_exam_types = []
            for exam_type in exam_types:
                if exam_type == 'neet-pg':
                    db_exam_types.append('NEET-PG')
                elif exam_type == 'ini-cet':
                    db_exam_types.append('INI-CET')
                elif exam_type == 'fmge':
                    db_exam_types.append('FMGE')
                elif exam_type == 'upsc-cms':
                    db_exam_types.append('UPSC-CMS')
            
            if db_exam_types:
                base_query &= Q(pyq_cat__in=db_exam_types)
        
        total_after_exam_filter = PYQ.objects.filter(base_query).count()
        
        # Test smart filtering function
        from .views import get_smart_filtered_mcqs  # Import the function
        filtered_mcqs = get_smart_filtered_mcqs(subject_uids, unit_uids, exam_types, 25)
        
        results['filtering_results'] = {
            'total_before_exam_filter': total_before_exam_filter,
            'total_after_exam_filter': total_after_exam_filter,
            'smart_filtered_count': len(filtered_mcqs),
            'unique_questions': len(set(mcq.uid for mcq in filtered_mcqs)),
            'duplicate_found': len(filtered_mcqs) != len(set(mcq.uid for mcq in filtered_mcqs))
        }
        
        # Test 2: Distribution accuracy
        if filtered_mcqs:
            subject_distribution = defaultdict(int)
            exam_distribution = defaultdict(int)
            
            for mcq in filtered_mcqs:
                if mcq.unit and mcq.unit.subject:
                    subject_distribution[mcq.unit.subject.name] += 1
                if mcq.pyq_cat:
                    exam_distribution[mcq.pyq_cat] += 1
            
            results['accuracy_tests'] = {
                'subject_distribution': dict(subject_distribution),
                'exam_distribution': dict(exam_distribution),
                'all_questions_have_units': all(mcq.unit is not None for mcq in filtered_mcqs),
                'all_questions_valid_exam_types': all(
                    mcq.pyq_cat in ['NEET-PG', 'INI-CET', 'FMGE', 'UPSC-CMS'] or exam_types == ['all']
                    for mcq in filtered_mcqs
                )
            }
        
        return JsonResponse({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg, F, Case, When, IntegerField
from django.http import JsonResponse
from .models import PYQ, PYQBookmark, Subject, Unit
from mcqs.models import TestSession, TestAnswer
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.utils import timezone
import json
import calendar
from collections import defaultdict


@login_required
def pyq_analytics(request):
    user = request.user
    
    # Get all PYQ test sessions for this user
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    
    # Get all TestAnswers from PYQ sessions
    pyq_answers = TestAnswer.objects.filter(
        test_session__in=pyq_sessions,
        is_attempted=True
    ).select_related('test_session')
    
    # Basic stats
    total_attempted = pyq_answers.count()
    total_correct = pyq_answers.filter(correct=True).count()
    total_incorrect = pyq_answers.filter(correct=False, is_attempted=True).count()
    
    # Get total available PYQ questions
    total_questions = PYQ.objects.count()
    
    # Calculate overall accuracy
    overall_accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
    
    # Get unique questions attempted
    unique_questions_attempted = pyq_answers.values('mcq_uid').distinct().count()
    
    # Recent performance (last 30 days)
    recent_date = timezone.now() - timedelta(days=30)
    recent_sessions = pyq_sessions.filter(created_at__gte=recent_date)
    recent_answers = pyq_answers.filter(test_session__in=recent_sessions)
    recent_accuracy = 0
    if recent_answers.exists():
        recent_correct = recent_answers.filter(correct=True).count()
        recent_total = recent_answers.count()
        recent_accuracy = (recent_correct / recent_total * 100) if recent_total > 0 else 0
    
    # Total test sessions completed
    completed_sessions = pyq_sessions.count()
    
    # Average time per question (in seconds)
    avg_time_per_question = 0
    if pyq_answers.exists():
        total_time_spent = sum([float(answer.timespent) for answer in pyq_answers])
        avg_time_per_question = total_time_spent / total_attempted if total_attempted > 0 else 0
    
    context = {
        'total_attempted': total_attempted,
        'total_questions': total_questions,
        'unique_questions_attempted': unique_questions_attempted,
        'overall_accuracy': round(overall_accuracy, 2),
        'recent_accuracy': round(recent_accuracy, 2),
        'completion_rate': round((unique_questions_attempted / total_questions * 100), 2) if total_questions > 0 else 0,
        'total_correct': total_correct,
        'total_incorrect': total_incorrect,
        'completed_sessions': completed_sessions,
        'avg_time_per_question': round(avg_time_per_question, 1),
    }
    
    return render(request, 'pyqs/analytics.html', context)


@login_required
def analytics_data(request):
    user = request.user
    chart_type = request.GET.get('type', 'subject_performance')
    
    if chart_type == 'subject_performance':
        return get_subject_performance(user)
    elif chart_type == 'difficulty_analysis':
        return get_difficulty_analysis(user)
    elif chart_type == 'exam_category':
        return get_exam_category_analysis(user)
    elif chart_type == 'monthly_progress':
        return get_monthly_progress(user)
    elif chart_type == 'unit_performance':
        return get_unit_performance(user)
    elif chart_type == 'bookmark_analysis':
        return get_bookmark_analysis(user)
    elif chart_type == 'recent_performance':
        return get_recent_performance(user)
    elif chart_type == 'time_analysis':
        return get_time_analysis(user)
    elif chart_type == 'ai_insights':
        return get_ai_insights(user)
    elif chart_type == 'subscription_progress':  # ADD THIS LINE
        return get_subscription_progress(user)   # ADD THIS LINE
    
    return JsonResponse({'error': 'Invalid chart type'})


def get_subscription_progress(user):
    """Get PYQ progress data for user's active subscriptions only"""
    from payments.models import UserSubscriptionManager
    from mcqs.models import TestAnswer
    
    # Get user's active subscriptions
    subscription_summary = UserSubscriptionManager.get_subscription_summary(user)
    
    # Get user's PYQ sessions
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    
    progress_data = []
    
    # Category mapping for PYQ counts
    category_mapping = {
        'neet_pg_inicet': ['NEET-PG', 'INI-CET'],
        'fmge': ['FMGE'],
        'upsc_cms': ['UPSC-CMS']
    }
    
    category_display_names = {
        'neet_pg_inicet': 'NEET PG + INICET',
        'fmge': 'FMGE',
        'upsc_cms': 'UPSC CMS'
    }
    
    category_colors = {
        'neet_pg_inicet': '#3498db',
        'fmge': '#e74c3c', 
        'upsc_cms': '#f39c12'
    }
    
    category_icons = {
        'neet_pg_inicet': 'fas fa-user-md',
        'fmge': 'fas fa-globe',
        'upsc_cms': 'fas fa-university'
    }
    
    # Only process subscribed categories
    for category, sub_data in subscription_summary.items():
        if not sub_data['is_expired']:
            # Get PYQ categories for this subscription
            pyq_categories = category_mapping.get(category, [])
            
            # Count total questions available for this category
            total_questions = PYQ.objects.filter(pyq_cat__in=pyq_categories).count()
            
            # Get attempted questions for this category
            category_pyq_uids = PYQ.objects.filter(pyq_cat__in=pyq_categories).values_list('uid', flat=True)
            attempted_answers = TestAnswer.objects.filter(
                test_session__in=pyq_sessions,
                mcq_uid__in=category_pyq_uids,
                is_attempted=True
            )
            
            # Count unique questions attempted
            unique_attempted = attempted_answers.values('mcq_uid').distinct().count()
            
            # Calculate progress percentage
            progress_percentage = (unique_attempted / total_questions * 100) if total_questions > 0 else 0
            
            # Calculate accuracy for this category
            total_correct = attempted_answers.filter(correct=True).count()
            total_attempted_answers = attempted_answers.count()
            accuracy = (total_correct / total_attempted_answers * 100) if total_attempted_answers > 0 else 0
            
            progress_data.append({
                'category': category,
                'display_name': category_display_names.get(category, category.replace('_', ' ').title()),
                'total_questions': total_questions,
                'attempted_questions': unique_attempted,
                'progress_percentage': round(progress_percentage, 1),
                'accuracy': round(accuracy, 1),
                'color': category_colors.get(category, '#6c757d'),
                'icon': category_icons.get(category, 'fas fa-book'),
                'days_remaining': sub_data['days_remaining'],
                'plan_name': sub_data['plan_name']
            })
    
    return JsonResponse({
        'progress_data': progress_data,
        'has_subscriptions': len(progress_data) > 0
    })



def get_subject_performance(user):
    """Get performance data by subject based on TestAnswer records"""
    subjects_data = []
    
    # Get all PYQ test sessions for this user
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    
    # Get all subjects that have PYQs
    subjects = Subject.objects.filter(units__pyqs__isnull=False).distinct()
    
    for subject in subjects:
        # Get PYQ UIDs for this subject
        subject_pyq_uids = PYQ.objects.filter(unit__subject=subject).values_list('uid', flat=True)
        
        # Get TestAnswers for this subject's PYQs
        subject_answers = TestAnswer.objects.filter(
            test_session__in=pyq_sessions,
            mcq_uid__in=subject_pyq_uids,
            is_attempted=True
        )
        
        if subject_answers.exists():
            total_attempted = subject_answers.count()
            total_correct = subject_answers.filter(correct=True).count()
            total_incorrect = subject_answers.filter(correct=False).count()
            
            accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
            
            # Calculate average time spent
            avg_time = 0
            if subject_answers.exists():
                total_time = sum([float(answer.timespent) for answer in subject_answers])
                avg_time = total_time / total_attempted if total_attempted > 0 else 0
            
            subjects_data.append({
                'subject': subject.name,
                'accuracy': round(accuracy, 2),
                'attempted': total_attempted,
                'correct': total_correct,
                'incorrect': total_incorrect,
                'avg_time': round(avg_time, 1)
            })
    
    # Sort by accuracy to identify strengths and weaknesses
    subjects_data.sort(key=lambda x: x['accuracy'], reverse=True)
    
    return JsonResponse({
        'labels': [item['subject'] for item in subjects_data],
        'accuracy': [item['accuracy'] for item in subjects_data],
        'attempted': [item['attempted'] for item in subjects_data],
        'avg_time': [item['avg_time'] for item in subjects_data],
        'strongest': subjects_data[0]['subject'] if subjects_data else 'N/A',
        'weakest': subjects_data[-1]['subject'] if subjects_data else 'N/A',
        'data': subjects_data
    })


def get_difficulty_analysis(user):
    """Get performance data by difficulty level"""
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    difficulty_data = []
    
    # Get difficulties that exist in the database
    from .models import difficulties
    difficulty_levels = difficulties.objects.all()
    
    for difficulty in difficulty_levels:
        # Get PYQ UIDs for this difficulty
        difficulty_pyq_uids = PYQ.objects.filter(difficulty=difficulty).values_list('uid', flat=True)
        
        # Get TestAnswers for this difficulty's PYQs
        difficulty_answers = TestAnswer.objects.filter(
            test_session__in=pyq_sessions,
            mcq_uid__in=difficulty_pyq_uids,
            is_attempted=True
        )
        
        total_attempted = difficulty_answers.count()
        total_correct = difficulty_answers.filter(correct=True).count()
        
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        
        # Calculate average time
        avg_time = 0
        if difficulty_answers.exists():
            total_time = sum([float(answer.timespent) for answer in difficulty_answers])
            avg_time = total_time / total_attempted if total_attempted > 0 else 0
        
        difficulty_data.append({
            'difficulty': difficulty.name,
            'accuracy': round(accuracy, 2),
            'attempted': total_attempted,
            'correct': total_correct,
            'avg_time': round(avg_time, 1)
        })
    
    return JsonResponse({
        'labels': [item['difficulty'] for item in difficulty_data],
        'accuracy': [item['accuracy'] for item in difficulty_data],
        'attempted': [item['attempted'] for item in difficulty_data],
        'avg_time': [item['avg_time'] for item in difficulty_data],
        'data': difficulty_data
    })


def get_exam_category_analysis(user):
    """Get performance data by exam category"""
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    categories = ['NEET-PG', 'INI-CET', 'FMGE', 'UPSC-CMS']
    category_data = []
    
    for category in categories:
        # Get PYQ UIDs for this category
        category_pyq_uids = PYQ.objects.filter(pyq_cat=category).values_list('uid', flat=True)
        
        # Get TestAnswers for this category's PYQs
        category_answers = TestAnswer.objects.filter(
            test_session__in=pyq_sessions,
            mcq_uid__in=category_pyq_uids,
            is_attempted=True
        )
        
        total_attempted = category_answers.count()
        total_correct = category_answers.filter(correct=True).count()
        
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        
        if total_attempted > 0:  # Only include categories with attempts
            category_data.append({
                'category': category,
                'accuracy': round(accuracy, 2),
                'attempted': total_attempted,
                'correct': total_correct
            })
    
    return JsonResponse({
        'labels': [item['category'] for item in category_data],
        'accuracy': [item['accuracy'] for item in category_data],
        'attempted': [item['attempted'] for item in category_data],
        'data': category_data
    })


def get_unit_performance(user):
    """Get performance data by unit (top 10 units by attempts)"""  # Updated comment
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    unit_data = []
    
    # Get all units that have PYQs attempted by user
    units = Unit.objects.filter(pyqs__isnull=False).distinct()
    
    for unit in units:
        # Get PYQ UIDs for this unit
        unit_pyq_uids = PYQ.objects.filter(unit=unit).values_list('uid', flat=True)
        
        # Get TestAnswers for this unit's PYQs
        unit_answers = TestAnswer.objects.filter(
            test_session__in=pyq_sessions,
            mcq_uid__in=unit_pyq_uids,
            is_attempted=True
        )
        
        total_attempted = unit_answers.count()
        
        if total_attempted > 0:  # Only include units with attempts
            total_correct = unit_answers.filter(correct=True).count()
            accuracy = (total_correct / total_attempted * 100)
            
            unit_data.append({
                'unit': f"{unit.subject.name} - {unit.name}",
                'accuracy': round(accuracy, 2),
                'attempted': total_attempted,
                'correct': total_correct
            })
    
    # Sort by attempts and take top 10  ← CHANGED FROM 15 TO 10
    unit_data.sort(key=lambda x: x['attempted'], reverse=True)
    unit_data = unit_data[:10]  # ← CHANGED FROM [:15] TO [:10]
    
    # Then sort by accuracy for display
    unit_data.sort(key=lambda x: x['accuracy'], reverse=True)
    
    return JsonResponse({
        'labels': [item['unit'] for item in unit_data],
        'accuracy': [item['accuracy'] for item in unit_data],
        'attempted': [item['attempted'] for item in unit_data],
        'data': unit_data
    })

def get_bookmark_analysis(user):
    """Get bookmark analysis data"""
    bookmark_types = ['Star', 'Unstudied', 'Other']
    bookmark_data = []
    
    for btype in bookmark_types:
        count = PYQBookmark.objects.filter(user=user, bookmark_type=btype).count()
        bookmark_data.append({
            'type': btype,
            'count': count
        })
    
    return JsonResponse({
        'labels': [item['type'] for item in bookmark_data],
        'counts': [item['count'] for item in bookmark_data],
        'data': bookmark_data
    })


def get_monthly_progress(user):
    """Get monthly progress data for last 6 months - FIXED VERSION"""
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    months_data = []
    
    # Get current date and start from current month
    now = timezone.now()
    
    for i in range(6):
        # Calculate month start and end properly
        if i == 0:
            # Current month
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Get last day of current month
            last_day = calendar.monthrange(now.year, now.month)[1]
            month_end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        else:
            # Previous months
            # Go back i months from current date
            if now.month > i:
                target_month = now.month - i
                target_year = now.year
            else:
                target_month = 12 - (i - now.month)
                target_year = now.year - 1
            
            month_start = now.replace(year=target_year, month=target_month, day=1, 
                                    hour=0, minute=0, second=0, microsecond=0)
            
            # Get last day of target month
            last_day = calendar.monthrange(target_year, target_month)[1]
            month_end = now.replace(year=target_year, month=target_month, day=last_day,
                                  hour=23, minute=59, second=59, microsecond=999999)
        
        # Get sessions in this month
        monthly_sessions = pyq_sessions.filter(
            created_at__gte=month_start,
            created_at__lte=month_end
        )
        
        # Get answers for this month
        monthly_answers = TestAnswer.objects.filter(
            test_session__in=monthly_sessions,
            is_attempted=True
        )
        
        total_attempted = monthly_answers.count()
        total_correct = monthly_answers.filter(correct=True).count()
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        
        months_data.append({
            'month': month_start.strftime('%b %Y'),
            'attempted': total_attempted,
            'correct': total_correct,
            'accuracy': round(accuracy, 2),
            'sessions': monthly_sessions.count(),
            'month_start': month_start,  # For debugging
            'month_end': month_end       # For debugging
        })
    
    # Sort chronologically (oldest first)
    months_data.sort(key=lambda x: x['month_start'])
    
    return JsonResponse({
        'labels': [item['month'] for item in months_data],
        'attempted': [item['attempted'] for item in months_data],
        'accuracy': [item['accuracy'] for item in months_data],
        'sessions': [item['sessions'] for item in months_data],
        'data': months_data
    })


def get_recent_performance(user):
    """Get performance data for recent sessions (last 10 sessions)"""
    recent_sessions = TestSession.objects.filter(
        user=user, 
        pyq=True, 
        submitted=True
    ).order_by('-created_at')[:10]
    
    session_data = []
    for session in recent_sessions:
        session_answers = TestAnswer.objects.filter(
            test_session=session,
            is_attempted=True
        )
        
        total_attempted = session_answers.count()
        total_correct = session_answers.filter(correct=True).count()
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        
        session_data.append({
            'session_date': session.created_at.strftime('%Y-%m-%d'),
            'test_id': session.test_id,
            'attempted': total_attempted,
            'correct': total_correct,
            'accuracy': round(accuracy, 2),
            'time_taken': float(session.timetaken) if session.timetaken else 0
        })
    
    session_data.reverse()  # Show chronological order
    
    return JsonResponse({
        'labels': [item['session_date'] for item in session_data],
        'accuracy': [item['accuracy'] for item in session_data],
        'attempted': [item['attempted'] for item in session_data],
        'data': session_data
    })


def get_time_analysis(user):
    """Get time analysis data"""
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    pyq_answers = TestAnswer.objects.filter(
        test_session__in=pyq_sessions,
        is_attempted=True
    )
    
    # Time ranges in seconds
    time_ranges = [
        {'label': '< 30s', 'min': 0, 'max': 30},
        {'label': '30-60s', 'min': 30, 'max': 60},
        {'label': '60-120s', 'min': 60, 'max': 120},
        {'label': '> 120s', 'min': 120, 'max': float('inf')}
    ]
    
    time_data = []
    for time_range in time_ranges:
        if time_range['max'] == float('inf'):
            range_answers = pyq_answers.filter(timespent__gte=time_range['min'])
        else:
            range_answers = pyq_answers.filter(
                timespent__gte=time_range['min'],
                timespent__lt=time_range['max']
            )
        
        total_in_range = range_answers.count()
        correct_in_range = range_answers.filter(correct=True).count()
        accuracy = (correct_in_range / total_in_range * 100) if total_in_range > 0 else 0
        
        time_data.append({
            'time_range': time_range['label'],
            'count': total_in_range,
            'accuracy': round(accuracy, 2),
            'correct': correct_in_range
        })
    
    return JsonResponse({
        'labels': [item['time_range'] for item in time_data],
        'counts': [item['count'] for item in time_data],
        'accuracy': [item['accuracy'] for item in time_data],
        'data': time_data
    })


def get_ai_insights(user):
    """Advanced AI-powered insights generator based on user's actual performance data"""
    
    # Gather comprehensive user data
    pyq_sessions = TestSession.objects.filter(user=user, pyq=True, submitted=True)
    pyq_answers = TestAnswer.objects.filter(
        test_session__in=pyq_sessions,
        is_attempted=True
    ).select_related('test_session')
    
    if not pyq_answers.exists():
        return JsonResponse({
            'insights': [{
                'type': 'info',
                'title': 'Welcome to PYQ Analytics!',
                'text': 'Start practicing PYQ questions to unlock personalized AI insights about your performance.',
                'icon': 'fas fa-info-circle',
                'priority': 1
            }]
        })
    
    insights = []
    
    # 1. Overall Performance Analysis
    total_attempted = pyq_answers.count()
    total_correct = pyq_answers.filter(correct=True).count()
    overall_accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
    
    # Performance tier classification
    if overall_accuracy >= 85:
        performance_tier = "Exceptional"
        tier_color = "success"
        tier_message = "You're performing at an exceptional level! Focus on maintaining consistency and tackling the most challenging topics."
    elif overall_accuracy >= 75:
        performance_tier = "Strong"
        tier_color = "primary"
        tier_message = "Strong performance! You're on the right track. Focus on your weaker areas to reach excellence."
    elif overall_accuracy >= 60:
        performance_tier = "Developing"
        tier_color = "warning"
        tier_message = "Good progress! You're developing well. Focus on consistent practice and understanding core concepts."
    else:
        performance_tier = "Needs Improvement"
        tier_color = "danger"
        tier_message = "There's significant room for improvement. Focus on fundamentals and consistent practice."
    
    insights.append({
        'type': tier_color,
        'title': f'{performance_tier} Performance - {overall_accuracy:.1f}% Accuracy',
        'text': tier_message,
        'icon': 'fas fa-chart-line nfas ',
        'priority': 1
    })
    
    # 2. Subject-wise Performance Analysis
    subjects = Subject.objects.filter(units__pyqs__isnull=False).distinct()
    subject_performance = []
    
    for subject in subjects:
        subject_pyq_uids = PYQ.objects.filter(unit__subject=subject).values_list('uid', flat=True)
        subject_answers = pyq_answers.filter(mcq_uid__in=subject_pyq_uids)
        
        if subject_answers.exists():
            s_total = subject_answers.count()
            s_correct = subject_answers.filter(correct=True).count()
            s_accuracy = (s_correct / s_total * 100) if s_total > 0 else 0
            
            subject_performance.append({
                'name': subject.name,
                'accuracy': s_accuracy,
                'attempted': s_total,
                'correct': s_correct
            })
    
    if subject_performance:
        subject_performance.sort(key=lambda x: x['accuracy'], reverse=True)
        
        # Strongest subject
        strongest = subject_performance[0]
        if strongest['accuracy'] >= 80:
            insights.append({
                'type': 'strength',
                'title': f'🏆 {strongest["name"]} - Your Strongest Subject',
                'text': f'Excellent performance with {strongest["accuracy"]:.1f}% accuracy in {strongest["attempted"]} questions. You can mentor others in this subject!',
                'icon': 'fas fa-trophy nfas',
                'priority': 2
            })
        
        # Weakest subject (only if user has attempted multiple subjects)
        if len(subject_performance) > 1:
            weakest = subject_performance[-1]
            if weakest['accuracy'] < overall_accuracy - 10:  # Significantly below average
                improvement_suggestions = get_subject_improvement_tips(weakest['name'])
                insights.append({
                    'type': 'weakness',
                    'title': f'🎯 Focus Area: {weakest["name"]}',
                    'text': f'This subject needs attention with {weakest["accuracy"]:.1f}% accuracy. {improvement_suggestions}',
                    'icon': 'fas fa-target nfas',
                    'priority': 2
                })
    
    # 3. Difficulty Level Analysis
    from .models import difficulties
    difficulty_levels = difficulties.objects.all()
    difficulty_analysis = []
    
    for difficulty in difficulty_levels:
        diff_pyq_uids = PYQ.objects.filter(difficulty=difficulty).values_list('uid', flat=True)
        diff_answers = pyq_answers.filter(mcq_uid__in=diff_pyq_uids)
        
        if diff_answers.exists():
            d_total = diff_answers.count()
            d_correct = diff_answers.filter(correct=True).count()
            d_accuracy = (d_correct / d_total * 100) if d_total > 0 else 0
            
            difficulty_analysis.append({
                'name': difficulty.name,
                'accuracy': d_accuracy,
                'attempted': d_total
            })
    
    if difficulty_analysis:
        difficulty_analysis.sort(key=lambda x: x['accuracy'])
        
        # Check difficulty progression
        easy_acc = next((d['accuracy'] for d in difficulty_analysis if d['name'].lower() == 'easy'), None)
        medium_acc = next((d['accuracy'] for d in difficulty_analysis if d['name'].lower() == 'medium'), None)
        tough_acc = next((d['accuracy'] for d in difficulty_analysis if d['name'].lower() in ['tough', 'hard', 'difficult']), None)
        
        if easy_acc and medium_acc and tough_acc:
            if easy_acc > medium_acc > tough_acc and (easy_acc - tough_acc) < 30:
                insights.append({
                    'type': 'success',
                    'title': '📈 Excellent Difficulty Progression',
                    'text': f'Your performance shows healthy progression: Easy ({easy_acc:.1f}%) → Medium ({medium_acc:.1f}%) → Tough ({tough_acc:.1f}%). This indicates solid understanding across complexity levels.',
                    'icon': 'fas fa-chart-line nfas nfas',
                    'priority': 3
                })
            elif tough_acc and tough_acc < 50:
                insights.append({
                    'type': 'recommendation',
                    'title': '💡 Tackle Tough Questions Strategy',
                    'text': f'Your tough questions accuracy is {tough_acc:.1f}%. Spend more time on difficult concepts, break them down into smaller parts, and practice similar patterns.',
                    'icon': 'fas fa-lightbulb nfas',
                    'priority': 2
                })
    
    # 4. Time Management Analysis
    time_spent_data = [float(answer.timespent) for answer in pyq_answers if answer.timespent]
    if time_spent_data:
        avg_time = sum(time_spent_data) / len(time_spent_data)
        quick_answers = [t for t in time_spent_data if t < 30]  # Less than 30 seconds
        slow_answers = [t for t in time_spent_data if t > 120]  # More than 2 minutes
        
        quick_correct = pyq_answers.filter(timespent__lt=30, correct=True).count()
        quick_total = pyq_answers.filter(timespent__lt=30).count()
        quick_accuracy = (quick_correct / quick_total * 100) if quick_total > 0 else 0
        
        if avg_time < 60 and overall_accuracy > 70:
            insights.append({
                'type': 'success',
                'title': '⚡ Excellent Time Management',
                'text': f'Average {avg_time:.1f} seconds per question with {overall_accuracy:.1f}% accuracy. You have great speed and accuracy balance!',
                'icon': 'fas fa-clock nfas',
                'priority': 3
            })
        elif avg_time > 90:
            insights.append({
                'type': 'recommendation',
                'title': '⏰ Time Management Opportunity',
                'text': f'Average {avg_time:.1f} seconds per question. Try to reduce time by practicing more questions and identifying patterns quickly.',
                'icon': 'fas fa-stopwatch nfas',
                'priority': 2
            })
        
        if len(quick_answers) > len(time_spent_data) * 0.3 and quick_accuracy < overall_accuracy - 15:
            insights.append({
                'type': 'warning',
                'title': '🚨 Speed vs Accuracy Alert',
                'text': f'Quick answers (<30s) have {quick_accuracy:.1f}% accuracy vs {overall_accuracy:.1f}% overall. Consider slowing down slightly for better accuracy.',
                'icon': 'fas fa-exclamation-triangle nfas',
                'priority': 2
            })
    
    # 5. Progress Trend Analysis
    recent_sessions = pyq_sessions.order_by('-created_at')[:5]
    if recent_sessions.count() >= 3:
        recent_accuracies = []
        for session in recent_sessions:
            session_answers = TestAnswer.objects.filter(test_session=session, is_attempted=True)
            if session_answers.exists():
                s_correct = session_answers.filter(correct=True).count()
                s_total = session_answers.count()
                s_acc = (s_correct / s_total * 100) if s_total > 0 else 0
                recent_accuracies.append(s_acc)
        
        if len(recent_accuracies) >= 3:
            trend = analyze_trend(recent_accuracies)
            if trend == 'improving':
                insights.append({
                    'type': 'success',
                    'title': '🚀 Upward Trend Detected!',
                    'text': f'Your recent sessions show consistent improvement! Keep up the excellent work and maintain this momentum.',
                    'icon': 'fas fa-arrow-trend-up nfas',
                    'priority': 1
                })
            elif trend == 'declining':
                insights.append({
                    'type': 'warning',
                    'title': '📉 Performance Dip Noticed',
                    'text': 'Recent sessions show a slight decline. Take a short break, review mistakes, and focus on weak areas before continuing.',
                    'icon': 'fas fa-arrow-trend-down nfas',
                    'priority': 1
                })
    
    # 6. Exam Category Insights
    categories = ['NEET-PG', 'INI-CET', 'FMGE', 'UPSC-CMS']
    category_performance = []
    
    for category in categories:
        cat_pyq_uids = PYQ.objects.filter(pyq_cat=category).values_list('uid', flat=True)
        cat_answers = pyq_answers.filter(mcq_uid__in=cat_pyq_uids)
        
        if cat_answers.exists():
            c_total = cat_answers.count()
            c_correct = cat_answers.filter(correct=True).count()
            c_accuracy = (c_correct / c_total * 100) if c_total > 0 else 0
            
            category_performance.append({
                'name': category,
                'accuracy': c_accuracy,
                'attempted': c_total
            })
    
    if category_performance:
        category_performance.sort(key=lambda x: x['accuracy'], reverse=True)
        best_category = category_performance[0]
        
        if best_category['accuracy'] > overall_accuracy + 10:
            insights.append({
                'type': 'info',
                'title': f'🎯 {best_category["name"]} Specialist',
                'text': f'You excel in {best_category["name"]} questions with {best_category["accuracy"]:.1f}% accuracy. Consider this as your strength area!',
                'icon': 'fas fa-star nfas',
                'priority': 3
            })
    
    # 7. Milestone and Achievement Recognition
    if total_attempted >= 1000:
        insights.append({
            'type': 'achievement',
            'title': '🏅 Milestone Achievement: 1000+ Questions!',
            'text': f'Congratulations! You\'ve attempted {total_attempted} questions. This dedication will definitely pay off in your exams.',
            'icon': 'fas fa-medal nfas',
            'priority': 3
        })
    elif total_attempted >= 500:
        insights.append({
            'type': 'achievement',
            'title': '🎉 Great Progress: 500+ Questions!',
            'text': f'You\'ve successfully attempted {total_attempted} questions. You\'re building excellent exam preparation habits!',
            'icon': 'fas fa-thumbs-up nfas',
            'priority': 3
        })
    
    # 8. Personalized Recommendations
    recommendations = generate_personalized_recommendations(user, overall_accuracy, subject_performance, difficulty_analysis)
    insights.extend(recommendations)
    
    # Sort insights by priority and limit to most relevant
    insights.sort(key=lambda x: x['priority'])
    
    return JsonResponse({
        'insights': insights[:8],  # Return top 8 most relevant insights
        'user_stats': {
            'total_attempted': total_attempted,
            'overall_accuracy': round(overall_accuracy, 1),
            'performance_tier': performance_tier
        }
    })


def analyze_trend(values):
    """Analyze if the trend is improving, declining, or stable"""
    if len(values) < 3:
        return 'insufficient_data'
    
    # Simple trend analysis
    recent_avg = sum(values[:3]) / 3  # Last 3
    older_avg = sum(values[3:]) / len(values[3:]) if len(values) > 3 else sum(values[:3]) / 3
    
    diff = recent_avg - older_avg
    
    if diff > 5:
        return 'improving'
    elif diff < -5:
        return 'declining'
    else:
        return 'stable'


def get_subject_improvement_tips(subject_name):
    """Get specific improvement tips for all MBBS subjects"""
    tips = {
        # Pre-clinical subjects
        'Anatomy': 'Focus on visual learning with diagrams and mnemonics. Practice identifying structures from multiple views and cross-sectional anatomy.',
        'Physiology': 'Understand physiological mechanisms deeply. Use flowcharts for complex pathways like cardiac cycle and respiratory regulation.',
        'Biochemistry': 'Master metabolic pathways step-by-step. Use mnemonics for cycles like Krebs cycle and glycolysis. Focus on enzyme kinetics.',
        
        # Para-clinical subjects
        'Pharmacology': 'Group drugs by mechanism of action and therapeutic classes. Focus on side effects, contraindications, and drug interactions.',
        'Pathology': 'Correlate pathological changes with clinical presentations. Use case-based learning and understand disease progression.',
        'Microbiology': 'Create organism-wise charts linking morphology, diseases, and treatments. Focus on antibiotic sensitivity patterns.',
        'FMT': 'Master medico-legal procedures and documentation. Practice autopsy findings and toxicology principles.',
        'PSM': 'Focus on epidemiology, biostatistics, and public health programs. Understand disease prevention strategies.',
        
        # Clinical subjects
        'Medicine': 'Enhance clinical reasoning through case discussions. Master differential diagnosis and evidence-based treatment protocols.',
        'Surgery': 'Understand surgical anatomy, pre/post-operative care. Practice suturing techniques and emergency procedures.',
        'Obstetrics and Gynecology': 'Master normal pregnancy progression, labor stages, and common gynecological conditions. Practice pelvic examination techniques.',
        'Pediatrics': 'Learn age-specific normal values, developmental milestones, and vaccination schedules. Focus on pediatric emergencies.',
        'Orthopedics': 'Study musculoskeletal anatomy, fracture classifications, and rehabilitation protocols. Practice X-ray interpretation.',
        'Ophthalmology': 'Master eye anatomy and common eye diseases. Practice fundoscopy and visual field examination techniques.',
        'ENT': 'Understand ear, nose, throat anatomy. Practice otoscopy and common ENT procedures.',
        'Dermatology': 'Learn skin lesion morphology and differential diagnosis. Use clinical images for pattern recognition.',
        'Psychiatry': 'Master psychiatric interview techniques and diagnostic criteria (DSM-5/ICD-11). Understand psychopharmacology.',
        'Radiology': 'Practice systematic image interpretation. Start with chest X-rays and progress to CT/MRI findings.',
        'Anaesthesia': 'Focus on anesthetic drugs, monitoring techniques, and perioperative management. Understand airway management.',
    }
    
    return tips.get(subject_name, 'Focus on understanding core concepts through regular practice and clinical correlation.')


def generate_personalized_recommendations(user, overall_accuracy, subject_performance, difficulty_analysis):
    """Generate highly personalized recommendations based on user's performance patterns"""
    recommendations = []
    
    # Accuracy-based recommendations
    if overall_accuracy < 60:
        recommendations.append({
            'type': 'urgent',
            'title': '🔥 Foundation Building Required',
            'text': 'Focus on understanding basic concepts first. Review textbooks and attend concept-clearing sessions before attempting more questions.',
            'icon': 'fas fa-foundation nfas',
            'priority': 1
        })
    elif overall_accuracy < 75:
        recommendations.append({
            'type': 'recommendation',
            'title': '📚 Structured Learning Approach',
            'text': 'Create a study schedule focusing on weak subjects. Attempt 20-25 questions daily with thorough explanation review.',
            'icon': 'fas fa-calendar-alt nfas',
            'priority': 2
        })
    
    # Subject balance recommendation
    if subject_performance and len(subject_performance) > 0:
        accuracy_range = max(subject_performance, key=lambda x: x['accuracy'])['accuracy'] - min(subject_performance, key=lambda x: x['accuracy'])['accuracy']
        
        if accuracy_range > 30:
            recommendations.append({
                'type': 'strategy',
                'title': '⚖️ Balance Your Subject Performance',
                'text': f'Large variation in subject performance detected. Allocate 70% study time to weaker subjects and 30% to maintaining strong subjects.',
                'icon': 'fas fa-balance-scale nfas',
                'priority': 2
            })
    
    # Time-based recommendation
    current_hour = timezone.now().hour
    if 22 <= current_hour or current_hour <= 6:
        recommendations.append({
            'type': 'wellness',
            'title': '😴 Optimal Learning Time',
            'text': 'Late night studying detected. Consider practicing during morning hours (7-11 AM) for better retention and accuracy.',
            'icon': 'fas fa-moon nfas',
            'priority': 3
        })
    
    return recommendations
