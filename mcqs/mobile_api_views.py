from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from django.db import transaction
from .models import Subject, Unit, Chapter, Topic, MCQ, TestSession, TestAnswer, difficulties, Bookmark, mcq_types
from accounts.models import Profile
from payments.models import UserSubscription, UserSubscriptionManager
from .serializers import MCQSerializer, MCQSubmitSerializer
import json
import random
import uuid
import traceback
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import logging
from django.core.cache import cache
from django.db.models import Count, Prefetch
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_cus_mcq(request, email_token):
    """
    Mobile API version of cus_mcq with accurate MCQ counting
    Returns MCQ structure data as JSON instead of rendering template
    """
    try:
        if request.user.is_authenticated:
            if email_token == request.user.profile.email_token:
                
                # Single optimized query with select_related and prefetch_related
                subjects = Subject.objects.prefetch_related(
                    Prefetch('units', queryset=Unit.objects.prefetch_related(
                        Prefetch('chapters', queryset=Chapter.objects.prefetch_related(
                            Prefetch('topics', queryset=Topic.objects.annotate(
                                mcq_count=Count('topics')
                            ))
                        ))
                    ))
                ).all()
                
                data = {}
                subject_icons = {}
                mcq_counts = {}
                
                # Process the prefetched data
                for subject in subjects:
                    data[subject.name] = {}
                    subject_icons[subject.name] = {
                        'icon': subject.icon,
                        'icon_color': subject.icon_color
                    }
                    
                    subject_mcq_count = 0
                    mcq_counts[subject.name] = {}
                    
                    for unit in subject.units.all():
                        data[subject.name][unit.name] = {}
                        unit_mcq_count = 0
                        mcq_counts[subject.name][unit.name] = {}
                        
                        for chapter in unit.chapters.all():
                            topics = chapter.topics.all()
                            data[subject.name][unit.name][chapter.name] = [topic.name for topic in topics]
                            
                            chapter_mcq_count = 0
                            mcq_counts[subject.name][unit.name][chapter.name] = {}
                            
                            for topic in topics:
                                topic_mcq_count = topic.mcq_count
                                mcq_counts[subject.name][unit.name][chapter.name][topic.name] = topic_mcq_count
                                chapter_mcq_count += topic_mcq_count
                            
                            mcq_counts[subject.name][unit.name][chapter.name]['_total'] = chapter_mcq_count
                            unit_mcq_count += chapter_mcq_count
                        
                        mcq_counts[subject.name][unit.name]['_total'] = unit_mcq_count
                        subject_mcq_count += unit_mcq_count
                    
                    mcq_counts[subject.name]['_total'] = subject_mcq_count
                
                # Get aggregate counts in a single query
                mcq_stats = MCQ.objects.aggregate(
                    total=Count('uid'),
                    clinical=Count('uid', filter=Q(types__types="Clinical")),
                    image=Count('uid', filter=Q(types__types="Image"))
                )
                
                response_data = {
                    'success': True,
                    'data': data,
                    'subject_icons': subject_icons,
                    'mcq_counts': mcq_counts,
                    'total_mcqs': mcq_stats['total'],
                    'clinical_mcqs': mcq_stats['clinical'],
                    'image_mcqs': mcq_stats['image']
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': 'Invalid email token'
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({
                'success': False,
                'error': 'User not authenticated'
            }, status=status.HTTP_401_UNAUTHORIZED)
           
    except Exception as e:
        logger.error(f"Error in mobile_cus_mcq: {str(e)}\n{traceback.format_exc()}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_test(request, email_token):
    """
    Mobile API version of test
    Returns test data as JSON instead of rendering template
    """
    try:
        profile = request.user.profile
        if not profile.current_test:
            user = request.user
            test_id = str(uuid.uuid4())
            
            # Get parameters from request
            selections_json = request.GET.get('selections')
            print(f"\n{'='*80}")
            print(f"🔍 RAW SELECTIONS JSON: {selections_json}")
            print(f"{'='*80}\n")
            
            selections = json.loads(selections_json) if selections_json else []
            print(f"📋 PARSED SELECTIONS LIST: {selections}")
            print(f"📊 TOTAL SELECTIONS COUNT: {len(selections)}\n")
            
            if not selections:
                return Response({
                    'success': False,
                    'error': 'Please add selections by clicking on Add Selection after making your choices.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            question_type = request.GET.get('questionType', '').title()
            difficulty_level = request.GET.get('difficultyLevel', '').title()
            num_mcqs_str = request.GET.get('numQuestions', '25')
            mode = request.GET.get('mode', 'test')
            time_per_question_str = request.GET.get('timePerQuestion', '1.0')
            
            print(f"⚙️ PARAMETERS:")
            print(f"   Question Type: {question_type}")
            print(f"   Difficulty Level: {difficulty_level}")
            print(f"   Num Questions: {num_mcqs_str}")
            print(f"   Mode: {mode}")
            print(f"   Time Per Question: {time_per_question_str}\n")
            
            # Process parameters
            try:
                num_mcqs = round(float(num_mcqs_str))
            except ValueError:
                num_mcqs = 25
            
            try:
                time_per_question = float(time_per_question_str) if time_per_question_str else 1.0
                if time_per_question < 0.6:
                    time_per_question = 0.6
                elif time_per_question > 3:
                    time_per_question = 3
            except ValueError:
                time_per_question = 1.0
            
            if num_mcqs > 40:
                return Response({
                    'success': False,
                    'error': 'You cannot select more than 40 questions.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Build queries and get MCQs
            selections_data = []
            print(f"🔨 BUILDING QUERIES FOR EACH SELECTION:\n")
            
            for idx, selection in enumerate(selections, 1):
                print(f"   Selection #{idx}: {selection}")
                parts = selection.split('->')
                print(f"   Parts: {parts}")
                print(f"   Parts Count: {len(parts)}")
                
                # Build the query based on hierarchy depth
                if len(parts) == 1:
                    # Subject only
                    subject_name = parts[0]
                    query = Q(topic__chapter__unit__subject__name=subject_name)
                    print(f"   ✅ Query Type: SUBJECT ONLY")
                    print(f"   Subject: {subject_name}")
                    
                elif len(parts) == 2:
                    # Subject -> Unit
                    subject_name, unit_name = parts[0], parts[1]
                    query = Q(
                        topic__chapter__unit__subject__name=subject_name,
                        topic__chapter__unit__name=unit_name
                    )
                    print(f"   ✅ Query Type: SUBJECT -> UNIT")
                    print(f"   Subject: {subject_name}")
                    print(f"   Unit: {unit_name}")
                    
                elif len(parts) == 3:
                    # Subject -> Unit -> Chapter
                    subject_name, unit_name, chapter_name = parts[0], parts[1], parts[2]
                    query = Q(
                        topic__chapter__unit__subject__name=subject_name,
                        topic__chapter__unit__name=unit_name,
                        topic__chapter__name=chapter_name
                    )
                    print(f"   ✅ Query Type: SUBJECT -> UNIT -> CHAPTER")
                    print(f"   Subject: {subject_name}")
                    print(f"   Unit: {unit_name}")
                    print(f"   Chapter: {chapter_name}")
                    
                elif len(parts) == 4:
                    # Subject -> Unit -> Chapter -> Topic
                    subject_name, unit_name, chapter_name, topic_name = parts[0], parts[1], parts[2], parts[3]
                    query = Q(
                        topic__chapter__unit__subject__name=subject_name,
                        topic__chapter__unit__name=unit_name,
                        topic__chapter__name=chapter_name,
                        topic__name=topic_name
                    )
                    print(f"   ✅ Query Type: SUBJECT -> UNIT -> CHAPTER -> TOPIC")
                    print(f"   Subject: {subject_name}")
                    print(f"   Unit: {unit_name}")
                    print(f"   Chapter: {chapter_name}")
                    print(f"   Topic: {topic_name}")
                else:
                    print(f"   ❌ SKIPPED: Invalid parts count ({len(parts)})")
                    continue
                
                # Apply filters for question type and difficulty
                if question_type and question_type.lower() != "mixed":
                    query &= Q(types__types=question_type)
                    print(f"   🔧 Applied Question Type Filter: {question_type}")
                if difficulty_level and difficulty_level.lower() != "mixed":
                    query &= Q(difficulty__name=difficulty_level)
                    print(f"   🔧 Applied Difficulty Filter: {difficulty_level}")
                
                print(f"   📝 Final Query Object: {query}\n")
                
                selections_data.append({
                    'selection': selection,
                    'query': query,
                    'parts_count': len(parts)
                })
            
            print(f"{'='*80}")
            print(f"🎯 TOTAL QUERIES BUILT: {len(selections_data)}\n")
            
            # Get MCQs using proper queryset combining
            all_mcqs = MCQ.objects.none()
            
            print(f"🔍 FETCHING MCQs FOR EACH SELECTION:\n")
            for idx, selection_data in enumerate(selections_data, 1):
                mcqs = MCQ.objects.filter(selection_data['query'])
                mcq_count = mcqs.count()
                print(f"   Selection #{idx}: '{selection_data['selection']}'")
                print(f"   MCQs Found: {mcq_count}")
                
                # Show first few MCQ titles if any found
                if mcq_count > 0:
                    sample_mcqs = mcqs[:3]
                    print(f"   Sample MCQs:")
                    for mcq in sample_mcqs:
                        mcq_text = mcq.text[:50] + "..." if len(mcq.text) > 50 else mcq.text
                        print(f"      - {mcq_text}")
                else:
                    print(f"   ⚠️ NO MCQs FOUND FOR THIS SELECTION!")
                print()
                
                all_mcqs = all_mcqs | mcqs
            
            # Remove duplicates and convert to list
            total_before_distinct = all_mcqs.count()
            filtered_mcqs = list(all_mcqs.distinct())
            total_after_distinct = len(filtered_mcqs)
            
            print(f"{'='*80}")
            print(f"📊 MCQ COLLECTION SUMMARY:")
            print(f"   Total MCQs (before distinct): {total_before_distinct}")
            print(f"   Total MCQs (after distinct): {total_after_distinct}")
            print(f"   Duplicates Removed: {total_before_distinct - total_after_distinct}")
            print(f"{'='*80}\n")
            
            random.shuffle(filtered_mcqs)
            
            if len(filtered_mcqs) == 0:
                print(f"? ERROR: NO MCQs FOUND!\n")
                
                # Build detailed error message
                error_details = []
                if question_type and question_type.lower() != "mixed":
                    error_details.append(f"Question Type: {question_type}")
                if difficulty_level and difficulty_level.lower() != "mixed":
                    error_details.append(f"Difficulty: {difficulty_level}")
                
                filters_text = " with filters: " + ", ".join(error_details) if error_details else ""
                
                return Response({
                    'success': False,
                    'error': f'No MCQs found with your current selections{filters_text}. Please try different selections or adjust your filters.',
                    'error_type': 'NO_MCQS_FOUND',  # ? Add this identifier
                    'details': {
                        'selections_count': len(selections),
                        'question_type': question_type if question_type else 'Mixed',
                        'difficulty_level': difficulty_level if difficulty_level else 'Mixed'
                    }
                }, status=status.HTTP_404_NOT_FOUND)  # Changed to 404
            
            # 🔥 FIX: Improved allocation to ensure exact count
            inverse_parts_count_sum = sum(1 / data['parts_count'] for data in selections_data)
            final_mcqs = []
            
            print(f"⚖️ ALLOCATING MCQs BY WEIGHT:\n")
            print(f"   Inverse Parts Count Sum: {inverse_parts_count_sum}")
            print(f"   Target MCQ Count: {num_mcqs}\n")
            
            # Calculate allocations without rounding first
            allocations = []
            for selection_data in selections_data:
                parts_count = selection_data['parts_count']
                inverse_weight = (1 / parts_count) / inverse_parts_count_sum
                allocated_mcqs_float = inverse_weight * num_mcqs
                allocations.append({
                    'selection_data': selection_data,
                    'parts_count': parts_count,
                    'weight': inverse_weight,
                    'allocated_float': allocated_mcqs_float,
                    'allocated_int': int(allocated_mcqs_float),  # Floor value
                    'remainder': allocated_mcqs_float - int(allocated_mcqs_float)
                })
            
            # Allocate floor values first
            total_allocated = sum(alloc['allocated_int'] for alloc in allocations)
            remaining_to_allocate = num_mcqs - total_allocated
            
            # Sort by remainder (descending) and allocate remaining slots
            allocations.sort(key=lambda x: x['remainder'], reverse=True)
            for i in range(remaining_to_allocate):
                allocations[i]['allocated_int'] += 1
            
            # Now allocate MCQs based on final counts
            for idx, alloc in enumerate(allocations, 1):
                selection_data = alloc['selection_data']
                allocated_count = alloc['allocated_int']
                
                selected_mcqs = [mcq for mcq in filtered_mcqs if mcq not in final_mcqs][:allocated_count]
                
                print(f"   Selection #{idx}: '{selection_data['selection']}'")
                print(f"   Parts Count: {alloc['parts_count']}")
                print(f"   Weight: {alloc['weight']:.4f}")
                print(f"   Allocated Float: {alloc['allocated_float']:.2f}")
                print(f"   Final Allocated: {allocated_count}")
                print(f"   Actually Added: {len(selected_mcqs)}\n")
                
                final_mcqs.extend(selected_mcqs)
            
            # 🔥 FIX: Ensure exact count by trimming if needed
            if len(final_mcqs) > num_mcqs:
                print(f"⚠️ TRIMMING: Removing {len(final_mcqs) - num_mcqs} extra MCQs")
                final_mcqs = final_mcqs[:num_mcqs]
            elif len(final_mcqs) < num_mcqs:
                # Fill remaining if needed
                remaining_mcqs = [mcq for mcq in filtered_mcqs if mcq not in final_mcqs]
                to_add = num_mcqs - len(final_mcqs)
                added_mcqs = remaining_mcqs[:to_add]
                print(f"📥 FILLING REMAINING SLOTS:")
                print(f"   Current Count: {len(final_mcqs)}")
                print(f"   Target Count: {num_mcqs}")
                print(f"   Adding: {len(added_mcqs)} more MCQs\n")
                final_mcqs.extend(added_mcqs)
            
            final_mcqs_count = len(final_mcqs)
            print(f"{'='*80}")
            print(f"✅ FINAL MCQ COUNT: {final_mcqs_count} (Target: {num_mcqs})")
            print(f"{'='*80}\n")
            
            # Check subscription
            has_active_subscription = False
            try:
                subscription_summary = UserSubscriptionManager.get_subscription_summary(user)
                
                for category, details in subscription_summary.items():
                    if not details['is_expired']:
                        has_active_subscription = True
                        break
                        
            except Exception as e:
                has_active_subscription = False
            
            print(f"💳 SUBSCRIPTION STATUS: {'Active' if has_active_subscription else 'No Active Subscription'}\n")
            
            # Access control
            if has_active_subscription:
                pass  # Unlimited access
            else:
                if not profile.can_attempt_test(final_mcqs_count):
                    print(f"❌ INSUFFICIENT FREE MCQs!")
                    print(f"   Required: {final_mcqs_count}")
                    print(f"   Available: {profile.free_mcqs_remaining}\n")
                    return Response({
                        'success': False,
                        'error': f'You don\'t have any active subscriptions and insufficient free MCQs. You need {final_mcqs_count} MCQs but only have {profile.free_mcqs_remaining} remaining.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                profile.consume_free_mcqs(final_mcqs_count)
                print(f"✅ CONSUMED {final_mcqs_count} FREE MCQs\n")
            
            # Create test session
            total_time_minutes = time_per_question * len(final_mcqs)
            total_time_seconds = round(total_time_minutes * 60)
            
            mcq_data = []
            for mcq in final_mcqs:
                mcq_dict = {
                    'uid': str(mcq.uid),
                    'text': mcq.text,
                    'option_1': mcq.option_1,
                    'option_2': mcq.option_2,
                    'option_3': mcq.option_3,
                    'option_4': mcq.option_4,
                    'image': request.build_absolute_uri(mcq.image.url) if mcq.image else None
                }
                mcq_data.append(mcq_dict)

            test_session = TestSession.objects.create(
                user=user, 
                test_id=test_id, 
                total_questions=len(final_mcqs), 
                selections=selections,
                totaltime=total_time_seconds,
                mode=mode
            )

            print(f"✅ TEST SESSION CREATED: {test_id}\n")

            current_test = request.user.profile
            current_test.current_test = test_id
            current_test.save()

            for mcq in final_mcqs:
                TestAnswer.objects.create(test_session=test_session, mcq_uid=mcq.uid)

            print(f"✅ TEST ANSWERS CREATED: {len(final_mcqs)} entries\n")
            print(f"{'='*80}\n")

            response_data = {
                'success': True,
                'message': 'New Test Started',
                'test_data': {
                    'mcqs': mcq_data,
                    'count': len(final_mcqs),
                    'test_id': test_id,
                    'total_time': total_time_minutes,
                    'mode': mode
                }
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'error': 'Your previous practice was not submitted. Please submit the pending test to start a new one.',
                'current_test_id': profile.current_test
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ ERROR IN mobile_test:")
        print(f"{'='*80}")
        print(f"Error Message: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






@login_required
@csrf_exempt
@require_http_methods(["GET"])
def mobile_qod(request, email_token):  # ✅ NOW accepts email_token parameter
    """Mobile API version of qod"""
    try:
        # ✅ Optional: Validate email_token if needed
        print(f"📧 Email token received: {email_token}")
        
        mcq = MCQ.objects.order_by('?').first()
        
        if not mcq:
            return JsonResponse({
                'success': False,
                'error': 'No questions available'
            }, status=404)
        
        # In your mobile_qod view
        if mcq.image:
            # Return full URL instead of relative path
            image_url = request.build_absolute_uri(mcq.image.url)
        else:
            image_url = None


        response_data = {
            'success': True,
            'id': str(mcq.uid),  # Use uid from BaseModel
            'text': mcq.text,
            'options': [
                mcq.option_1,
                mcq.option_2,
                mcq.option_3,
                mcq.option_4
            ],
            'correct_answer': mcq.correct_option,
            'explanation': mcq.explanation,
            'has_image': bool(mcq.image),
            'image_url': image_url
        }
        
        print(f"✅ Mobile QOD Success: MCQ {mcq.uid} sent")
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"❌ Mobile QOD Error: {e}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch question',
            'message': str(e)
        }, status=500)


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_submit_mcq_feedback(request):
    """
    Mobile API version of submit_mcq_feedback
    Same functionality but returns JSON response
    """
    try:
        from .models import MCQFeedback
        data = request.data
        
        mcq = MCQ.objects.get(uid=data['mcq_id'])
        feedback = MCQFeedback.objects.create(
            mcq=mcq,
            user=request.user,
            feedback_type=data['feedback_type'],
            feedback_text=data['feedback_text']
        )
        
        return Response({
            'success': True,
            'message': 'Feedback submitted successfully'
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_toggle_bookmark(request):
    if request.method == 'POST':
        mcq_uid = request.POST.get('mcq_uid')
        bookmark_type = request.POST.get('bookmark_type')
        test_session_id = request.POST.get('test_session_id')
        user = request.user

        try:
            test_session = TestSession.objects.get(test_id=test_session_id)
            
            # Get MCQ/PYQ instance based on test session type
            mcq_instance = get_mcq_instance_by_uid(test_session, mcq_uid)
            if not mcq_instance:
                return JsonResponse({'error': 'Question not found'}, status=404)
                
        except TestSession.DoesNotExist:
            return JsonResponse({'error': 'TestSession not found'}, status=404)

        # Handle bookmark creation/update based on test session type
        if test_session.pyq:
            from pyqs.models import PYQBookmark
            try:
                # Check if bookmark already exists
                bookmark = PYQBookmark.objects.get(
                    user=user, 
                    pyq=mcq_instance, 
                    test_session=test_session
                )
                
                # Toggle or update bookmark type
                if bookmark.bookmark_type == bookmark_type:
                    bookmark.delete()
                    return JsonResponse({'status': 'unbookmarked'})
                else:
                    bookmark.bookmark_type = bookmark_type
                    bookmark.save()
                    return JsonResponse({'status': 'bookmarked', 'bookmark_type': bookmark.bookmark_type})
                    
            except PYQBookmark.DoesNotExist:
                # Create new bookmark
                bookmark = PYQBookmark.objects.create(
                    user=user,
                    pyq=mcq_instance,
                    test_session=test_session,
                    bookmark_type=bookmark_type,
                    bkmk_id=str(uuid.uuid4())
                )
                return JsonResponse({'status': 'bookmarked', 'bookmark_type': bookmark.bookmark_type})
                
        else:
            # Handle regular MCQ bookmarks
            try:
                bookmark = Bookmark.objects.get(
                    user=user, 
                    mcq=mcq_instance, 
                    test_session=test_session
                )
                
                if bookmark.bookmark_type == bookmark_type:
                    bookmark.delete()
                    return JsonResponse({'status': 'unbookmarked'})
                else:
                    bookmark.bookmark_type = bookmark_type
                    bookmark.save()
                    return JsonResponse({'status': 'bookmarked', 'bookmark_type': bookmark.bookmark_type})
                    
            except Bookmark.DoesNotExist:
                bookmark = Bookmark.objects.create(
                    user=user,
                    mcq=mcq_instance,
                    test_session=test_session,
                    bookmark_type=bookmark_type,
                    bkmk_id=str(uuid.uuid4())
                )
                return JsonResponse({'status': 'bookmarked', 'bookmark_type': bookmark.bookmark_type})

    return JsonResponse({'error': 'Invalid request'}, status=400)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_bookmarks_home(request, email_token):
    """
    Mobile API version of bookmarks_home
    Returns bookmark data as JSON with complete MCQ and PYQ data
    """
    try:
        from pyqs.models import PYQBookmark
        
        # Fetch MCQ bookmarks
        mcq_star_bookmarks = Bookmark.objects.filter(
            user=request.user, 
            bookmark_type='Star'
        ).select_related('mcq', 'test_session', 'mcq__topic', 'mcq__topic__chapter', 
                         'mcq__topic__chapter__unit', 'mcq__topic__chapter__unit__subject',
                         'mcq__difficulty', 'mcq__types')
        
        mcq_unstudied_bookmarks = Bookmark.objects.filter(
            user=request.user, 
            bookmark_type='Unstudied'
        ).select_related('mcq', 'test_session', 'mcq__topic', 'mcq__topic__chapter', 
                         'mcq__topic__chapter__unit', 'mcq__topic__chapter__unit__subject',
                         'mcq__difficulty', 'mcq__types')
        
        mcq_other_bookmarks = Bookmark.objects.filter(
            user=request.user, 
            bookmark_type='Other'
        ).select_related('mcq', 'test_session', 'mcq__topic', 'mcq__topic__chapter', 
                         'mcq__topic__chapter__unit', 'mcq__topic__chapter__unit__subject',
                         'mcq__difficulty', 'mcq__types')
        
        # Fetch PYQ bookmarks
        pyq_star_bookmarks = PYQBookmark.objects.filter(
            user=request.user, 
            bookmark_type='Star'
        ).select_related('pyq', 'test_session', 'pyq__unit', 'pyq__unit__subject',
                         'pyq__difficulty', 'pyq__types')
        
        pyq_unstudied_bookmarks = PYQBookmark.objects.filter(
            user=request.user, 
            bookmark_type='Unstudied'
        ).select_related('pyq', 'test_session', 'pyq__unit', 'pyq__unit__subject',
                         'pyq__difficulty', 'pyq__types')
        
        pyq_other_bookmarks = PYQBookmark.objects.filter(
            user=request.user, 
            bookmark_type='Other'
        ).select_related('pyq', 'test_session', 'pyq__unit', 'pyq__unit__subject',
                         'pyq__difficulty', 'pyq__types')

        def serialize_mcq_bookmark(bookmark):
            """Serialize MCQ bookmark with complete data"""
            try:
                mcq_data = {
                    'bkmk_id': bookmark.bkmk_id,
                    'bookmark_type': bookmark.bookmark_type,
                    'created_at': bookmark.created_at.isoformat(),
                    'mcq': {
                        'uid': str(bookmark.mcq.uid),
                        'text': bookmark.mcq.text,
                        'subject': bookmark.mcq.topic.chapter.unit.subject.name if bookmark.mcq.topic else 'Unknown Subject',
                        'topic': bookmark.mcq.topic.name if bookmark.mcq.topic else 'Unknown Topic',
                        'difficulty': bookmark.mcq.difficulty.name if bookmark.mcq.difficulty else None,
                        'option_1': bookmark.mcq.option_1 or '',
                        'option_2': bookmark.mcq.option_2 or '',
                        'option_3': bookmark.mcq.option_3 or '',
                        'option_4': bookmark.mcq.option_4 or '',
                        'correct_option': bookmark.mcq.correct_option or '',
                        'explanation': bookmark.mcq.explanation or '',
                        'image': request.build_absolute_uri(bookmark.mcq.image.url) if bookmark.mcq.image else None,
                        'mcq_type': bookmark.mcq.types.types if bookmark.mcq.types else 'General',
                        'high_yield': bookmark.mcq.hig_yield,
                        'pyq': bookmark.mcq.pyq,
                        'pyq_cat': bookmark.mcq.pyq_cat or '',
                        'pyq_year': bookmark.mcq.pyq_year or '',
                        'mcq_code': bookmark.mcq.mcqcode or '',
                        'correct_attempts': bookmark.mcq.correct_attempts,
                        'incorrect_attempts': bookmark.mcq.incorrect_attempts,
                    },
                    'test_session': {
                        'test_id': bookmark.test_session.test_id,
                        'created_at': bookmark.test_session.created_at.isoformat(),
                        'mode': bookmark.test_session.mode or '',
                        'pyq': bookmark.test_session.pyq,
                    },
                    'question_type': 'mcq'
                }
                return mcq_data
            except AttributeError as e:
                # Handle missing relationships gracefully
                return {
                    'bkmk_id': bookmark.bkmk_id,
                    'bookmark_type': bookmark.bookmark_type,
                    'created_at': bookmark.created_at.isoformat(),
                    'mcq': {
                        'uid': str(bookmark.mcq.uid),
                        'text': bookmark.mcq.text,
                        'subject': 'Unknown Subject',
                        'topic': 'Unknown Topic',
                        'difficulty': None,
                        'option_1': bookmark.mcq.option_1 or '',
                        'option_2': bookmark.mcq.option_2 or '',
                        'option_3': bookmark.mcq.option_3 or '',
                        'option_4': bookmark.mcq.option_4 or '',
                        'correct_option': bookmark.mcq.correct_option or '',
                        'explanation': bookmark.mcq.explanation or '',
                        'image': None,
                        'mcq_type': 'General',
                        'high_yield': bookmark.mcq.hig_yield,
                        'pyq': bookmark.mcq.pyq,
                        'pyq_cat': bookmark.mcq.pyq_cat or '',
                        'pyq_year': bookmark.mcq.pyq_year or '',
                        'mcq_code': bookmark.mcq.mcqcode or '',
                        'correct_attempts': bookmark.mcq.correct_attempts,
                        'incorrect_attempts': bookmark.mcq.incorrect_attempts,
                    },
                    'test_session': {
                        'test_id': bookmark.test_session.test_id,
                        'created_at': bookmark.test_session.created_at.isoformat(),
                        'mode': bookmark.test_session.mode or '',
                        'pyq': bookmark.test_session.pyq,
                    },
                    'question_type': 'mcq'
                }

        def serialize_pyq_bookmark(bookmark):
            """Serialize PYQ bookmark with complete data"""
            try:
                # Get exam display string
                exam_display = ''
                if bookmark.pyq.pyq_cat:
                    exam_display = bookmark.pyq.pyq_cat
                    
                    # Add month for exams that happen multiple times per year
                    if hasattr(bookmark.pyq, 'pyq_month') and bookmark.pyq.pyq_month and bookmark.pyq.pyq_cat in ['INI-CET', 'FMGE']:
                        exam_display += f" {bookmark.pyq.pyq_month}"
                    
                    # Add year if available
                    if bookmark.pyq.pyq_year:
                        exam_display += f" {bookmark.pyq.pyq_year}"

                pyq_data = {
                    'bkmk_id': bookmark.bkmk_id,
                    'bookmark_type': bookmark.bookmark_type,
                    'created_at': bookmark.created_at.isoformat(),
                    'mcq': {  # Keep same structure as MCQ for frontend compatibility
                        'uid': str(bookmark.pyq.uid),
                        'text': bookmark.pyq.text,
                        'subject': bookmark.pyq.unit.subject.name if bookmark.pyq.unit and bookmark.pyq.unit.subject else 'Unknown Subject',
                        'topic': bookmark.pyq.topic or (bookmark.pyq.unit.name if bookmark.pyq.unit else 'PYQ Topic'),
                        'difficulty': bookmark.pyq.difficulty.name if bookmark.pyq.difficulty else None,
                        'option_1': bookmark.pyq.option_1 or '',
                        'option_2': bookmark.pyq.option_2 or '',
                        'option_3': bookmark.pyq.option_3 or '',
                        'option_4': bookmark.pyq.option_4 or '',
                        'correct_option': bookmark.pyq.correct_option or '',
                        'explanation': bookmark.pyq.explanation or '',
                        'image': request.build_absolute_uri(bookmark.pyq.image.url) if bookmark.pyq.image else None,
                        'mcq_type': bookmark.pyq.types.types if bookmark.pyq.types else 'General',
                        'high_yield': bookmark.pyq.hig_yield,
                        'pyq': True,  # Always True for PYQ
                        'pyq_cat': bookmark.pyq.pyq_cat or '',
                        'pyq_year': bookmark.pyq.pyq_year or '',
                        'pyq_month': getattr(bookmark.pyq, 'pyq_month', ''),
                        'pyq_code': bookmark.pyq.pyqcode or '',
                        'correct_attempts': bookmark.pyq.correct_attempts,
                        'incorrect_attempts': bookmark.pyq.incorrect_attempts,
                        'exam_display': exam_display,
                    },
                    'test_session': {
                        'test_id': bookmark.test_session.test_id,
                        'created_at': bookmark.test_session.created_at.isoformat(),
                        'mode': bookmark.test_session.mode or '',
                        'pyq': bookmark.test_session.pyq,
                    },
                    'question_type': 'pyq'
                }
                return pyq_data
            except AttributeError as e:
                # Handle missing relationships gracefully
                return {
                    'bkmk_id': bookmark.bkmk_id,
                    'bookmark_type': bookmark.bookmark_type,
                    'created_at': bookmark.created_at.isoformat(),
                    'mcq': {
                        'uid': str(bookmark.pyq.uid),
                        'text': bookmark.pyq.text,
                        'subject': 'Unknown Subject',
                        'topic': 'PYQ Topic',
                        'difficulty': None,
                        'option_1': bookmark.pyq.option_1 or '',
                        'option_2': bookmark.pyq.option_2 or '',
                        'option_3': bookmark.pyq.option_3 or '',
                        'option_4': bookmark.pyq.option_4 or '',
                        'correct_option': bookmark.pyq.correct_option or '',
                        'explanation': bookmark.pyq.explanation or '',
                        'image': None,
                        'mcq_type': 'General',
                        'high_yield': bookmark.pyq.hig_yield,
                        'pyq': True,
                        'pyq_cat': bookmark.pyq.pyq_cat or '',
                        'pyq_year': bookmark.pyq.pyq_year or '',
                        'pyq_month': '',
                        'pyq_code': bookmark.pyq.pyqcode or '',
                        'correct_attempts': bookmark.pyq.correct_attempts,
                        'incorrect_attempts': bookmark.pyq.incorrect_attempts,
                        'exam_display': bookmark.pyq.pyq_cat or 'PYQ',
                    },
                    'test_session': {
                        'test_id': bookmark.test_session.test_id,
                        'created_at': bookmark.test_session.created_at.isoformat(),
                        'mode': bookmark.test_session.mode or '',
                        'pyq': bookmark.test_session.pyq,
                    },
                    'question_type': 'pyq'
                }

        def combine_and_sort_bookmarks(mcq_bookmarks, pyq_bookmarks):
            """Combine MCQ and PYQ bookmarks and sort by creation date"""
            combined = []
            
            # Add MCQ bookmarks
            for bookmark in mcq_bookmarks:
                try:
                    serialized = serialize_mcq_bookmark(bookmark)
                    combined.append(serialized)
                except Exception as e:
                    print(f"Error serializing MCQ bookmark {bookmark.bkmk_id}: {e}")
                    continue
            
            # Add PYQ bookmarks
            for bookmark in pyq_bookmarks:
                try:
                    serialized = serialize_pyq_bookmark(bookmark)
                    combined.append(serialized)
                except Exception as e:
                    print(f"Error serializing PYQ bookmark {bookmark.bkmk_id}: {e}")
                    continue
            
            # Sort by creation date (newest first)
            combined.sort(key=lambda x: x['created_at'], reverse=True)
            return combined

        # Combine and serialize bookmarks
        star_bookmarks = combine_and_sort_bookmarks(mcq_star_bookmarks, pyq_star_bookmarks)
        unstudied_bookmarks = combine_and_sort_bookmarks(mcq_unstudied_bookmarks, pyq_unstudied_bookmarks)
        other_bookmarks = combine_and_sort_bookmarks(mcq_other_bookmarks, pyq_other_bookmarks)

        # Calculate statistics
        total_bookmarks = len(star_bookmarks) + len(unstudied_bookmarks) + len(other_bookmarks)
        mcq_count = len(mcq_star_bookmarks) + len(mcq_unstudied_bookmarks) + len(mcq_other_bookmarks)
        pyq_count = len(pyq_star_bookmarks) + len(pyq_unstudied_bookmarks) + len(pyq_other_bookmarks)

        response_data = {
            'success': True,
            'bookmarks': {
                'star': star_bookmarks,
                'unstudied': unstudied_bookmarks,
                'other': other_bookmarks
            },
            'statistics': {
                'total_bookmarks': total_bookmarks,
                'star_count': len(star_bookmarks),
                'unstudied_count': len(unstudied_bookmarks),
                'other_count': len(other_bookmarks),
                'mcq_count': mcq_count,
                'pyq_count': pyq_count,
            },
            'message': f'Successfully loaded {total_bookmarks} bookmarks ({mcq_count} MCQs, {pyq_count} PYQs)'
        }
        
        return Response(response_data)
        
    except Exception as e:
        print(f"Error in mobile_bookmarks_home: {e}")  # Add logging
        return Response({
            'success': False,
            'error': str(e),
            'bookmarks': {
                'star': [],
                'unstudied': [],
                'other': []
            },
            'statistics': {
                'total_bookmarks': 0,
                'star_count': 0,
                'unstudied_count': 0,
                'other_count': 0,
                'mcq_count': 0,
                'pyq_count': 0,
            }
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def mobile_delete_bookmark(request, email_token, bkmk_id):
    """
    Mobile API version of delete_bookmark
    Handles both MCQ and PYQ bookmark deletion
    """
    try:
        from pyqs.models import PYQBookmark
        
        # Try to find MCQ bookmark first
        try:
            bookmark = Bookmark.objects.get(bkmk_id=bkmk_id, user=request.user)
            bookmark.delete()
            return Response({
                'success': True,
                'message': 'MCQ bookmark deleted successfully',
                'bookmark_type': 'mcq'
            })
        except Bookmark.DoesNotExist:
            # If not found, try PYQ bookmark
            try:
                pyq_bookmark = PYQBookmark.objects.get(bkmk_id=bkmk_id, user=request.user)
                pyq_bookmark.delete()
                return Response({
                    'success': True,
                    'message': 'PYQ bookmark deleted successfully',
                    'bookmark_type': 'pyq'
                })
            except PYQBookmark.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Bookmark not found'
                }, status=status.HTTP_404_NOT_FOUND)
                
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





@login_required(login_url='/')
@csrf_exempt  
def api_submit_quiz(request):
    if request.method == 'POST':
        try:
            mcq_ids = request.POST.getlist('mcq_ids')
            test_id = request.POST.get('test_id')
            
            if not mcq_ids or not test_id:
                return JsonResponse({
                    'error': 'mcq_ids and test_id are required'
                }, status=400)
            
            user = request.user
            test_session = TestSession.objects.get(user=user, test_id=test_id)
            
            # Get model class based on pyq flag
            model_class = get_mcq_model_for_session(test_session)
            
            mcq_data = []
            hierarchy_stats = {}  # Will store either unit-topic or unit-chapter-topic stats
            difficulty_stats = {'Easy': {'correct': 0, 'incorrect': 0, 'not_attempted': 0, 'total': 0},
                              'Medium': {'correct': 0, 'incorrect': 0, 'not_attempted': 0, 'total': 0},
                              'Tough': {'correct': 0, 'incorrect': 0, 'not_attempted': 0, 'total': 0}}
            
            # Get test answers to check attempt status
            test_answers = TestAnswer.objects.filter(test_session=test_session)
            answer_map = {str(answer.mcq_uid): answer for answer in test_answers}
            
            for mcq_id in mcq_ids:
                try:
                    mcq = model_class.objects.get(uid=mcq_id)
                    total_attempts = mcq.correct_attempts + mcq.incorrect_attempts
                    correct_percentage = (mcq.correct_attempts / total_attempts) * 100 if total_attempts > 0 else 0
                    incorrect_percentage = (mcq.incorrect_attempts / total_attempts) * 100 if total_attempts > 0 else 0
                    
                    # Get test answer for this MCQ
                    test_answer = answer_map.get(str(mcq_id))
                    
                    # Process Hierarchy Statistics based on session type
                    if test_session.pyq:
                        # PYQ Hierarchy: Subject -> Unit -> Topic (optional)
                        if mcq.unit and mcq.unit.subject:
                            subject_name = mcq.unit.subject.name
                            unit_name = mcq.unit.name
                            topic_name = mcq.topic if mcq.topic and mcq.topic.strip() else None
                            
                            if topic_name:
                                hierarchy_key = f"{subject_name}|{unit_name}|{topic_name}"
                                display_hierarchy = f"{subject_name} → {unit_name} → {topic_name}"
                            else:
                                hierarchy_key = f"{subject_name}|{unit_name}"
                                display_hierarchy = f"{subject_name} → {unit_name}"
                        else:
                            hierarchy_key = "Unknown Subject|Unknown Unit"
                            display_hierarchy = "Unknown Subject → Unknown Unit"
                            subject_name = "Unknown Subject"
                            unit_name = "Unknown Unit"
                    else:
                        # MCQ Hierarchy: Subject -> Unit -> Chapter -> Topic
                        if mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit and mcq.topic.chapter.unit.subject:
                            subject_name = mcq.topic.chapter.unit.subject.name
                            unit_name = mcq.topic.chapter.unit.name
                            chapter_name = mcq.topic.chapter.name
                            topic_name = mcq.topic.name
                            
                            hierarchy_key = f"{subject_name}|{unit_name}|{chapter_name}|{topic_name}"
                            display_hierarchy = f"{subject_name} → {unit_name} → {chapter_name} → {topic_name}"
                        else:
                            hierarchy_key = "Unknown Subject|Unknown Unit|Unknown Chapter|Unknown Topic"
                            display_hierarchy = "Unknown Subject → Unknown Unit → Unknown Chapter → Unknown Topic"
                            subject_name = "Unknown Subject"
                            unit_name = "Unknown Unit"
                            chapter_name = "Unknown Chapter"
                            topic_name = "Unknown Topic"
                    
                    # Initialize hierarchy stats if not exists
                    if hierarchy_key not in hierarchy_stats:
                        hierarchy_stats[hierarchy_key] = {
                            'subject': subject_name,
                            'hierarchy_display': display_hierarchy,
                            'total': 0,
                            'correct': 0,
                            'incorrect': 0,
                            'not_attempted': 0
                        }
                    
                    hierarchy_stats[hierarchy_key]['total'] += 1
                    
                    # Process Difficulty Statistics
                    difficulty_name = mcq.difficulty.name if mcq.difficulty else 'Medium'  # Default to Medium
                    if difficulty_name not in difficulty_stats:
                        difficulty_stats[difficulty_name] = {'correct': 0, 'incorrect': 0, 'not_attempted': 0, 'total': 0}
                    
                    difficulty_stats[difficulty_name]['total'] += 1
                    
                    # Determine answer status and update stats
                    if test_answer and test_answer.is_attempted:
                        if test_answer.correct:
                            hierarchy_stats[hierarchy_key]['correct'] += 1
                            difficulty_stats[difficulty_name]['correct'] += 1
                        else:
                            hierarchy_stats[hierarchy_key]['incorrect'] += 1
                            difficulty_stats[difficulty_name]['incorrect'] += 1
                    else:
                        hierarchy_stats[hierarchy_key]['not_attempted'] += 1
                        difficulty_stats[difficulty_name]['not_attempted'] += 1
                    
                    mcq_data.append({
                        'uid': mcq.uid,
                        'correct_option': mcq.correct_option,
                        'explanation': mcq.explanation,
                        'total_attempts': total_attempts,
                        'correct_percentage': correct_percentage,
                        'incorrect_percentage': incorrect_percentage,
                    })
                    
                except model_class.DoesNotExist:
                    continue
            
            # Convert hierarchy_stats to list for easier frontend consumption
            hierarchy_list = []
            for key, stats in hierarchy_stats.items():
                hierarchy_list.append({
                    'hierarchy_key': key,
                    'subject': stats['subject'],
                    'hierarchy_display': stats['hierarchy_display'],
                    'total_questions': stats['total'],
                    'correct': stats['correct'],
                    'incorrect': stats['incorrect'],
                    'not_attempted': stats['not_attempted'],
                    'accuracy_percentage': round((stats['correct'] / stats['total']) * 100, 1) if stats['total'] > 0 else 0
                })
            
            # Sort hierarchy list by subject name and then by hierarchy display
            hierarchy_list.sort(key=lambda x: (x['subject'], x['hierarchy_display']))
            
            # Convert difficulty_stats to list
            difficulty_list = []
            for difficulty, stats in difficulty_stats.items():
                if stats['total'] > 0:  # Only include difficulties that have questions
                    difficulty_list.append({
                        'difficulty': difficulty,
                        'total_questions': stats['total'],
                        'correct': stats['correct'],
                        'incorrect': stats['incorrect'],
                        'not_attempted': stats['not_attempted'],
                        'accuracy_percentage': round((stats['correct'] / stats['total']) * 100, 1) if stats['total'] > 0 else 0
                    })
            
            # Sort difficulty list by a predefined order
            difficulty_order = {'Easy': 1, 'Medium': 2, 'Tough': 3}
            difficulty_list.sort(key=lambda x: difficulty_order.get(x['difficulty'], 999))
            
            return JsonResponse({
                'mcq_data': mcq_data,
                'hierarchy_stats': hierarchy_list,
                'difficulty_stats': difficulty_list,
                'is_pyq_session': test_session.pyq,  # To help frontend determine table headers
                'session_type': 'PYQ Practice' if test_session.pyq else 'MCQ Practice'
            }, safe=False)
            
        except TestSession.DoesNotExist:
            return JsonResponse({
                'error': 'Test session not found'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'error': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({
        'error': 'Method not allowed'
    }, status=405)


def get_mcq_instance_by_uid(test_session, mcq_uid):
    """
    Get MCQ instance by UID from the test session
    """
    try:
        if test_session.pyq:
            # 🔥 FIX: Import and use PYQ model correctly
            from pyqs.models import PYQ
            print(f"🔍 DEBUG: Looking for PYQ with UID: {mcq_uid}")
            pyq = PYQ.objects.get(uid=mcq_uid)
            print(f"✅ DEBUG: Found PYQ - correct_option: {pyq.correct_option}")
            return pyq
        else:
            # For regular sessions, get from MCQ model
            from .models import MCQ
            print(f"🔍 DEBUG: Looking for MCQ with UID: {mcq_uid}")
            mcq = MCQ.objects.get(uid=mcq_uid)
            print(f"✅ DEBUG: Found MCQ - correct_option: {mcq.correct_option}")
            return mcq
    except Exception as e:
        print(f"❌ DEBUG: Error in get_mcq_instance_by_uid: {str(e)}")
        print(f"❌ DEBUG: test_session.pyq = {test_session.pyq}")
        print(f"❌ DEBUG: mcq_uid = {mcq_uid}")
        return None



@login_required(login_url='/')
@csrf_exempt
def api_save_answer(request):
    if request.method == 'POST':
        user = request.user
        test_id = request.POST.get('test_id')
        mcq_uid = request.POST.get('mcq_uid')
        selected_option = request.POST.get('selected_option')
        time_spent = request.POST.get('time_spent')
        print("time_per que", time_spent)
        time_taken = request.POST.get('time_taken')
        mode = request.POST.get('mode')
        selectedanstext = request.POST.get('selectedanstext')
        
        # Safe time conversion
        total_seconds = 0
        if time_taken and ':' in str(time_taken):
            try:
                parts = str(time_taken).strip().split(':')
                if len(parts) == 2:
                    minutes, seconds = map(int, parts)
                    total_seconds = minutes * 60 + seconds
            except (ValueError, AttributeError):
                total_seconds = 0
        print("TIME liya",total_seconds)
        # Safe time_spent conversion
        time_spent_int = 0
        if time_spent:
            try:
                time_spent_int = int(float(str(time_spent)))
            except (ValueError, TypeError):
                time_spent_int = 0

        try:
            test_session = TestSession.objects.get(user=user, test_id=test_id)
            test_answer = TestAnswer.objects.get(test_session=test_session, mcq_uid=mcq_uid)

            # Update session total time
            test_session.timetaken = total_seconds
            test_session.save()

            # Handle instant mode
            if mode == 'instant':
                if not test_answer.is_attempted:
                    if time_spent_int > 0:
                        test_answer.timespent = time_spent_int
                    
                    if selected_option is not None and selected_option != "":

                        test_answer.selected_option = selected_option
                        test_answer.selected_optiontext = selectedanstext
                        test_answer.is_attempted = True
                        # 🔥 NEW: Check if answer is correct and set is_correct field
                            
                    test_answer.save()

                    # Return answer details for instant mode
                    if selected_option and selected_option != "":
                        mcq = get_mcq_instance_by_uid(test_session, mcq_uid)
                        if mcq:
                            test_answer.correct = selectedanstext == mcq.correct_option
                            test_answer.save()
                            total_attempts = mcq.correct_attempts + mcq.incorrect_attempts
                            correct_percentage = (mcq.correct_attempts / total_attempts) * 100 if total_attempts > 0 else 0
                            incorrect_percentage = (mcq.incorrect_attempts / total_attempts) * 100 if total_attempts > 0 else 0
                            
                            return JsonResponse({
                                'correct_option': mcq.correct_option,
                                'explanation': mcq.explanation,
                                'correct_percentage': correct_percentage,
                                'incorrect_percentage': incorrect_percentage
                            })

            # Handle test mode
            elif mode == 'test':
                if selected_option is not None and selected_option != "":
                    test_answer.selected_option = selected_option
                    test_answer.selected_optiontext = selectedanstext
                    test_answer.is_attempted = True
                
                if time_spent_int > 0:
                    test_answer.timespent = time_spent_int
                
                test_answer.save()

            return JsonResponse({'status': 'success'})

        except (TestSession.DoesNotExist, TestAnswer.DoesNotExist):
            return JsonResponse({
                'status': 'error',
                'message': 'Session or Answer not found'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Method not allowed'
    }, status=405)


def get_mcq_model_for_session(test_session):
    """
    Returns the appropriate model class (PYQ or MCQ) based on TestSession.pyq flag
    """
    if test_session.pyq:
        from pyqs.models import PYQ
        return PYQ
    else:
        from mcqs.models import MCQ
        return MCQ

@login_required(login_url='/')
@csrf_exempt
def api_submitted_active(request):
    print("SUBMIT")
    print(f"Request method: {request.method}")
    print(f"POST data: {dict(request.POST)}")
    
    if request.method == 'POST':
        print("Inside POST block")
        user = request.user
        
        # Handle user_choices from FormData format
        user_choices = {}
        for key, value in request.POST.items():
            if key.startswith('user_choices[') and key.endswith(']'):
                mcq_uid = key[12:-1]  # Remove 'user_choices[' and ']'
                # ✅ FIX: Clean the UUID string by removing extra quotes and brackets
                mcq_uid = mcq_uid.strip().strip('"').strip('[').strip(']').strip('"')
                user_choices[mcq_uid] = value
        
        print(f"User choices found: {user_choices}")
        
        # If no FormData format, try direct parameter
        if not user_choices:
            user_choices = request.POST.get('userchoices', {})
            if isinstance(user_choices, str):
                try:
                    user_choices = json.loads(user_choices)
                except json.JSONDecodeError:
                    user_choices = {}
        
        test_id = request.POST.get('test_id')
        curr_mcq_uid = request.POST.get('current_que_uid')
        timespent = request.POST.get('time_spent') or request.POST.get('timespent')
        print("timespent", timespent)
        timetaken = request.POST.get('time_taken') or request.POST.get('timetaken')
        mode = request.POST.get('mode')
        
        print(f"Parameters: test_id={test_id}, mode={mode}, timetaken={timetaken}")
        
        # Validate required parameters
        if not test_id:
            print("ERROR: Missing test_id")
            return JsonResponse({
                'status': 'error',
                'message': 'test_id is required'
            }, status=400)
        
        if not mode:
            print("ERROR: Missing mode")
            return JsonResponse({
                'status': 'error',
                'message': 'mode is required'
            }, status=400)
        
        # Safe time conversion
        total_seconds = 0
        if timetaken and ':' in str(timetaken):
            try:
                parts = str(timetaken).strip().split(':')
                if len(parts) == 2:
                    minutes, seconds = map(int, parts)
                    total_seconds = minutes * 60 + seconds
                    print(f"Time converted: {total_seconds} seconds")
            except (ValueError, AttributeError) as e:
                print(f"Time conversion error: {e}")
                total_seconds = 0
        
        try:
            profile = request.user.profile
            print("User profile found")
        except AttributeError:
            print("ERROR: No user profile")
            return JsonResponse({
                'status': 'error',
                'message': 'User profile not found'
            }, status=400)

        score = 0
        total_questions = 0
        incorrect_answers = 0
        not_attempted = 0
        correct_answers = {}

        try:
            print("Starting transaction...")
            with transaction.atomic():
                test_session = TestSession.objects.get(user=user, test_id=test_id)
                print(f"Test session found: {test_session.test_id}")
                
                # Handle the current question's time spent
                if curr_mcq_uid and timespent:
                    print(f"Updating time for question: {curr_mcq_uid}")
                    try:
                        test_answer = TestAnswer.objects.get(test_session=test_session, mcq_uid=curr_mcq_uid)
                        if mode == 'instant':
                            if not test_answer.is_attempted:
                                test_answer.timespent = timespent
                                test_answer.save()
                                print("Time updated for instant mode")
                        else:
                            test_answer.timespent = timespent
                            test_answer.save()
                            print("Time updated for test mode")
                    except TestAnswer.DoesNotExist:
                        print(f"TestAnswer not found for {curr_mcq_uid}")

                if test_session.submitted:
                    print("ERROR: Test already submitted")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Test already submitted'
                    }, status=400)

                print("Getting model class...")
                # Get model class based on pyq flag
                model_class = get_mcq_model_for_session(test_session)
                print(f"Model class: {model_class}")
                
                if mode == 'test':
                    print("Processing test mode...")
                    # ✅ EXACT SAME LOGIC AS INSTANT MODE
                    test_answers = TestAnswer.objects.filter(test_session=test_session)
                    total_questions = test_answers.count()
                    
                    for test_answer in test_answers:
                        try:
                            mcq = model_class.objects.get(uid=test_answer.mcq_uid)
                            correct_answers[str(mcq.uid)] = mcq.correct_option
                            
                            if not test_answer.is_attempted and str(mcq.uid) in user_choices:
                                test_answer.selected_optiontext = user_choices[str(mcq.uid)]
                                test_answer.save()
                                
                            if test_answer.selected_optiontext and not test_answer.is_attempted:
                                test_answer.is_attempted = True
                                test_answer.save()
                                
                            if test_answer.is_attempted:
                                if test_answer.selected_optiontext == mcq.correct_option:
                                    score += 1
                                    test_answer.correct = True
                                    test_answer.save()
                                    mcq.correct_attempts += 1
                                    mcq.save()
                                else:
                                    mcq.incorrect_attempts += 1
                                    mcq.save()
                                    incorrect_answers += 1
                            else:
                                not_attempted += 1
                        except Exception as e:
                            print(f"ERROR: Unexpected error in test mode: {str(e)}")
                            continue
            


                        
                else:  # instant mode
                    print("Processing instant mode...")
                    # Instant mode logic
                    test_answers = TestAnswer.objects.filter(test_session=test_session)
                    total_questions = test_answers.count()
                    
                    for test_answer in test_answers:
                        try:
                            mcq = model_class.objects.get(uid=test_answer.mcq_uid)
                            correct_answers[str(mcq.uid)] = mcq.correct_option
                            
                            if not test_answer.is_attempted and str(mcq.uid) in user_choices:
                                test_answer.selected_optiontext = user_choices[str(mcq.uid)]
                                test_answer.save()
                                
                            if test_answer.selected_optiontext and not test_answer.is_attempted:
                                test_answer.is_attempted = True
                                test_answer.save()
                                
                            if test_answer.is_attempted:
                                if test_answer.selected_optiontext == mcq.correct_option:
                                    score += 1
                                    test_answer.correct = True
                                    test_answer.save()
                                    mcq.correct_attempts += 1
                                    mcq.save()
                                else:
                                    mcq.incorrect_attempts += 1
                                    mcq.save()
                                    incorrect_answers += 1
                            else:
                                not_attempted += 1
                        except Exception as e:
                            print(f"ERROR: Unexpected error in instant mode: {str(e)}")
                            continue

                # Save test session data
                test_session.timetaken = total_seconds
                test_session.submitted = True
                test_session.score = score
                test_session.save()

        except TestSession.DoesNotExist:
            print("ERROR: Test session not found")
            return JsonResponse({
                'status': 'error',
                'message': 'Test session not found'
            }, status=404)
        except Exception as e:
            print(f"ERROR Error in submitted_active: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': 'Server error occurred'
            }, status=500)
        
        session_time_taken = int(test_session.timetaken) if test_session.timetaken else 0

        # Response data and profile updates (outside transaction)
        response_data = {
            'status': 'success',
            'score': score,
            'total_questions': total_questions,
            'incorrect_answers': incorrect_answers,
            'not_attempted': not_attempted,
            'correct_answers': correct_answers,
            'time_taken': session_time_taken,  # ✅ NEW: Pass time_taken from TestSession.timetaken
            'percentage': round((score / total_questions) * 100, 2) if total_questions > 0 else 0,
            'test_id': test_id,
            'submitted_at': test_session.timestamp.isoformat(),
            'total_time_allocated': int(test_session.totaltime) if test_session.totaltime else 0,
            'mode': mode,
            'message': f'Test submitted successfully! Score: {score}/{total_questions}',
        }

        # Clear current test
        if profile.current_test == test_id:
            profile.current_test = ''
            profile.save()
        elif hasattr(profile, 'hive_current_test') and profile.hive_current_test == test_id:
            profile.hive_current_test = ''
            profile.save()
        elif hasattr(profile, 'mock_current_test') and profile.mock_current_test == test_id:
            profile.mock_current_test = ''
            profile.save()
        elif hasattr(profile, 'pyq_test') and profile.pyq_test == test_id:  # 🔥 NEW: Clear PYQ test
            profile.pyq_test = ''
            profile.save()

        return JsonResponse(response_data)

    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_continue_test_mobile(request, test_id):
    """
    Mobile API version of continue_test
    Returns test data as JSON for continuing an unsubmitted test
    """
    try:
        user = request.user
        
        try:
            test_session = TestSession.objects.get(user=user, test_id=test_id)
            mode = test_session.mode
        except TestSession.DoesNotExist:
            return Response({
                'status': 'error', 
                'message': 'Test session not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if test_session.submitted:
            return Response({
                'status': 'error',
                'message': 'Test already submitted'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        profile = user.profile
        is_mock_session = False
        
        if hasattr(profile, 'mock_current_test') and profile.mock_current_test == test_id:
            is_mock_session = True
            logger.info(f"✅ Continuing MOCK practice session: {test_id}")
        else:
            logger.info(f"✅ Continuing regular MCQ session: {test_id}")
        # Retrieve test answers in the order they were saved
        test_answers = TestAnswer.objects.filter(test_session=test_session).order_by('id')
        
        # Get model class and serializer based on pyq flag
        model_class = get_mcq_model_for_session(test_session)
        
        if test_session.pyq:
            from pyqs.serializers import PYQSerializer
            serializer_class = PYQSerializer
        else:
            from mcqs.serializers import MCQSerializer
            serializer_class = MCQSerializer
        
        mcqs_data = []
        selected_answers = {}
        timespent = {}
        answer_details = {}
        time_taken = getattr(test_session, 'timetaken', 0)
        total_time = test_session.totaltime
        total_time_minutes = total_time / 60
        time_left_seconds = total_time - time_taken
        selected_option_texts = {}
        time_left_minutes = time_left_seconds / 60

        for index, answer in enumerate(test_answers):
            try:
                mcq = model_class.objects.get(uid=answer.mcq_uid)
            except model_class.DoesNotExist:
                continue

            # 🔥 FIX: For instant mode, use correct_option directly (it's already text)
            if mode == "instant" and answer.is_attempted:
                # mcq.correct_option is already the text value, not A/B/C/D
                correct_option_text = mcq.correct_option or "No correct option set"
                
                # ALWAYS create answer_details entry for instant mode
                answer_details[index] = {
                    'correct_option': correct_option_text,  # 🔥 FIX: Use direct text
                    'explanation': mcq.explanation or "No explanation available",
                    'correct_attempts': mcq.correct_attempts,
                    'incorrect_attempts': mcq.incorrect_attempts
                }

            if answer.is_attempted:
                # Map selected option letter to text
                selected_option_text = {
                    "A": mcq.option_1,
                    "B": mcq.option_2,
                    "C": mcq.option_3,
                    "D": mcq.option_4
                }.get(answer.selected_option)
                
                if selected_option_text:
                    selected_option_texts[index] = selected_option_text

            serializer = serializer_class(mcq)
            mcq_data = serializer.data
            if mcq.image:
                mcq_data['image'] = request.build_absolute_uri(mcq.image.url)
            else:
                mcq_data['image'] = None
            # Add selected option as TEXT (not A/B/C/D)
            mcq_data['selected_option'] = answer.selected_optiontext if answer.is_attempted else ''
            mcq_data['timespent'] = float(answer.timespent)

            # 🔥 FIX: For instant mode attempted questions, compare texts directly
            if mode == "instant" and answer.is_attempted:
                selected_option_text = {
                    "A": mcq.option_1,
                    "B": mcq.option_2,
                    "C": mcq.option_3,
                    "D": mcq.option_4
                }.get(answer.selected_option)
                
                print(selected_option_text)
                print(mcq.correct_option)
                # Compare selected text with correct text (both are text now)
                mcq_data['is_correct'] = selected_option_text == mcq.correct_option

            mcqs_data.append(mcq_data)
            selected_answers[index] = answer.selected_option if answer.is_attempted else ''
            timespent[str(mcq.uid)] = float(answer.timespent)


        # Get bookmarks based on test session type
        bookmarked_mcqs = {}
        if test_session.pyq:
            from pyqs.models import PYQBookmark
            bookmarks = PYQBookmark.objects.filter(user=user, test_session=test_session)
            for bookmark in bookmarks:
                bookmarked_mcqs[str(bookmark.pyq.uid)] = bookmark.bookmark_type
        else:
            bookmarks = Bookmark.objects.filter(user=user, test_session=test_session)
            for bookmark in bookmarks:
                bookmarked_mcqs[str(bookmark.mcq.uid)] = bookmark.bookmark_type

        # Prepare response data
        response_data = {
            'success': True,
            'test_data': {
                'mcqs': mcqs_data,
                'count': len(mcqs_data),
                'test_id': test_id,
                'timespent': timespent,
                'selected_answers': selected_answers,
                'bookmarked_mcqs': bookmarked_mcqs,
                'total_time': total_time_minutes,
                'time_left_minutes': time_left_minutes,
                'selected_option_texts': selected_option_texts,
                'mode': mode,
                'is_continuing': True,
                'is_pyq': test_session.pyq,
                'is_mock': is_mock_session  # ✅ AUTO-DETECTED FLAG

            }
        }
        
        # 🔥 FIX: Always add answer_details for instant mode
        if mode == "instant":
            response_data['test_data']['answer_details'] = answer_details
            print(f"✅ Created answer_details for {len(answer_details)} questions")

        return Response(response_data)

    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_check_current_test(request):
    """
    Check if user has any current unsubmitted test
    """
    print("HELOOOO")
    try:
        profile = request.user.profile
        current_test_id = None
        
        # Check different types of current tests
        if profile.current_test:
            current_test_id = profile.current_test
        
        
        if current_test_id:
            try:
                test_session = TestSession.objects.get(user=request.user, test_id=current_test_id)
                if not test_session.submitted:
                    print("NOT SUBMITTED")
                    return Response({
                        'success': True,
                        'has_current_test': True,
                        'test_id': current_test_id,
                        'mode': test_session.mode,
                        'total_questions': test_session.total_questions,
                        'created_at': test_session.created_at.isoformat()
                    })
            except TestSession.DoesNotExist:
                # Clear invalid current test
                profile.current_test = ''
                profile.save()
        
        return Response({
            'success': True,
            'has_current_test': False
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_clear_current_test(request):
    """
    Clear the current active test for the user
    """
    try:
        profile = request.user.profile
        
        # Clear all types of current tests
        profile.current_test = ''
        if hasattr(profile, 'hive_current_test'):
            profile.hive_current_test = ''
        if hasattr(profile, 'mock_current_test'):
            profile.mock_current_test = ''
        
        profile.save()
        
        return Response({
            'success': True,
            'message': 'Current test cleared successfully'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from mcqs.models import TestSession, TestAnswer, MCQ
from pyqs.models import PYQ
import json

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from mcqs.models import TestSession, TestAnswer
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
import json

@csrf_exempt
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_test_sessions(request):
    """Get paginated & filtered test sessions"""
    try:
        user = request.user
        
        # ✅ Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        filter_type = request.GET.get('filter_type', 'all')  # all/pyq/curated/mock
        sort_by = request.GET.get('sort_by', 'recent')  # recent/highest/lowest
        
        # ✅ Base query
        queryset = TestSession.objects.filter(user=user, submitted=True)
        
        # ✅ Apply type filter
        if filter_type == 'pyq':
            queryset = queryset.filter(pyq=True)
        elif filter_type == 'curated':
            queryset = queryset.filter(pyq=False)
            # Exclude mock tests (check selections for MOCK TEST)
            # We'll filter this in Python since it's in JSON field
        elif filter_type == 'mock':
            # We'll filter mock tests in Python
            pass
        
        # ✅ Apply sorting
        if sort_by == 'recent':
            queryset = queryset.order_by('-created_at')
        elif sort_by == 'highest':
            queryset = queryset.order_by('-score', '-created_at')
        elif sort_by == 'lowest':
            queryset = queryset.order_by('score', '-created_at')
        else:
            queryset = queryset.order_by('-created_at')
        
        # ✅ Get all matching sessions (we'll filter mock in Python)
        all_sessions = queryset
        
        sessions_data = []
        
        for session in all_sessions:
            # Parse selections
            selections = []
            if session.selections:
                try:
                    raw_selections = session.selections
                    if isinstance(raw_selections, str):
                        try:
                            raw_selections = json.loads(raw_selections)
                        except json.JSONDecodeError:
                            raw_selections = [raw_selections]
                    
                    if not isinstance(raw_selections, list):
                        raw_selections = [raw_selections]
                    
                    for item in raw_selections:
                        if item is None:
                            continue
                        elif isinstance(item, str):
                            selections.append(item)
                        elif isinstance(item, dict):
                            if 'text' in item and item['text']:
                                selections.append(str(item['text']))
                            else:
                                parts = []
                                for key in ['subject', 'unit', 'chapter', 'topic', 'name']:
                                    if key in item and item[key]:
                                        parts.append(str(item[key]))
                                if parts:
                                    selections.append('->'.join(parts))
                        else:
                            selections.append(str(item))
                except:
                    selections = []
            
            # Check if mock
            is_mock = any('MOCK TEST' in str(s).upper() for s in selections if s)
            
            # ✅ Apply mock filter
            if filter_type == 'mock' and not is_mock:
                continue
            elif filter_type == 'curated' and is_mock:
                continue
            
            # Get answer counts
            answers = TestAnswer.objects.filter(test_session=session)
            total_questions = answers.count()
            
            if total_questions == 0:
                continue
            
            total_correct = answers.filter(correct=True).count()
            total_attempted = answers.exclude(selected_option=None).exclude(selected_option='').count()
            total_incorrect = total_attempted - total_correct
            total_unattempted = total_questions - total_attempted
            accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
            
            sessions_data.append({
                'test_id': str(session.test_id),
                'created_at': session.created_at.isoformat(),
                'submitted': session.submitted,
                'score': float(session.score or 0),
                'total_questions': total_questions,
                'time_taken': float(session.timetaken or 0),
                'total_time': float(session.totaltime or 0),
                'selections': selections,
                'mode': session.mode or 'test',
                'pyq': session.pyq,
                'is_mock': is_mock,
                'total_correct': total_correct,
                'total_incorrect': total_incorrect,
                'total_unattempted': total_unattempted,
                'accuracy': round(accuracy, 2),
            })
        
        # ✅ Apply pagination
        total_count = len(sessions_data)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_data = sessions_data[start_idx:end_idx]
        
        has_more = end_idx < total_count
        
        return Response({
            'success': True,
            'sessions': paginated_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'has_more': has_more,
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_test_session_detail(request, test_id):
    """Get detailed review with full hierarchy"""
    try:
        user = request.user
        
        try:
            test_session = TestSession.objects.get(test_id=test_id, user=user)
        except TestSession.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Test session not found'
            }, status=404)
        
        test_answers = TestAnswer.objects.filter(test_session=test_session)
        question_data = []
        
        for answer in test_answers:
            try:
                if test_session.pyq:
                    pyq = PYQ.objects.get(uid=answer.mcq_uid)
                    
                    # Build PYQ hierarchy
                    hierarchy = []
                    if pyq.unit and pyq.unit.subject:
                        hierarchy.append(pyq.unit.subject.name)
                        hierarchy.append(pyq.unit.name)
                    
                    question_data.append({
                        'mcq_uid': str(pyq.uid),
                        'question_number': len(question_data) + 1,
                        'text': pyq.text,
                        'image': request.build_absolute_uri(pyq.image.url) if pyq.image else None,
                        'options': {
                            'A': pyq.option_1 or '',
                            'B': pyq.option_2 or '',
                            'C': pyq.option_3 or '',
                            'D': pyq.option_4 or '',
                        },
                        'correct_option': pyq.correct_option or '',
                        'selected_option': answer.selected_optiontext,
                        'is_attempted': answer.is_attempted,
                        'is_correct': answer.correct,
                        'time_spent': float(answer.timespent or 0),
                        'explanation': pyq.explanation or None,
                        'hierarchy': ' → '.join(hierarchy) if hierarchy else 'N/A',
                        'topic': pyq.topic if pyq.topic else None,
                        'difficulty': pyq.difficulty.name if pyq.difficulty else 'Medium',
                        'pyq': True,
                        'pyq_cat': pyq.pyq_cat if pyq.pyq_cat else None,
                        'pyq_year': pyq.pyq_year if pyq.pyq_year else None,
                        'pyq_month': pyq.pyq_month if hasattr(pyq, 'pyq_month') and pyq.pyq_month else None,
                    })
                    
                else:
                    mcq = MCQ.objects.get(uid=answer.mcq_uid)
                    
                    # Build MCQ hierarchy: Subject → Unit → Chapter → Topic
                    hierarchy = []
                    if mcq.topic:
                        if mcq.topic.chapter:
                            if mcq.topic.chapter.unit:
                                if mcq.topic.chapter.unit.subject:
                                    hierarchy.append(mcq.topic.chapter.unit.subject.name)
                                hierarchy.append(mcq.topic.chapter.unit.name)
                            hierarchy.append(mcq.topic.chapter.name)
                        hierarchy.append(mcq.topic.name)
                    
                    question_data.append({
                        'mcq_uid': str(mcq.uid),
                        'question_number': len(question_data) + 1,
                        'text': mcq.text,
                        'image': request.build_absolute_uri(mcq.image.url) if mcq.image else None,
                        'options': {
                            'A': mcq.option_1 or '',
                            'B': mcq.option_2 or '',
                            'C': mcq.option_3 or '',
                            'D': mcq.option_4 or '',
                        },
                        'correct_option': mcq.correct_option or '',
                        'selected_option': answer.selected_optiontext,
                        'is_attempted': answer.is_attempted,
                        'is_correct': answer.correct,
                        'time_spent': float(answer.timespent or 0),
                        'explanation': mcq.explanation or None,
                        'hierarchy': ' → '.join(hierarchy) if hierarchy else 'N/A',
                        'topic': None,  # Already in hierarchy
                        'difficulty': mcq.difficulty.name if mcq.difficulty else 'Medium',
                        'pyq': False,
                        'pyq_cat': None,
                        'pyq_year': None,
                        'pyq_month': None,
                    })
                    
            except (MCQ.DoesNotExist, PYQ.DoesNotExist):
                continue
        
        # Calculate stats
        total_questions = len(question_data)
        total_correct = sum(1 for q in question_data if q['is_correct'])
        total_incorrect = sum(1 for q in question_data if q['is_attempted'] and not q['is_correct'])
        total_unattempted = sum(1 for q in question_data if not q['is_attempted'])
        total_attempted = total_correct + total_incorrect
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        correct_percentage = (total_correct / total_questions * 100) if total_questions > 0 else 0
        incorrect_percentage = (total_incorrect / total_questions * 100) if total_questions > 0 else 0
        
        # Parse selections
        selections = []
        raw_selections = []
        if test_session.selections:
            try:
                if isinstance(test_session.selections, str):
                    raw_selections = json.loads(test_session.selections)
                elif isinstance(test_session.selections, list):
                    raw_selections = test_session.selections
                
                if not isinstance(raw_selections, list):
                    raw_selections = [raw_selections]
                
                # Process selections
                for item in raw_selections:
                    if isinstance(item, str):
                        selections.append(item)
                    elif isinstance(item, dict) and 'text' in item:
                        selections.append(item['text'])
            except:
                selections = []
        
        is_mock = any('MOCK TEST' in str(s).upper() for s in selections if s)
        
        # Extract mock exam name if it's a mock test
        mock_exam_name = None
        if is_mock and selections:
            for selection in selections:
                if 'MOCK TEST' in str(selection).upper():
                    parts = str(selection).split(' - ')
                    if len(parts) >= 2:
                        mock_exam_name = parts[1].strip()  # Get 2nd word (exam name)
                    break
        
        session_data = {
            'test_id': str(test_session.test_id),
            'created_at': test_session.created_at.isoformat(),
            'submitted': test_session.submitted,
            'score': float(test_session.score or 0),
            'total_questions': total_questions,
            'time_taken': float(test_session.timetaken or 0),
            'total_time': float(test_session.totaltime or 0),
            'selections': selections,
            'mock_exam_name': mock_exam_name,
            'mode': test_session.mode or 'test',
            'pyq': test_session.pyq,
            'is_mock': is_mock,
            'total_correct': total_correct,
            'total_incorrect': total_incorrect,
            'total_unattempted': total_unattempted,
            'accuracy': round(accuracy, 2),
            'correct_percentage': round(correct_percentage, 1),
            'incorrect_percentage': round(incorrect_percentage, 1),
            'answers': question_data,
        }
        
        return Response({
            'success': True,
            'session': session_data,
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)



@csrf_exempt
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_continue_sessions(request):
    """Get paginated list of incomplete test sessions"""
    try:
        user = request.user
        
        # Get query parameters
        filter_type = request.GET.get('filter_type', 'all')  # all/pyq/curated/mock
        
        # Base query - only non-submitted sessions
        queryset = TestSession.objects.filter(user=user, submitted=False).order_by('-created_at')
        
        # Apply PYQ filter early
        if filter_type == 'pyq':
            queryset = queryset.filter(pyq=True)
        elif filter_type == 'curated':
            queryset = queryset.filter(pyq=False)
        
        sessions_data = []
        
        for session in queryset:
            # Parse selections
            selections = []
            if session.selections:
                try:
                    raw_selections = session.selections
                    if isinstance(raw_selections, str):
                        try:
                            raw_selections = json.loads(raw_selections)
                        except json.JSONDecodeError:
                            raw_selections = [raw_selections]
                    
                    if not isinstance(raw_selections, list):
                        raw_selections = [raw_selections]
                    
                    for item in raw_selections:
                        if item is None:
                            continue
                        elif isinstance(item, str):
                            selections.append(item)
                        elif isinstance(item, dict):
                            if 'text' in item and item['text']:
                                selections.append(str(item['text']))
                            else:
                                parts = []
                                for key in ['subject', 'unit', 'chapter', 'topic', 'name']:
                                    if key in item and item[key]:
                                        parts.append(str(item[key]))
                                if parts:
                                    selections.append('->'.join(parts))
                        else:
                            selections.append(str(item))
                except:
                    selections = []
            
            # Check if mock
            is_mock = any('MOCK TEST' in str(s).upper() for s in selections if s)
            
            # Apply mock/curated filter
            if filter_type == 'mock' and not is_mock:
                continue
            elif filter_type == 'curated' and (is_mock or session.pyq):
                continue
            
            # Get question stats
            answers = TestAnswer.objects.filter(test_session=session)
            total_questions = answers.count()
            
            if total_questions == 0:
                continue
            
            total_attempted = answers.exclude(selected_option=None).exclude(selected_option='').count()
            total_unattempted = total_questions - total_attempted
            progress_percentage = (total_attempted / total_questions * 100) if total_questions > 0 else 0
            
            # Determine session type
            if session.pyq:
                session_type = 'pyq'
            elif is_mock:
                session_type = 'mock'
            else:
                session_type = 'curated'
            
            # Extract mock exam name if applicable
            mock_exam_name = None
            if is_mock and selections:
                for selection in selections:
                    if 'MOCK TEST' in str(selection).upper():
                        parts = str(selection).split(' - ')
                        if len(parts) >= 2:
                            mock_exam_name = parts[1].strip()
                        break
            
            sessions_data.append({
                'test_id': str(session.test_id),
                'created_at': session.created_at.isoformat(),
                'selections': selections,
                'mock_exam_name': mock_exam_name,
                'mode': session.mode or 'test',
                'session_type': session_type,
                'pyq': session.pyq,
                'is_mock': is_mock,
                'total_questions': total_questions,
                'total_attempted': total_attempted,
                'total_unattempted': total_unattempted,
                'progress_percentage': round(progress_percentage, 1),
                'time_spent': float(session.timetaken or 0),
            })
        
        return Response({
            'success': True,
            'sessions': sessions_data,
            'total_count': len(sessions_data),
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
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
def check_mcq_access(request):
    """
    Check if user can start MCQ practice based on:
    0. No incomplete test session exists (current_test is blank)
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
        
        print(f"?? Checking MCQ access for {num_questions} questions")
        print(f"?? User: {user.username}, Free MCQs: {profile.free_mcqs_remaining}")
        
        # ? FIRST CHECK: Does user have an incomplete test?
        if profile.current_test:
            print(f"?? User has incomplete test: {profile.current_test}")
            return Response({
                'success': True,
                'access_granted': False,
                'access_type': 'blocked',
                'has_incomplete_test': True,
                'current_test_id': profile.current_test,
                'message': 'You have an incomplete practice session. Please complete it before starting a new one.',
                'redirect_to': 'continue_test'
            })
        
        print("? No incomplete test found")
        
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
                'has_incomplete_test': False,
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
                'has_incomplete_test': False,
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
            'has_incomplete_test': False,
            'message': f'You need {num_questions} MCQs but only have {profile.free_mcqs_remaining} free attempts remaining. Subscribe to continue unlimited practice.',
            'free_mcqs_remaining': profile.free_mcqs_remaining,
            'required_mcqs': num_questions,
            'shortfall': num_questions - profile.free_mcqs_remaining,
            'has_subscription': False,
            'redirect_to': 'subscription'
        })
        
    except Exception as e:
        print(f"? Error in check_mcq_access: {e}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
