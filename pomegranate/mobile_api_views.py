# apipomegranate/mobile_api_views.py - COMPLETE OPTIMIZED VERSION

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from mcqs.models import TestSession, TestAnswer, MCQ, Subject, Unit, Chapter, Topic
from django.db.models import Sum
from collections import defaultdict
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
import json
import sys
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication

def _get_curated_sessions_cached(user):
    """Helper with caching - avoid recalculating every time"""
    cache_key = f"curated_sessions_{user.id}"
    
    # Try cache first
    cached = cache.get(cache_key)
    if cached:
        print(f"✅ Using CACHED curated sessions: {len(cached)} IDs", flush=True)
        return TestSession.objects.filter(id__in=cached)
    
    print(f"\n{'='*80}", flush=True)
    print(f"🔍 Getting curated sessions for user: {user.username}", flush=True)
    
    base_sessions = TestSession.objects.filter(
        user=user,
        submitted=True,
        pyq=False
    )
    
    count = base_sessions.count()
    print(f"📊 Found {count} submitted non-PYQ sessions", flush=True)
    
    # Filter out Mock sessions
    filtered_ids = []
    for idx, session in enumerate(base_sessions):
        if idx % 100 == 0:
            print(f"  Processing {idx}/{count}...", flush=True)
            
        is_mock = False
        if session.selections:
            try:
                selections = session.selections if isinstance(session.selections, list) else json.loads(session.selections)
                is_mock = any('MOCK TEST' in str(sel).upper() for sel in selections if sel)
            except:
                pass
        
        if not is_mock:
            filtered_ids.append(session.id)
    
    # Cache for 5 minutes
    cache.set(cache_key, filtered_ids, 300)
    
    result = TestSession.objects.filter(id__in=filtered_ids)
    print(f"✅ Curated sessions: {result.count()} (cached 5min)", flush=True)
    print(f"{'='*80}\n", flush=True)
    
    return result


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_overall_stats(request):
    """Get overall performance statistics"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Overall Stats", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=curated_sessions)
        
        total_sessions = curated_sessions.count()
        total_questions = all_answers.count()
        total_attempted = all_answers.filter(is_attempted=True).count()
        total_correct = all_answers.filter(correct=True, is_attempted=True).count()
        total_incorrect = all_answers.filter(correct=False, is_attempted=True).count()
        
        overall_accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        total_score = float(curated_sessions.aggregate(Sum('score'))['score__sum'] or 0)
        
        print(f"✅ SUCCESS: {total_sessions} sessions, {overall_accuracy:.2f}%", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({
            'success': True,
            'overall_stats': {
                'total_sessions': total_sessions,
                'total_questions_answered': total_questions,
                'total_attempted': total_attempted,
                'total_correct': total_correct,
                'total_incorrect': total_incorrect,
                'total_score': total_score,
                'overall_accuracy': round(overall_accuracy, 2),
            }
        })
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_unique_questions(request):
    """Get unique questions statistics"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Unique Questions", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=curated_sessions)
        
        unique_mcq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        total_unique_faced = len(unique_mcq_uids)
        total_mcqs_in_db = MCQ.objects.count()
        
        unique_attempted = set()
        unique_correct = set()
        unique_incorrect = set()
        
        for answer in all_answers:
            if answer.is_attempted:
                unique_attempted.add(answer.mcq_uid)
                if answer.correct:
                    unique_correct.add(answer.mcq_uid)
                else:
                    unique_incorrect.add(answer.mcq_uid)
        
        print(f"✅ SUCCESS: {total_unique_faced}/{total_mcqs_in_db}", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({
            'success': True,
            'unique_question_stats': {
                'total_in_db': total_mcqs_in_db,
                'unique_faced': total_unique_faced,
                'unique_attempted': len(unique_attempted),
                'unique_correct': len(unique_correct),
                'unique_incorrect': len(unique_incorrect),
                'coverage_percentage': round((total_unique_faced / total_mcqs_in_db * 100), 2) if total_mcqs_in_db > 0 else 0,
            }
        })
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_subject_hierarchy(request):
    """Get subject hierarchy - HEAVILY OPTIMIZED"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Subject Hierarchy", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        
        # Get all answers with only needed fields
        all_answers = TestAnswer.objects.filter(
            test_session__in=curated_sessions
        ).only('mcq_uid', 'is_attempted', 'correct')
        
        total_answers = all_answers.count()
        print(f"📊 Processing {total_answers} answers...", flush=True)
        
        # Get unique MCQ UIDs
        mcq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        print(f"🔍 Fetching {len(mcq_uids)} unique MCQs...", flush=True)
        
        # CRITICAL: Fetch ALL MCQs at once with select_related
        mcq_dict = {}
        mcqs = MCQ.objects.filter(uid__in=mcq_uids).select_related(
            'topic__chapter__unit__subject'
        ).only(
            'uid',
            'topic__uid', 'topic__name',
            'topic__chapter__uid', 'topic__chapter__name',
            'topic__chapter__unit__uid', 'topic__chapter__unit__name',
            'topic__chapter__unit__subject__uid', 'topic__chapter__unit__subject__name'
        )
        
        for mcq in mcqs:
            mcq_dict[str(mcq.uid)] = mcq
        
        print(f"✅ Fetched {len(mcq_dict)} MCQs", flush=True)
        
        hierarchy = {}
        processed = 0
        errors = 0
        
        # Process using MCQ dict (NO database queries in loop!)
        for idx, answer in enumerate(all_answers):
            if idx % 1000 == 0:
                print(f"  {idx}/{total_answers} ({(idx/total_answers*100):.1f}%)", flush=True)
            
            mcq = mcq_dict.get(str(answer.mcq_uid))
            
            if not mcq or not (mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit and mcq.topic.chapter.unit.subject):
                errors += 1
                continue
            
            s = mcq.topic.chapter.unit.subject
            u = mcq.topic.chapter.unit
            c = mcq.topic.chapter
            t = mcq.topic
            
            # Initialize structures
            if s.name not in hierarchy:
                hierarchy[s.name] = {'subject_id': str(s.uid), 'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0, 'units': {}}
            
            hierarchy[s.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['attempted'] += 1
                if answer.correct:
                    hierarchy[s.name]['correct'] += 1
            
            if u.name not in hierarchy[s.name]['units']:
                hierarchy[s.name]['units'][u.name] = {'unit_id': str(u.uid), 'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0, 'chapters': {}}
            
            hierarchy[s.name]['units'][u.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['units'][u.name]['attempted'] += 1
                if answer.correct:
                    hierarchy[s.name]['units'][u.name]['correct'] += 1
            
            if c.name not in hierarchy[s.name]['units'][u.name]['chapters']:
                hierarchy[s.name]['units'][u.name]['chapters'][c.name] = {'chapter_id': str(c.uid), 'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0, 'topics': {}}
            
            hierarchy[s.name]['units'][u.name]['chapters'][c.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['units'][u.name]['chapters'][c.name]['attempted'] += 1
                if answer.correct:
                    hierarchy[s.name]['units'][u.name]['chapters'][c.name]['correct'] += 1
            
            if t.name not in hierarchy[s.name]['units'][u.name]['chapters'][c.name]['topics']:
                hierarchy[s.name]['units'][u.name]['chapters'][c.name]['topics'][t.name] = {'topic_id': str(t.uid), 'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0}
            
            hierarchy[s.name]['units'][u.name]['chapters'][c.name]['topics'][t.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['units'][u.name]['chapters'][c.name]['topics'][t.name]['attempted'] += 1
                if answer.correct:
                    hierarchy[s.name]['units'][u.name]['chapters'][c.name]['topics'][t.name]['correct'] += 1
            
            processed += 1
        
        print(f"📊 Processed {processed}, Errors {errors}", flush=True)
        
        # Calculate accuracies
        for sn, sd in hierarchy.items():
            if sd['attempted'] > 0:
                sd['accuracy'] = round((sd['correct'] / sd['attempted'] * 100), 2)
            for un, ud in sd['units'].items():
                if ud['attempted'] > 0:
                    ud['accuracy'] = round((ud['correct'] / ud['attempted'] * 100), 2)
                for cn, cd in ud['chapters'].items():
                    if cd['attempted'] > 0:
                        cd['accuracy'] = round((cd['correct'] / cd['attempted'] * 100), 2)
                    for tn, td in cd['topics'].items():
                        if td['attempted'] > 0:
                            td['accuracy'] = round((td['correct'] / td['attempted'] * 100), 2)
        
        print(f"✅ COMPLETE: {len(hierarchy)} subjects", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({'success': True, 'subject_hierarchy': hierarchy})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_monthly_progress(request):
    """Get monthly progress"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Monthly Progress", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        
        monthly_data = []
        now = timezone.now()
        
        for i in range(5, -1, -1):
            month_start = now - timedelta(days=30 * (i + 1))
            month_end = now - timedelta(days=30 * i)
            
            month_sessions = curated_sessions.filter(created_at__gte=month_start, created_at__lt=month_end)
            
            if month_sessions.exists():
                month_answers = TestAnswer.objects.filter(test_session__in=month_sessions)
                attempted = month_answers.filter(is_attempted=True).count()
                correct = month_answers.filter(correct=True, is_attempted=True).count()
                accuracy = (correct / attempted * 100) if attempted > 0 else 0
                
                monthly_data.append({
                    'month': month_start.strftime('%b %Y'),
                    'sessions': month_sessions.count(),
                    'questions': month_answers.count(),
                    'accuracy': round(accuracy, 2),
                    'attempted': attempted,
                    'correct': correct,
                })
            else:
                monthly_data.append({
                    'month': month_start.strftime('%b %Y'),
                    'sessions': 0,
                    'questions': 0,
                    'accuracy': 0,
                    'attempted': 0,
                    'correct': 0,
                })
        
        print(f"✅ SUCCESS: {len(monthly_data)} months", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({'success': True, 'monthly_progress': monthly_data})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_clinical_performance(request):
    """Get clinical MCQ performance - OPTIMIZED"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Clinical Performance", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=curated_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        # Get unique UIDs
        mcq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        print(f"📊 Fetching {len(mcq_uids)} MCQs...", flush=True)
        
        # Fetch all MCQs with types
        mcq_dict = {}
        mcqs = MCQ.objects.filter(uid__in=mcq_uids).select_related(
            'topic__chapter__unit__subject', 'types'
        ).only('uid', 'types__types', 'topic__chapter__unit__subject__name')
        
        for mcq in mcqs:
            mcq_dict[str(mcq.uid)] = mcq
        
        clinical_subjects = {}
        clinical_count = 0
        
        for answer in all_answers:
            mcq = mcq_dict.get(str(answer.mcq_uid))
            
            if not mcq or not mcq.types or mcq.types.types != 'Clinical':
                continue
            
            clinical_count += 1
            
            if not (mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit and mcq.topic.chapter.unit.subject):
                continue
            
            sn = mcq.topic.chapter.unit.subject.name
            
            if sn not in clinical_subjects:
                clinical_subjects[sn] = {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0}
            
            clinical_subjects[sn]['total'] += 1
            if answer.is_attempted:
                clinical_subjects[sn]['attempted'] += 1
                if answer.correct:
                    clinical_subjects[sn]['correct'] += 1
        
        # Calculate accuracy
        for sn, data in clinical_subjects.items():
            if data['attempted'] > 0:
                data['accuracy'] = round((data['correct'] / data['attempted'] * 100), 2)
        
        print(f"✅ SUCCESS: {clinical_count} clinical, {len(clinical_subjects)} subjects", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({'success': True, 'clinical_performance': clinical_subjects})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_weakness_detection(request):
    """AI weakness detection - OPTIMIZED"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Weakness Detection", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=curated_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        # Get unique UIDs and fetch all MCQs
        mcq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        print(f"📊 Fetching {len(mcq_uids)} MCQs...", flush=True)
        
        mcq_dict = {}
        mcqs = MCQ.objects.filter(uid__in=mcq_uids).select_related(
            'topic__chapter__unit__subject'
        ).only('uid', 'topic__name', 'topic__chapter__name', 'topic__chapter__unit__name', 'topic__chapter__unit__subject__name')
        
        for mcq in mcqs:
            mcq_dict[str(mcq.uid)] = mcq
        
        weakness_data = {
            'weak_subjects': [],
            'weak_units': [],
            'weak_chapters': [],
            'weak_topics': [],
            'recommendations': []
        }
        
        # Build metrics
        subject_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0})
        unit_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0, 'subject': ''})
        chapter_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0, 'unit': '', 'subject': ''})
        topic_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0, 'chapter': '', 'unit': '', 'subject': ''})
        
        for answer in all_answers:
            mcq = mcq_dict.get(str(answer.mcq_uid))
            
            if not mcq or not (mcq.topic and mcq.topic.chapter and mcq.topic.chapter.unit and mcq.topic.chapter.unit.subject):
                continue
            
            s = mcq.topic.chapter.unit.subject
            u = mcq.topic.chapter.unit
            c = mcq.topic.chapter
            t = mcq.topic
            
            subject_metrics[s.name]['total'] += 1
            unit_metrics[u.name]['total'] += 1
            unit_metrics[u.name]['subject'] = s.name
            chapter_metrics[c.name]['total'] += 1
            chapter_metrics[c.name]['unit'] = u.name
            chapter_metrics[c.name]['subject'] = s.name
            topic_metrics[t.name]['total'] += 1
            topic_metrics[t.name]['chapter'] = c.name
            topic_metrics[t.name]['unit'] = u.name
            topic_metrics[t.name]['subject'] = s.name
            
            if answer.is_attempted:
                subject_metrics[s.name]['attempted'] += 1
                unit_metrics[u.name]['attempted'] += 1
                chapter_metrics[c.name]['attempted'] += 1
                topic_metrics[t.name]['attempted'] += 1
                
                if answer.correct:
                    subject_metrics[s.name]['correct'] += 1
                    unit_metrics[u.name]['correct'] += 1
                    chapter_metrics[c.name]['correct'] += 1
                    topic_metrics[t.name]['correct'] += 1
        
        # Detect weak areas
        for sn, m in subject_metrics.items():
            if m['attempted'] >= 5:
                acc = (m['correct'] / m['attempted'] * 100)
                if acc < 60:
                    weakness_data['weak_subjects'].append({
                        'name': sn,
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium',
                    })
        
        for un, m in unit_metrics.items():
            if m['attempted'] >= 3:
                acc = (m['correct'] / m['attempted'] * 100)
                if acc < 60:
                    weakness_data['weak_units'].append({
                        'name': un,
                        'subject': m['subject'],
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium',
                    })
        
        for cn, m in chapter_metrics.items():
            if m['attempted'] >= 2:
                acc = (m['correct'] / m['attempted'] * 100)
                if acc < 60:
                    weakness_data['weak_chapters'].append({
                        'name': cn,
                        'unit': m['unit'],
                        'subject': m['subject'],
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium',
                    })
        
        for tn, m in topic_metrics.items():
            if m['attempted'] >= 1:
                acc = (m['correct'] / m['attempted'] * 100)
                if acc < 60:
                    weakness_data['weak_topics'].append({
                        'name': tn,
                        'chapter': m['chapter'],
                        'unit': m['unit'],
                        'subject': m['subject'],
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium',
                    })
        
        # Sort and recommendations
        weakness_data['weak_subjects'].sort(key=lambda x: x['accuracy'])
        weakness_data['weak_units'].sort(key=lambda x: x['accuracy'])
        weakness_data['weak_chapters'].sort(key=lambda x: x['accuracy'])
        weakness_data['weak_topics'].sort(key=lambda x: x['accuracy'])
        
        if weakness_data['weak_subjects']:
            w = weakness_data['weak_subjects'][0]
            weakness_data['recommendations'].append(f"Focus on {w['name']} - {w['accuracy']}% accuracy")
        
        if weakness_data['weak_topics']:
            for t in weakness_data['weak_topics'][:3]:
                weakness_data['recommendations'].append(f"Practice {t['name']} in {t['subject']}")
        
        print(f"✅ SUCCESS: {len(weakness_data['weak_subjects'])} weak subjects", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({'success': True, 'weakness_analysis': weakness_data})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_difficulty_performance(request):
    """Get difficulty performance - OPTIMIZED"""
    print(f"\n{'='*80}", flush=True)
    print(f"🚀 ANALYTICS - Difficulty Performance", flush=True)
    
    try:
        curated_sessions = _get_curated_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=curated_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        # Get unique UIDs
        mcq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        print(f"📊 Fetching {len(mcq_uids)} MCQs...", flush=True)
        
        # Fetch all with difficulty
        mcq_dict = {}
        mcqs = MCQ.objects.filter(uid__in=mcq_uids).select_related('difficulty').only('uid', 'difficulty__name')
        
        for mcq in mcqs:
            mcq_dict[str(mcq.uid)] = mcq
        
        difficulty_stats = {
            'Easy': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0},
            'Medium': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0},
            'Tough': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0},
        }
        
        for answer in all_answers:
            mcq = mcq_dict.get(str(answer.mcq_uid))
            
            if not mcq or not mcq.difficulty:
                continue
            
            dn = mcq.difficulty.name
            if dn in difficulty_stats:
                difficulty_stats[dn]['total'] += 1
                if answer.is_attempted:
                    difficulty_stats[dn]['attempted'] += 1
                    if answer.correct:
                        difficulty_stats[dn]['correct'] += 1
        
        # Calculate accuracy
        for dn, stats in difficulty_stats.items():
            if stats['attempted'] > 0:
                stats['accuracy'] = round((stats['correct'] / stats['attempted'] * 100), 2)
        
        print(f"✅ SUCCESS", flush=True)
        print(f"{'='*80}\n", flush=True)
        
        return Response({'success': True, 'difficulty_performance': difficulty_stats})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


from pyqs.models import PYQ

def get_pyq_sessions_cached(user):
    """Helper to get PYQ sessions with caching"""
    cache_key = f'pyq_sessions_{user.id}'
    
    # Try cache first
    cached = cache.get(cache_key)
    if cached:
        print(f"✓ Using CACHED PYQ sessions: {len(cached)} IDs", flush=True)
        return TestSession.objects.filter(id__in=cached)
    
    print(f"Getting PYQ sessions for user {user.username}", flush=True)
    base_sessions = TestSession.objects.filter(
        user=user,
        submitted=True,
        pyq=True  # Only PYQ sessions
    )
    
    count = base_sessions.count()
    print(f"Found {count} submitted PYQ sessions", flush=True)
    
    # Filter out Mock sessions
    filtered_ids = []
    for idx, session in enumerate(base_sessions):
        if idx % 100 == 0:
            print(f"Processing {idx}/{count}...", flush=True)
        
        is_mock = False
        if session.selections:
            try:
                selections = session.selections if isinstance(session.selections, list) else json.loads(session.selections)
                is_mock = any("MOCK TEST" in str(sel).upper() for sel in selections if sel)
            except:
                pass
        
        if not is_mock:
            filtered_ids.append(session.id)
    
    # Cache for 5 minutes
    cache.set(cache_key, filtered_ids, 300)
    result = TestSession.objects.filter(id__in=filtered_ids)
    print(f"✓ PYQ sessions: {result.count()} (cached 5min)", flush=True)
    
    return result


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_exam_progress(request):
    """Get PYQ exam-wise progress (NEET-PG, INI-CET, FMGE, UPSC-CMS)"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Exam Progress", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions)
        
        # Get unique attempted PYQ UIDs (count each PYQ only once)
        attempted_pyq_uids = set()
        for answer in all_answers.filter(is_attempted=True):
            attempted_pyq_uids.add(str(answer.mcq_uid))
        
        # Get all attempted PYQs with their exam categories
        attempted_pyqs = PYQ.objects.filter(uid__in=attempted_pyq_uids).only('uid', 'pyq_cat')
        
        exam_stats = {
            'NEET-PG': {'total_attempted': 0, 'total_in_db': 0, 'correct': 0, 'accuracy': 0},
            'INI-CET': {'total_attempted': 0, 'total_in_db': 0, 'correct': 0, 'accuracy': 0},
            'FMGE': {'total_attempted': 0, 'total_in_db': 0, 'correct': 0, 'accuracy': 0},
            'UPSC-CMS': {'total_attempted': 0, 'total_in_db': 0, 'correct': 0, 'accuracy': 0},
        }
        
        # Get total PYQs in database for each exam
        for exam_cat in exam_stats.keys():
            exam_stats[exam_cat]['total_in_db'] = PYQ.objects.filter(pyq_cat=exam_cat).count()
        
        # Count attempted PYQs by exam category
        exam_pyq_map = {}  # {exam_cat: set of unique UIDs}
        for pyq in attempted_pyqs:
            if pyq.pyq_cat and pyq.pyq_cat in exam_stats:
                if pyq.pyq_cat not in exam_pyq_map:
                    exam_pyq_map[pyq.pyq_cat] = set()
                exam_pyq_map[pyq.pyq_cat].add(str(pyq.uid))
        
        for exam_cat, uid_set in exam_pyq_map.items():
            exam_stats[exam_cat]['total_attempted'] = len(uid_set)
        
        # Calculate accuracy for each exam
        for answer in all_answers.filter(is_attempted=True):
            pyq = PYQ.objects.filter(uid=answer.mcq_uid).first()
            if pyq and pyq.pyq_cat and pyq.pyq_cat in exam_stats:
                if answer.correct:
                    exam_stats[pyq.pyq_cat]['correct'] += 1
        
        # Calculate accuracy percentages
        for exam_cat, stats in exam_stats.items():
            if stats['total_attempted'] > 0:
                stats['accuracy'] = round((stats['correct'] / stats['total_attempted']) * 100, 2)
            stats['progress_percentage'] = round((stats['total_attempted'] / stats['total_in_db']) * 100, 2) if stats['total_in_db'] > 0 else 0
        
        print(f"✓ SUCCESS: Exam stats calculated", flush=True)
        print("="*80, flush=True)
        
        return Response({
            'success': True,
            'exam_progress': exam_stats
        })
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_overall_stats(request):
    """Get overall PYQ performance statistics"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Overall Stats", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions)
        
        total_sessions = pyq_sessions.count()
        total_questions = all_answers.count()
        total_attempted = all_answers.filter(is_attempted=True).count()
        total_correct = all_answers.filter(correct=True, is_attempted=True).count()
        total_incorrect = all_answers.filter(correct=False, is_attempted=True).count()
        
        overall_accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
        total_score = float(pyq_sessions.aggregate(Sum('score'))['score__sum'] or 0)
        
        print(f"✓ SUCCESS: {total_sessions} sessions, {overall_accuracy:.2f}%", flush=True)
        print("="*80, flush=True)
        
        return Response({
            'success': True,
            'overall_stats': {
                'total_sessions': total_sessions,
                'total_questions_answered': total_questions,
                'total_attempted': total_attempted,
                'total_correct': total_correct,
                'total_incorrect': total_incorrect,
                'total_score': total_score,
                'overall_accuracy': round(overall_accuracy, 2)
            }
        })
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_subject_hierarchy(request):
    """Get PYQ subject hierarchy (Subject -> Unit -> Topic)"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Subject Hierarchy", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        total_answers = all_answers.count()
        print(f"Processing {total_answers} answers...", flush=True)
        
        # Get unique PYQ UIDs
        pyq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        print(f"Fetching {len(pyq_uids)} unique PYQs...", flush=True)
        
        # Fetch all PYQs with related unit and subject
        pyq_dict = {}
        pyqs = PYQ.objects.filter(uid__in=pyq_uids).select_related('unit__subject').only(
            'uid', 'topic', 'unit__uid', 'unit__name', 'unit__subject__uid', 'unit__subject__name'
        )
        
        for pyq in pyqs:
            pyq_dict[str(pyq.uid)] = pyq
        
        print(f"Fetched {len(pyq_dict)} PYQs", flush=True)
        
        hierarchy = {}
        processed = 0
        errors = 0
        
        for idx, answer in enumerate(all_answers):
            if idx % 1000 == 0:
                print(f"{idx}/{total_answers} ({idx/total_answers*100:.1f}%)", flush=True)
            
            pyq = pyq_dict.get(str(answer.mcq_uid))
            if not pyq or not (pyq.unit and pyq.unit.subject):
                errors += 1
                continue
            
            s = pyq.unit.subject
            u = pyq.unit
            t = pyq.topic  # Topic is just a string field in PYQ
            
            # Initialize subject
            if s.name not in hierarchy:
                hierarchy[s.name] = {
                    'subject_id': str(s.uid),
                    'total': 0,
                    'correct': 0,
                    'attempted': 0,
                    'accuracy': 0,
                    'units': {}
                }
            
            hierarchy[s.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['attempted'] += 1
            if answer.correct:
                hierarchy[s.name]['correct'] += 1
            
            # Initialize unit
            if u.name not in hierarchy[s.name]['units']:
                hierarchy[s.name]['units'][u.name] = {
                    'unit_id': str(u.uid),
                    'total': 0,
                    'correct': 0,
                    'attempted': 0,
                    'accuracy': 0,
                    'topics': {}
                }
            
            hierarchy[s.name]['units'][u.name]['total'] += 1
            if answer.is_attempted:
                hierarchy[s.name]['units'][u.name]['attempted'] += 1
            if answer.correct:
                hierarchy[s.name]['units'][u.name]['correct'] += 1
            
            # Initialize topic only if PYQ has a topic name
            if t:
                if t not in hierarchy[s.name]['units'][u.name]['topics']:
                    hierarchy[s.name]['units'][u.name]['topics'][t] = {
                        'topic_name': t,
                        'total': 0,
                        'correct': 0,
                        'attempted': 0,
                        'accuracy': 0
                    }
                
                hierarchy[s.name]['units'][u.name]['topics'][t]['total'] += 1
                if answer.is_attempted:
                    hierarchy[s.name]['units'][u.name]['topics'][t]['attempted'] += 1
                if answer.correct:
                    hierarchy[s.name]['units'][u.name]['topics'][t]['correct'] += 1
            
            processed += 1
        
        # Calculate accuracies
        for sn, sd in hierarchy.items():
            if sd['attempted'] > 0:
                sd['accuracy'] = round(sd['correct'] / sd['attempted'] * 100, 2)
            
            for un, ud in sd['units'].items():
                if ud['attempted'] > 0:
                    ud['accuracy'] = round(ud['correct'] / ud['attempted'] * 100, 2)
                
                for tn, td in ud['topics'].items():
                    if td['attempted'] > 0:
                        td['accuracy'] = round(td['correct'] / td['attempted'] * 100, 2)
        
        print(f"✓ COMPLETE: {len(hierarchy)} subjects", flush=True)
        print("="*80, flush=True)
        
        return Response({'success': True, 'subject_hierarchy': hierarchy})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_monthly_progress(request):
    """Get PYQ monthly progress"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Monthly Progress", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        monthly_data = []
        
        now = timezone.now()
        for i in range(5, -1, -1):
            month_start = now - timedelta(days=30 * (i + 1))
            month_end = now - timedelta(days=30 * i)
            
            month_sessions = pyq_sessions.filter(created_at__gte=month_start, created_at__lt=month_end)
            
            if month_sessions.exists():
                month_answers = TestAnswer.objects.filter(test_session__in=month_sessions)
                
                attempted = month_answers.filter(is_attempted=True).count()
                correct = month_answers.filter(correct=True, is_attempted=True).count()
                accuracy = (correct / attempted * 100) if attempted > 0 else 0
                
                monthly_data.append({
                    'month': month_start.strftime("%b %Y"),
                    'sessions': month_sessions.count(),
                    'questions': month_answers.count(),
                    'accuracy': round(accuracy, 2),
                    'attempted': attempted,
                    'correct': correct
                })
            else:
                monthly_data.append({
                    'month': month_start.strftime("%b %Y"),
                    'sessions': 0,
                    'questions': 0,
                    'accuracy': 0,
                    'attempted': 0,
                    'correct': 0
                })
        
        print(f"✓ SUCCESS: {len(monthly_data)} months", flush=True)
        print("="*80, flush=True)
        
        return Response({'success': True, 'monthly_progress': monthly_data})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_clinical_performance(request):
    """Get PYQ clinical performance"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Clinical Performance", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        pyq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        
        # Fetch PYQs with their types
        pyq_dict = {}
        pyqs = PYQ.objects.filter(uid__in=pyq_uids).select_related('types', 'unit__subject').only(
            'uid', 'types__types', 'unit__subject__name'
        )
        
        for pyq in pyqs:
            pyq_dict[str(pyq.uid)] = pyq
        
        clinical_subjects = {}
        clinical_count = 0
        
        for answer in all_answers:
            pyq = pyq_dict.get(str(answer.mcq_uid))
            if not pyq or not pyq.types or pyq.types.types != 'Clinical':
                continue
            
            clinical_count += 1
            
            if not (pyq.unit and pyq.unit.subject):
                continue
            
            sn = pyq.unit.subject.name
            
            if sn not in clinical_subjects:
                clinical_subjects[sn] = {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0}
            
            clinical_subjects[sn]['total'] += 1
            if answer.is_attempted:
                clinical_subjects[sn]['attempted'] += 1
            if answer.correct:
                clinical_subjects[sn]['correct'] += 1
        
        # Calculate accuracies
        for sn, data in clinical_subjects.items():
            if data['attempted'] > 0:
                data['accuracy'] = round(data['correct'] / data['attempted'] * 100, 2)
        
        print(f"✓ SUCCESS: {clinical_count} clinical, {len(clinical_subjects)} subjects", flush=True)
        print("="*80, flush=True)
        
        return Response({'success': True, 'clinical_performance': clinical_subjects})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_weakness_detection(request):
    """PYQ AI weakness detection"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Weakness Detection", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        pyq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        
        pyq_dict = {}
        pyqs = PYQ.objects.filter(uid__in=pyq_uids).select_related('unit__subject').only(
            'uid', 'topic', 'unit__name', 'unit__subject__name'
        )
        
        for pyq in pyqs:
            pyq_dict[str(pyq.uid)] = pyq
        
        weakness_data = {
            'weak_subjects': [],
            'weak_units': [],
            'weak_topics': [],
            'recommendations': []
        }
        
        # Build metrics
        subject_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0})
        unit_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0, 'subject': ''})
        topic_metrics = defaultdict(lambda: {'correct': 0, 'total': 0, 'attempted': 0, 'unit': '', 'subject': ''})
        
        for answer in all_answers:
            pyq = pyq_dict.get(str(answer.mcq_uid))
            if not pyq or not (pyq.unit and pyq.unit.subject):
                continue
            
            s = pyq.unit.subject
            u = pyq.unit
            t = pyq.topic
            
            subject_metrics[s.name]['total'] += 1
            unit_metrics[u.name]['total'] += 1
            unit_metrics[u.name]['subject'] = s.name
            
            if t:
                topic_metrics[t]['total'] += 1
                topic_metrics[t]['unit'] = u.name
                topic_metrics[t]['subject'] = s.name
            
            if answer.is_attempted:
                subject_metrics[s.name]['attempted'] += 1
                unit_metrics[u.name]['attempted'] += 1
                if t:
                    topic_metrics[t]['attempted'] += 1
                
                if answer.correct:
                    subject_metrics[s.name]['correct'] += 1
                    unit_metrics[u.name]['correct'] += 1
                    if t:
                        topic_metrics[t]['correct'] += 1
        
        # Detect weak areas
        for sn, m in subject_metrics.items():
            if m['attempted'] >= 5:
                acc = (m['correct'] / m['attempted']) * 100
                if acc < 60:
                    weakness_data['weak_subjects'].append({
                        'name': sn,
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium'
                    })
        
        for un, m in unit_metrics.items():
            if m['attempted'] >= 3:
                acc = (m['correct'] / m['attempted']) * 100
                if acc < 60:
                    weakness_data['weak_units'].append({
                        'name': un,
                        'subject': m['subject'],
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium'
                    })
        
        for tn, m in topic_metrics.items():
            if m['attempted'] >= 1:
                acc = (m['correct'] / m['attempted']) * 100
                if acc < 60:
                    weakness_data['weak_topics'].append({
                        'name': tn,
                        'unit': m['unit'],
                        'subject': m['subject'],
                        'accuracy': round(acc, 2),
                        'attempted': m['attempted'],
                        'correct': m['correct'],
                        'severity': 'high' if acc < 40 else 'medium'
                    })
        
        # Sort by accuracy
        weakness_data['weak_subjects'].sort(key=lambda x: x['accuracy'])
        weakness_data['weak_units'].sort(key=lambda x: x['accuracy'])
        weakness_data['weak_topics'].sort(key=lambda x: x['accuracy'])
        
        # Generate recommendations
        if weakness_data['weak_subjects']:
            w = weakness_data['weak_subjects'][0]
            weakness_data['recommendations'].append(f"Focus on {w['name']} - {w['accuracy']}% accuracy")
        
        if weakness_data['weak_topics']:
            for t in weakness_data['weak_topics'][:3]:
                weakness_data['recommendations'].append(f"Practice {t['name']} in {t['subject']}")
        
        print(f"✓ SUCCESS: {len(weakness_data['weak_subjects'])} weak subjects", flush=True)
        print("="*80, flush=True)
        
        return Response({'success': True, 'weakness_analysis': weakness_data})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def analytics_pyq_difficulty_performance(request):
    """Get PYQ difficulty performance"""
    print("="*80, flush=True)
    print("ANALYTICS - PYQ Difficulty Performance", flush=True)
    
    try:
        pyq_sessions = get_pyq_sessions_cached(request.user)
        all_answers = TestAnswer.objects.filter(test_session__in=pyq_sessions).only('mcq_uid', 'is_attempted', 'correct')
        
        pyq_uids = set(all_answers.values_list('mcq_uid', flat=True))
        
        pyq_dict = {}
        pyqs = PYQ.objects.filter(uid__in=pyq_uids).select_related('difficulty').only('uid', 'difficulty__name')
        
        for pyq in pyqs:
            pyq_dict[str(pyq.uid)] = pyq
        
        difficulty_stats = {
            'Easy': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0},
            'Medium': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0},
            'Tough': {'total': 0, 'correct': 0, 'attempted': 0, 'accuracy': 0}
        }
        
        for answer in all_answers:
            pyq = pyq_dict.get(str(answer.mcq_uid))
            if not pyq or not pyq.difficulty:
                continue
            
            dn = pyq.difficulty.name
            if dn in difficulty_stats:
                difficulty_stats[dn]['total'] += 1
                if answer.is_attempted:
                    difficulty_stats[dn]['attempted'] += 1
                if answer.correct:
                    difficulty_stats[dn]['correct'] += 1
        
        # Calculate accuracies
        for dn, stats in difficulty_stats.items():
            if stats['attempted'] > 0:
                stats['accuracy'] = round(stats['correct'] / stats['attempted'] * 100, 2)
        
        print("✓ SUCCESS", flush=True)
        print("="*80, flush=True)
        
        return Response({'success': True, 'difficulty_performance': difficulty_stats})
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return Response({'success': False, 'error': str(e)}, status=500)

