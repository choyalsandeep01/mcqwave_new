from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
import logging
import json
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication
from pyqs.models import Subject, Unit, PYQ
from pyqs.views import (
    check_user_subscription_for_practice,
    get_smart_filtered_mcqs,
    parse_and_format_selections,
    calculate_smart_distribution
)
from mcqs.models import TestSession, TestAnswer
from django.utils import timezone
import uuid
import random
from django.core.cache import cache
from django.db.models import Count, Q, Prefetch
logger = logging.getLogger(__name__)

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def pyq_selection_data(request):
    """
    Get PYQ selection page data with pre-calculated counts for all combinations
    """
    try:
        profile = request.user.profile
       
        # Check if user has an ongoing PYQ test
        ongoing_test = None
        if profile.pyq_test:
            try:
                test_session = TestSession.objects.get(
                    test_id=profile.pyq_test,
                    user=request.user,
                    pyq=True
                )
                if not test_session.submitted:
                    ongoing_test = {
                        'test_id': profile.pyq_test,
                        'has_ongoing_test': True,
                        'message': 'You have an ongoing PYQ test. You can continue your previous test.'
                    }
                else:
                    profile.pyq_test = ''
                    profile.save()
            except TestSession.DoesNotExist:
                profile.pyq_test = ''
                profile.save()
       
        # Get unique exam categories from database
        pyq_cats_from_db = PYQ.objects.values_list('pyq_cat', flat=True).distinct().exclude(pyq_cat__isnull=True).exclude(pyq_cat='')
       
        if pyq_cats_from_db:
            pyq_categories = [{'code': cat, 'name': cat} for cat in pyq_cats_from_db]
        else:
            from pyqs.models import PYQ_Cat
            pyq_categories = [{'code': cat[0], 'name': cat[1]} for cat in PYQ_Cat]
       
        # Add 'ALL' option
        all_exam_codes = [cat['code'] for cat in pyq_categories]
       
        # Get subjects with units and pre-calculate counts
        subjects = Subject.objects.prefetch_related('units').all()
        subjects_data = []
       
        for subject in subjects:
            units_data = []
           
            # Calculate subject counts for each exam category
            subject_counts = {}
            for category in pyq_categories:
                count = PYQ.objects.filter(
                    unit__subject__uid=subject.uid,
                    pyq_cat=category['code']
                ).distinct().count()
                subject_counts[category['code']] = count
           
            # Calculate subject count for ALL exams
            subject_counts['ALL'] = PYQ.objects.filter(
                unit__subject__uid=subject.uid,
                pyq_cat__in=all_exam_codes
            ).distinct().count()
           
            for unit in subject.units.all():
                # Calculate unit counts for each exam category
                unit_counts = {}
                for category in pyq_categories:
                    count = PYQ.objects.filter(
                        unit__uid=unit.uid,
                        pyq_cat=category['code']
                    ).distinct().count()
                    unit_counts[category['code']] = count
               
                # Calculate unit count for ALL exams
                unit_counts['ALL'] = PYQ.objects.filter(
                    unit__uid=unit.uid,
                    pyq_cat__in=all_exam_codes
                ).distinct().count()
               
                units_data.append({
                    'uid': str(unit.uid),
                    'name': unit.name,
                    'order': unit.order,
                    'counts': unit_counts  # Pre-calculated counts for each exam type
                })
           
            subjects_data.append({
                'uid': str(subject.uid),
                'name': subject.name,
                'icon': subject.icon,
                'icon_color': subject.icon_color,
                'order': subject.order,
                'units': units_data,
                'counts': subject_counts  # Pre-calculated counts for each exam type
            })
       
        # Calculate total counts for each exam category (for reference)
        exam_totals = {}
        for category in pyq_categories:
            exam_totals[category['code']] = PYQ.objects.filter(
                pyq_cat=category['code']
            ).distinct().count()
       
        exam_totals['ALL'] = PYQ.objects.filter(
            pyq_cat__in=all_exam_codes
        ).distinct().count()
       
        response_data = {
            'success': True,
            'data': {
                'subjects': subjects_data,
                'pyq_categories': pyq_categories,
                'ongoing_test': ongoing_test,
                'exam_totals': exam_totals  # Total counts for each exam type
            }
        }
       
        return Response(response_data, status=status.HTTP_200_OK)
       
    except Exception as e:
        logger.error(f"Error in pyq_selection_data: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'An error occurred loading the PYQ selection data.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def start_pyq_practice(request):
    """
    Start PYQ practice session - Mobile API version of get_filtered_mcqs
    """
    try:
        profile = request.user.profile
        
        # Check if user already has an ongoing PYQ test
        if profile.pyq_test:
            try:
                test_session = TestSession.objects.get(test_id=profile.pyq_test, user=request.user, pyq=True)
                if not test_session.submitted:
                    return Response({
                        'success': False,
                        'error': 'You have an ongoing PYQ test. Please complete or abandon it first.',
                        'ongoing_test_id': profile.pyq_test
                    }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    profile.pyq_test = ''
                    profile.save()
            except TestSession.DoesNotExist:
                profile.pyq_test = ''
                profile.save()

        # Parse request data
        data = request.data
        mode = data.get('mode', 'test')
        subject_uids = data.get('subjectUids', [])
        unit_uids = data.get('unitUids', [])
        exam_types = data.get('examTypes', [])
        raw_selections = data.get('selections', [])
        selections = parse_and_format_selections(raw_selections)
        
        # ?? FIX: Transform exam types to lowercase format for get_smart_filtered_mcqs
        normalized_exam_types = []
        for exam_type in exam_types:
            exam_upper = exam_type.upper()
            if exam_upper == 'NEET-PG' or exam_upper == 'NEETPG':
                normalized_exam_types.append('neet-pg')
            elif exam_upper == 'INI-CET' or exam_upper == 'INICET':
                normalized_exam_types.append('ini-cet')
            elif exam_upper == 'FMGE':
                normalized_exam_types.append('fmge')
            elif exam_upper == 'UPSC-CMS' or exam_upper == 'UPSCCMS':
                normalized_exam_types.append('upsc-cms')
            elif exam_upper == 'ALL':
                normalized_exam_types.append('all')
            else:
                # Fallback: convert to lowercase with hyphen
                normalized_exam_types.append(exam_type.lower())
        
        # ?? ADD: Debug logging
        logger.info(f"PYQ Practice - User: {request.user.username}")
        logger.info(f"Original exam_types: {exam_types}")
        logger.info(f"Normalized exam_types: {normalized_exam_types}")
        logger.info(f"Subject UIDs: {subject_uids}")
        logger.info(f"Unit UIDs: {unit_uids}")
        
        # Validate input
        if not (subject_uids or unit_uids):
            return Response({
                'success': False,
                'error': 'No subjects or units selected'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not exam_types:
            return Response({
                'success': False,
                'error': 'No exam types selected'
            }, status=status.HTTP_400_BAD_REQUEST)

        # **SUBSCRIPTION CHECK - CRITICAL VALIDATION**
        # Use ORIGINAL exam_types for subscription check (uppercase format)
        is_allowed, subscription_error = check_user_subscription_for_practice(request.user, exam_types)
        
        if not is_allowed:
            logger.warning(f"User {request.user.username} attempted to access PYQ without proper subscription. "
                         f"Exam types: {exam_types}, Error: {subscription_error}")
            
            return Response({
                'success': False, 
                'error': subscription_error,
                'error_type': 'subscription_required',
                'redirect_to_subscription': True
            }, status=status.HTTP_403_FORBIDDEN)
        
        # ?? FIX: Pass normalized exam types to get_smart_filtered_mcqs
        final_mcqs = get_smart_filtered_mcqs(subject_uids, unit_uids, normalized_exam_types)
        
        logger.info(f"Final MCQs count: {len(final_mcqs)} for exam types: {normalized_exam_types}")
        
        if not final_mcqs:
            return Response({
                'success': False,
                'error': 'No questions found for your selection'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Generate unique test ID
        test_id = f"PYQ_{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate total time (1 minute per question)
        total_time_minutes = len(final_mcqs)
        total_time_seconds = total_time_minutes * 60
        
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
        
        # Prepare MCQ data for mobile app
        mcq_data = []
        for mcq in final_mcqs:
            mcq_dict = {
                'uid': str(mcq.uid),
                'text': mcq.text,
                'option_1': mcq.option_1,
                'option_2': mcq.option_2,
                'option_3': mcq.option_3,
                'option_4': mcq.option_4,
                'image': mcq.image.url if mcq.image else None,
                'topic': mcq.topic,
                'unit_name': mcq.unit.name if mcq.unit else '',
                'subject_name': mcq.unit.subject.name if mcq.unit and mcq.unit.subject else '',
                # PYQ specific fields for display
                'pyq_cat': mcq.pyq_cat,
                'pyq_year': mcq.pyq_year,
                'pyq_month': mcq.pyq_month,
                'exam_display': mcq.get_exam_display(),
            }
            mcq_data.append(mcq_dict)
        
        # Format selections for display
        formatted_selections = parse_and_format_selections(raw_selections)
        
        # Log successful test creation
        logger.info(f"PYQ test created successfully for user {request.user.username}. "
                   f"Test ID: {test_id}, Questions: {len(final_mcqs)}, Exam types: {normalized_exam_types}")
        
        response_data = {
            'success': True,
            'message': f'New PYQ Test Started - {", ".join(formatted_selections[:3])}{"..." if len(formatted_selections) > 3 else ""}',
            'test_data': {
                'mcqs': mcq_data,
                'count': len(final_mcqs),
                'test_id': test_id,
                'total_time': total_time_minutes,
                'mode': mode,
                'selections': formatted_selections,
                'exam_types': exam_types,  # Return original format to frontend
                'is_pyq': True
            }
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error in start_pyq_practice: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_pyq_count_api(request):
    """
    Get count of available PYQs for given selections and exam types - Mobile API
    """
    try:
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
        
        return Response({
            'success': True,
            'count': count,
            'subject_uids': subject_uids,
            'unit_uids': unit_uids,
            'exam_types': exam_types
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in get_pyq_count_api: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to get question count'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def continue_pyq_test_api(request, test_id):
    """
    Continue PYQ test function - Mobile API version
    """
    try:
        user = request.user
        
        # Get test session
        try:
            test_session = TestSession.objects.get(user=user, test_id=test_id, pyq=True)
        except TestSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'PYQ test session not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if test_session.submitted:
            # Clear the pyq_test field since test is already submitted
            profile = request.user.profile
            profile.pyq_test = ''
            profile.save()
            
            return Response({
                'success': False,
                'error': 'PYQ test already submitted.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'message': 'Your previous PYQ practice was not submitted. Please submit the pending test to start a new one.',
            'continue_test_id': test_id
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in continue_pyq_test_api: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to check test continuation.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_current_pyq_test(request):
    """
    Check if user has any current unsubmitted PYQ test
    """
    try:
        profile = request.user.profile
        
        if profile.pyq_test:
            try:
                test_session = TestSession.objects.get(
                    user=request.user, 
                    test_id=profile.pyq_test, 
                    pyq=True
                )
                if not test_session.submitted:
                    return Response({
                        'success': True,
                        'has_current_test': True,
                        'test_id': profile.pyq_test,
                        'mode': test_session.mode,
                        'total_questions': test_session.total_questions,
                        'is_pyq': True,
                        'created_at': test_session.created_at.isoformat()
                    })
                else:
                    # Clear submitted PYQ test
                    profile.pyq_test = ''
                    profile.save()
            except TestSession.DoesNotExist:
                # Clear invalid PYQ test reference
                profile.pyq_test = ''
                profile.save()
        
        return Response({
            'success': True,
            'has_current_test': False
        })
        
    except Exception as e:
        logger.error(f"Error in check_current_pyq_test: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def validate_exam_selection(request):
    """
    Real-time validation of exam type selection based on user subscription
    Returns immediately whether user can select the exam type
    """
    try:
        from payments.models import UserSubscriptionManager
        
        exam_type = request.data.get('exam_type')
        
        if not exam_type:
            return Response({
                'success': False,
                'error': 'No exam type provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Normalize exam type
        exam_type_lower = exam_type.lower().replace('_', '-')
        
        # Check subscription for this specific exam type
        has_access = False
        restricted_exam = None
        required_plan = None
        
        if exam_type_lower in ['neet-pg', 'neetpg']:
            has_access = UserSubscriptionManager.has_active_subscription_for_category(
                request.user, 'neet_pg_inicet'
            )
            if not has_access:
                restricted_exam = 'NEET-PG'
                required_plan = {
                    'category': 'neet_pg_inicet',
                    'display_name': 'NEET PG + INI-CET',
                    'exam_types': ['NEET-PG', 'INI-CET']
                }
        
        elif exam_type_lower in ['ini-cet', 'inicet']:
            has_access = UserSubscriptionManager.has_active_subscription_for_category(
                request.user, 'neet_pg_inicet'
            )
            if not has_access:
                restricted_exam = 'INI-CET'
                required_plan = {
                    'category': 'neet_pg_inicet',
                    'display_name': 'NEET PG + INI-CET',
                    'exam_types': ['NEET-PG', 'INI-CET']
                }
        
        elif exam_type_lower == 'fmge':
            has_access = UserSubscriptionManager.has_active_subscription_for_category(
                request.user, 'fmge'
            )
            if not has_access:
                restricted_exam = 'FMGE'
                required_plan = {
                    'category': 'fmge',
                    'display_name': 'FMGE',
                    'exam_types': ['FMGE']
                }
        
        elif exam_type_lower in ['upsc-cms', 'upsccms', 'upsc']:
            has_access = UserSubscriptionManager.has_active_subscription_for_category(
                request.user, 'upsc_cms'
            )
            if not has_access:
                restricted_exam = 'UPSC-CMS'
                required_plan = {
                    'category': 'upsc_cms',
                    'display_name': 'UPSC CMS',
                    'exam_types': ['UPSC-CMS']
                }
        
        elif exam_type_lower == 'all':
            # Check all categories
            all_access = True
            restricted_exams = []
            
            if not UserSubscriptionManager.has_active_subscription_for_category(request.user, 'neet_pg_inicet'):
                all_access = False
                restricted_exams.extend(['NEET-PG', 'INI-CET'])
            
            if not UserSubscriptionManager.has_active_subscription_for_category(request.user, 'fmge'):
                all_access = False
                restricted_exams.append('FMGE')
            
            if not UserSubscriptionManager.has_active_subscription_for_category(request.user, 'upsc_cms'):
                all_access = False
                restricted_exams.append('UPSC-CMS')
            
            if not all_access:
                return Response({
                    'success': False,
                    'has_access': False,
                    'message': f'Subscription required for: {", ".join(restricted_exams)}',
                    'restricted_exams': restricted_exams,
                    'required_plans': [
                        {'category': 'neet_pg_inicet', 'display_name': 'NEET PG + INI-CET'},
                        {'category': 'fmge', 'display_name': 'FMGE'},
                        {'category': 'upsc_cms', 'display_name': 'UPSC CMS'}
                    ] if len(restricted_exams) > 2 else []
                }, status=status.HTTP_403_FORBIDDEN)
            
            has_access = True
        
        if has_access:
            return Response({
                'success': True,
                'has_access': True,
                'message': f'Access granted for {exam_type.upper()}'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'has_access': False,
                'message': f'Subscription required for {restricted_exam} PYQs',
                'restricted_exam': restricted_exam,
                'required_plan': required_plan
            }, status=status.HTTP_403_FORBIDDEN)
    
    except Exception as e:
        logger.error(f"Error in validate_exam_selection: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Validation failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

