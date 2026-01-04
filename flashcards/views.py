from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q, Avg, F, Case, When, IntegerField
from datetime import datetime, timedelta
import json
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from .authentication import CsrfExemptSessionAuthentication  # Your custom auth class
from .models import (
    Subject, Unit, Topic, Flashcard, UserFlashcardProgress,
    UserStreak, Badge, UserBadge, StudySession
)


# ======================== HOME SCREEN ========================
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def flashcard_home(request):
    """
    Flashcard Home Screen API
    Returns: due_today, new_today, done_today, daily_goal, weak_topics, subjects
    """
    user = request.user
    today = timezone.now().date()
    
    # Get or create user streak
    streak, _ = UserStreak.objects.get_or_create(user=user)
    
    # Calculate due today (cards with next_review <= now)
    due_today_count = UserFlashcardProgress.objects.filter(
        user=user,
        next_review__lte=timezone.now(),
        flashcard__is_active=True
    ).count()
    
    # Calculate new cards today (cards never seen by user)
    all_active_cards = Flashcard.objects.filter(is_active=True).count()
    user_progress_count = UserFlashcardProgress.objects.filter(user=user).count()
    new_cards_available = max(0, all_active_cards - user_progress_count)
    
    # Calculate done today (cards reviewed today)
    done_today_count = UserFlashcardProgress.objects.filter(
        user=user,
        last_reviewed__date=today
    ).count()
    
    # Get weak topics (accuracy < 60%)
    weak_topics = []
    topic_progress = UserFlashcardProgress.objects.filter(
        user=user,
        total_reviews__gt=0
    ).values('flashcard__topic').annotate(
        total=Count('id'),
        correct=Count(Case(
            When(last_rating__gte=3, then=1),
            output_field=IntegerField()
        )),
        accuracy=Avg(Case(
            When(last_rating__gte=3, then=100.0),
            default=0.0,
            output_field=IntegerField()
        ))
    ).filter(accuracy__lt=60).order_by('accuracy')[:5]
    
    for item in topic_progress:
        try:
            topic = Topic.objects.get(id=item['flashcard__topic'])
            weak_topics.append({
                'id': str(topic.id),
                'name': topic.name,
                'accuracy': round(item['accuracy'], 1)
            })
        except Topic.DoesNotExist:
            pass
    
    # Get subjects with stats
    subjects_data = []
    subjects = Subject.objects.filter(is_active=True).prefetch_related('units__topics__flashcards')
    
    for subject in subjects:
        # Get all flashcard IDs for this subject
        flashcard_ids = Flashcard.objects.filter(
            topic__unit__subject=subject,
            is_active=True
        ).values_list('id', flat=True)
        
        # Count due cards for this subject
        due_count = UserFlashcardProgress.objects.filter(
            user=user,
            flashcard_id__in=flashcard_ids,
            next_review__lte=timezone.now()
        ).count()
        
        # Count mastered cards
        mastered_count = UserFlashcardProgress.objects.filter(
            user=user,
            flashcard_id__in=flashcard_ids,
            status='mastered'
        ).count()
        
        total_cards = len(flashcard_ids)
        mastered_percent = round((mastered_count / total_cards * 100) if total_cards > 0 else 0, 1)
        
        subjects_data.append({
            'id': str(subject.id),
            'name': subject.name,
            'icon': subject.icon,
            'color': subject.color,
            'due_count': due_count,
            'mastered_percent': mastered_percent,
            'total_cards': total_cards
        })
    
    response_data = {
        'success': True,
        'data': {
            'due_today': due_today_count,
            'new_today': min(new_cards_available, streak.daily_goal),
            'done_today': done_today_count,
            'daily_goal': streak.daily_goal,
            'weak_topics': weak_topics,
            'subjects': subjects_data,
            'current_streak': streak.current_streak,
            'total_xp': streak.total_xp
        }
    }
    
    return JsonResponse(response_data)


# ======================== BROWSE SCREEN ========================
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def flashcard_browse(request):
    """
    Flashcard Browse Screen API
    Returns: subjects -> units -> topics hierarchy
    """
    user = request.user
    
    subjects_data = []
    subjects = Subject.objects.filter(is_active=True).prefetch_related(
        'units__topics__flashcards'
    ).order_by('display_order', 'name')
    
    for subject in subjects:
        units_data = []
        
        for unit in subject.units.filter(is_active=True).order_by('display_order', 'name'):
            topics_data = []
            
            for topic in unit.topics.filter(is_active=True).order_by('display_order', 'name'):
                # Count total cards
                total_cards = Flashcard.objects.filter(
                    topic=topic,
                    is_active=True
                ).count()
                
                # Count due cards
                flashcard_ids = Flashcard.objects.filter(
                    topic=topic,
                    is_active=True
                ).values_list('id', flat=True)
                
                due_count = UserFlashcardProgress.objects.filter(
                    user=user,
                    flashcard_id__in=flashcard_ids,
                    next_review__lte=timezone.now()
                ).count()
                
                # Calculate accuracy
                progress_stats = UserFlashcardProgress.objects.filter(
                    user=user,
                    flashcard_id__in=flashcard_ids,
                    total_reviews__gt=0
                ).aggregate(
                    total_reviews=Count('id'),
                    correct_reviews=Count(Case(
                        When(last_rating__gte=3, then=1),
                        output_field=IntegerField()
                    ))
                )
                
                accuracy_percent = 0
                if progress_stats['total_reviews'] and progress_stats['total_reviews'] > 0:
                    accuracy_percent = round(
                        (progress_stats['correct_reviews'] / progress_stats['total_reviews'] * 100),
                        1
                    )
                
                topics_data.append({
                    'id': str(topic.id),
                    'name': topic.name,
                    'total_cards': total_cards,
                    'due_count': due_count,
                    'accuracy_percent': accuracy_percent
                })
            
            units_data.append({
                'id': str(unit.id),
                'name': unit.name,
                'topics': topics_data
            })
        
        subjects_data.append({
            'id': str(subject.id),
            'name': subject.name,
            'icon': subject.icon,
            'color': subject.color,
            'units': units_data
        })
    
    return JsonResponse({
        'success': True,
        'data': {
            'subjects': subjects_data
        }
    })


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def topic_flashcards(request, topic_id):
    """
    Get flashcards for a specific topic with filters
    Query params: difficulty, card_type, bookmarked, status, page, page_size
    """
    user = request.user
    
    try:
        topic = Topic.objects.get(id=topic_id, is_active=True)
    except Topic.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Topic not found'
        }, status=404)
    
    # Get filters
    difficulty = request.GET.get('difficulty', None)
    card_type = request.GET.get('card_type', None)
    bookmarked = request.GET.get('bookmarked', None)
    status_filter = request.GET.get('status', None)
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    # Base query
    flashcards = Flashcard.objects.filter(
        topic=topic,
        is_active=True
    )
    
    # Apply filters
    if difficulty:
        flashcards = flashcards.filter(difficulty=difficulty)
    
    if card_type:
        flashcards = flashcards.filter(card_type=card_type)
    
    # Get user progress for filtering
    if bookmarked == 'true':
        bookmarked_card_ids = UserFlashcardProgress.objects.filter(
            user=user,
            is_bookmarked=True
        ).values_list('flashcard_id', flat=True)
        flashcards = flashcards.filter(id__in=bookmarked_card_ids)
    
    if status_filter:
        status_card_ids = UserFlashcardProgress.objects.filter(
            user=user,
            status=status_filter
        ).values_list('flashcard_id', flat=True)
        flashcards = flashcards.filter(id__in=status_card_ids)
    
    # Pagination
    total_count = flashcards.count()
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    flashcards = flashcards[start_idx:end_idx]
    
    # Serialize flashcards
    flashcards_data = []
    for card in flashcards:
        # Get user progress
        try:
            progress = UserFlashcardProgress.objects.get(user=user, flashcard=card)
            progress_data = {
                'status': progress.status,
                'is_bookmarked': progress.is_bookmarked,
                'repetitions': progress.repetitions,
                'next_review': progress.next_review.isoformat(),
                'accuracy': progress.accuracy
            }
        except UserFlashcardProgress.DoesNotExist:
            progress_data = {
                'status': 'new',
                'is_bookmarked': False,
                'repetitions': 0,
                'next_review': None,
                'accuracy': 0
            }
        
        flashcards_data.append({
            'id': str(card.id),
            'front_text': card.front_text[:100] + '...' if len(card.front_text) > 100 else card.front_text,
            'card_type': card.card_type,
            'difficulty': card.difficulty,
            'user_progress': progress_data
        })
    
    return JsonResponse({
        'success': True,
        'data': {
            'topic': {
                'id': str(topic.id),
                'name': topic.name
            },
            'flashcards': flashcards_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        }
    })


# ======================== STUDY SCREEN ========================
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def start_study_session(request):
    """
    Start a new study session with filter support
    Body: { 
        mode: 'today'|'topic'|'weak'|'mixed'|'custom', 
        topic_id?: string, 
        card_ids?: [],
        filters?: { difficulty, card_type, bookmarked, status }
    }
    """
    user = request.user
    profile = user.profile

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    
    mode = data.get('mode', 'today')
    topic_id = data.get('topic_id', None)
    custom_card_ids = data.get('card_ids', [])
    filters = data.get('filters', {})
    
    # Debug logging
    print(f"\n{'='*60}")
    print(f"🎴 Starting Study Session")
    print(f"{'='*60}")
    print(f"👤 User: {user.username}")
    print(f"📌 Mode: {mode}")
    print(f"📍 Topic ID: {topic_id}")
    print(f"🔍 Filters: {filters}")
    print(f"{'='*60}\n")
    
    has_subscription = UserSubscriptionManager.get_subscription_summary(user)
    if not has_subscription:
        profile.consume_flashcard_session()
        print(f"? Free session consumed. Remaining: {profile.flashcard_sessions_remaining}")
    # Create study session
    session = StudySession.objects.create(
        user=user,
        mode=mode,
        topic_id=topic_id if topic_id else None
    )
    
    # Get flashcards based on mode
    flashcards = []
    
    if mode == 'today':
        print("📅 MODE: Today's Session")
        # Get due cards first
        due_cards = UserFlashcardProgress.objects.filter(
            user=user,
            next_review__lte=timezone.now(),
            flashcard__is_active=True
        ).select_related('flashcard')
        
        print(f"📊 Initial due cards: {due_cards.count()}")
        
        # Apply filters to flashcards
        if filters.get('difficulty'):
            due_cards = due_cards.filter(flashcard__difficulty=filters['difficulty'])
            print(f"✅ After difficulty filter ({filters['difficulty']}): {due_cards.count()}")
        
        if filters.get('card_type'):
            due_cards = due_cards.filter(flashcard__card_type=filters['card_type'])
            print(f"✅ After card_type filter ({filters['card_type']}): {due_cards.count()}")
        
        if filters.get('status'):
            due_cards = due_cards.filter(status=filters['status'])
            print(f"✅ After status filter ({filters['status']}): {due_cards.count()}")
        
        if filters.get('bookmarked'):
            due_cards = due_cards.filter(is_bookmarked=True)
            print(f"✅ After bookmarked filter: {due_cards.count()}")
        
        due_cards = due_cards[:20]
        flashcards = [p.flashcard for p in due_cards]
        
        # Add new cards if needed
        streak, _ = UserStreak.objects.get_or_create(user=user)
        if len(flashcards) < streak.daily_goal:
            existing_card_ids = UserFlashcardProgress.objects.filter(
                user=user
            ).values_list('flashcard_id', flat=True)
            
            new_cards_query = Flashcard.objects.filter(
                is_active=True
            ).exclude(id__in=existing_card_ids)
            
            print(f"📊 New cards available: {new_cards_query.count()}")
            
            # Apply filters to new cards
            if filters.get('difficulty'):
                new_cards_query = new_cards_query.filter(difficulty=filters['difficulty'])
                print(f"✅ New cards after difficulty filter: {new_cards_query.count()}")
            
            if filters.get('card_type'):
                new_cards_query = new_cards_query.filter(card_type=filters['card_type'])
                print(f"✅ New cards after card_type filter: {new_cards_query.count()}")
            
            new_cards = new_cards_query[:streak.daily_goal - len(flashcards)]
            flashcards.extend(list(new_cards))
        
        print(f"🎴 Final flashcards for today: {len(flashcards)}")
    
    elif mode == 'topic' and topic_id:
        print(f"📚 MODE: Topic Focus (Topic ID: {topic_id})")
        
        # Get all cards from topic
        flashcards_query = Flashcard.objects.filter(
            topic_id=topic_id,
            is_active=True
        )
        
        print(f"📊 Initial cards in topic: {flashcards_query.count()}")
        
        # Apply difficulty filter
        if filters.get('difficulty'):
            flashcards_query = flashcards_query.filter(difficulty=filters['difficulty'])
            print(f"✅ After difficulty filter ({filters['difficulty']}): {flashcards_query.count()}")
        
        # Apply card_type filter
        if filters.get('card_type'):
            flashcards_query = flashcards_query.filter(card_type=filters['card_type'])
            print(f"✅ After card_type filter ({filters['card_type']}): {flashcards_query.count()}")
        
        # If bookmarked or status filter, need to join with progress
        if filters.get('bookmarked') or filters.get('status'):
            progress_filters = {'user': user}
            
            if filters.get('bookmarked'):
                progress_filters['is_bookmarked'] = True
                print(f"✅ Applying bookmarked filter")
            
            if filters.get('status'):
                progress_filters['status'] = filters['status']
                print(f"✅ Applying status filter ({filters['status']})")
            
            filtered_card_ids = UserFlashcardProgress.objects.filter(
                **progress_filters
            ).values_list('flashcard_id', flat=True)
            
            print(f"📊 Cards matching progress filters: {len(filtered_card_ids)}")
            
            flashcards_query = flashcards_query.filter(id__in=filtered_card_ids)
            print(f"✅ After progress filters: {flashcards_query.count()}")
        
        flashcards = list(flashcards_query[:50])
        print(f"🎴 Final flashcards for topic: {len(flashcards)}")
    
    elif mode == 'weak':
        print("⚠️ MODE: Weak Topics")
        
        # Get cards from weak topics
        weak_progress = UserFlashcardProgress.objects.filter(
            user=user,
            total_reviews__gt=0
        ).annotate(
            accuracy_calc=ExpressionWrapper(
                Case(
                    When(total_reviews__gt=0, then=F('correct_reviews') * 100.0 / F('total_reviews')),
                    default=0.0,
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        ).filter(accuracy_calc__lt=60)
        
        print(f"📊 Initial weak cards: {weak_progress.count()}")
        
        # Apply filters
        if filters.get('difficulty'):
            weak_progress = weak_progress.filter(flashcard__difficulty=filters['difficulty'])
            print(f"✅ After difficulty filter: {weak_progress.count()}")
        
        if filters.get('card_type'):
            weak_progress = weak_progress.filter(flashcard__card_type=filters['card_type'])
            print(f"✅ After card_type filter: {weak_progress.count()}")
        
        if filters.get('status'):
            weak_progress = weak_progress.filter(status=filters['status'])
            print(f"✅ After status filter: {weak_progress.count()}")
        
        if filters.get('bookmarked'):
            weak_progress = weak_progress.filter(is_bookmarked=True)
            print(f"✅ After bookmarked filter: {weak_progress.count()}")
        
        weak_progress = weak_progress.order_by('accuracy_calc')[:30]
        flashcards = [p.flashcard for p in weak_progress]
        print(f"🎴 Final weak flashcards: {len(flashcards)}")
    
    elif mode == 'custom' and custom_card_ids:
        print(f"🎯 MODE: Custom ({len(custom_card_ids)} cards)")
        flashcards = list(Flashcard.objects.filter(
            id__in=custom_card_ids,
            is_active=True
        ))
        print(f"🎴 Custom flashcards loaded: {len(flashcards)}")
    
    else:
        print("🔀 MODE: Mixed Review")
        # Mixed mode
        due_cards = UserFlashcardProgress.objects.filter(
            user=user,
            next_review__lte=timezone.now(),
            flashcard__is_active=True
        ).select_related('flashcard')
        
        print(f"📊 Initial due cards: {due_cards.count()}")
        
        # Apply filters
        if filters.get('difficulty'):
            due_cards = due_cards.filter(flashcard__difficulty=filters['difficulty'])
            print(f"✅ After difficulty filter: {due_cards.count()}")
        
        if filters.get('card_type'):
            due_cards = due_cards.filter(flashcard__card_type=filters['card_type'])
            print(f"✅ After card_type filter: {due_cards.count()}")
        
        if filters.get('status'):
            due_cards = due_cards.filter(status=filters['status'])
            print(f"✅ After status filter: {due_cards.count()}")
        
        if filters.get('bookmarked'):
            due_cards = due_cards.filter(is_bookmarked=True)
            print(f"✅ After bookmarked filter: {due_cards.count()}")
        
        due_cards = due_cards[:15]
        flashcards = [p.flashcard for p in due_cards]
        print(f"🎴 Final mixed flashcards: {len(flashcards)}")
    
    # Serialize flashcards with full data
    cards_data = []
    for card in flashcards:
        # Get or create user progress
        progress, created = UserFlashcardProgress.objects.get_or_create(
            user=user,
            flashcard=card,
            defaults={'next_review': timezone.now()}
        )
        
        cards_data.append({
            'id': str(card.id),
            'front_text': card.front_text,
            'back_text': card.back_text,
            'front_image_url': request.build_absolute_uri(card.front_image.url) if card.front_image else None,
            'back_image_url': request.build_absolute_uri(card.back_image.url) if card.back_image else None,
            'mnemonic': card.mnemonic,
            'key_points': card.key_points,
            'card_type': card.card_type,
            'difficulty': card.difficulty,
            'user_progress': {
                'next_review': progress.next_review.isoformat(),
                'repetitions': progress.repetitions,
                'ease_factor': progress.ease_factor,
                'is_bookmarked': progress.is_bookmarked,
                'status': progress.status,
                'accuracy': progress.accuracy
            }
        })
    
    print(f"\n✅ Session created with {len(cards_data)} cards")
    print(f"{'='*60}\n")
    
    return JsonResponse({
        'success': True,
        'data': {
            'session_id': str(session.id),
            'mode': mode,
            'total_cards': len(cards_data),
            'cards': cards_data,
            'filters_applied': filters
        }
    })

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def rate_flashcard(request, card_id):
    """
    Rate a flashcard (0-5) and update SM-2 algorithm
    Body: { quality: 0-5, session_id: string }
    """
    user = request.user
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    
    quality = data.get('quality', None)
    session_id = data.get('session_id', None)
    
    if quality is None or quality not in range(6):
        return JsonResponse({
            'success': False,
            'error': 'Quality must be 0-5'
        }, status=400)
    
    try:
        card = Flashcard.objects.get(id=card_id, is_active=True)
    except Flashcard.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Flashcard not found'
        }, status=404)
    
    # Get or create progress
    progress, created = UserFlashcardProgress.objects.get_or_create(
        user=user,
        flashcard=card,
        defaults={'next_review': timezone.now()}
    )
    
    # Update SM-2
    progress.update_sm2(quality)
    
    # Update study session
    if session_id:
        try:
            session = StudySession.objects.get(id=session_id, user=user)
            session.cards_reviewed += 1
            if quality >= 3:
                session.cards_correct += 1
                session.xp_earned += 10
            else:
                session.xp_earned += 5
            session.save()
        except StudySession.DoesNotExist:
            pass
    
    # Update user streak
    streak, _ = UserStreak.objects.get_or_create(user=user)
    streak.update_streak()
    streak.total_cards_studied += 1
    streak.total_xp += 10 if quality >= 3 else 5
    streak.save()
    
    return JsonResponse({
        'success': True,
        'data': {
            'next_review': progress.next_review.isoformat(),
            'interval_days': progress.interval,
            'status': progress.status,
            'repetitions': progress.repetitions,
            'accuracy': progress.accuracy
        }
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def toggle_bookmark(request, card_id):
    """
    Toggle bookmark status for a flashcard
    """
    user = request.user
    
    try:
        card = Flashcard.objects.get(id=card_id, is_active=True)
    except Flashcard.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Flashcard not found'
        }, status=404)
    
    # Get or create progress
    progress, created = UserFlashcardProgress.objects.get_or_create(
        user=user,
        flashcard=card,
        defaults={'next_review': timezone.now()}
    )
    
    progress.is_bookmarked = not progress.is_bookmarked
    progress.save()
    
    return JsonResponse({
        'success': True,
        'data': {
            'is_bookmarked': progress.is_bookmarked
        }
    })


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_note(request, card_id):
    """
    Add or update user note for a flashcard
    Body: { note: string }
    """
    user = request.user
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    
    note = data.get('note', '')
    
    try:
        card = Flashcard.objects.get(id=card_id, is_active=True)
    except Flashcard.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Flashcard not found'
        }, status=404)
    
    # Get or create progress
    progress, created = UserFlashcardProgress.objects.get_or_create(
        user=user,
        flashcard=card,
        defaults={'next_review': timezone.now()}
    )
    
    progress.user_note = note
    progress.save()
    
    return JsonResponse({
        'success': True,
        'data': {
            'note': progress.user_note
        }
    })

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def end_study_session(request, session_id):
    """
    End a study session
    """
    user = request.user
    
    try:
        session = StudySession.objects.get(id=session_id, user=user)
    except StudySession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Session not found'
        }, status=404)
    
    session.ended_at = timezone.now()
    session.duration_seconds = int((session.ended_at - session.started_at).total_seconds())
    session.save()
    
    accuracy = 0
    if session.cards_reviewed > 0:
        accuracy = round((session.cards_correct / session.cards_reviewed * 100), 1)
    
    return JsonResponse({
        'success': True,
        'data': {
            'cards_reviewed': session.cards_reviewed,
            'cards_correct': session.cards_correct,
            'accuracy': accuracy,
            'duration_seconds': session.duration_seconds,
            'xp_earned': session.xp_earned
        }
    })


# ======================== ANALYTICS SCREEN ========================
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def flashcard_analytics(request):
    """
    Flashcard Analytics Screen API
    Returns: mastery_percent, avg_accuracy, cards_reviewed_last_7_days, 
             current_streak, subject_stats, weak_topics, recent_sessions
    """
    user = request.user
    
    # Get user streak
    streak, _ = UserStreak.objects.get_or_create(user=user)
    
    # Calculate mastery percentage
    total_progress = UserFlashcardProgress.objects.filter(user=user).count()
    mastered_count = UserFlashcardProgress.objects.filter(
        user=user,
        status='mastered'
    ).count()
    mastery_percent = round((mastered_count / total_progress * 100) if total_progress > 0 else 0, 1)
    
    # Calculate average accuracy
    progress_with_reviews = UserFlashcardProgress.objects.filter(
        user=user,
        total_reviews__gt=0
    )
    
    total_reviews_sum = sum([p.total_reviews for p in progress_with_reviews])
    correct_reviews_sum = sum([p.correct_reviews for p in progress_with_reviews])
    avg_accuracy = round((correct_reviews_sum / total_reviews_sum * 100) if total_reviews_sum > 0 else 0, 1)
    
    # Cards reviewed last 7 days
    seven_days_ago = timezone.now() - timedelta(days=7)
    cards_last_7_days = UserFlashcardProgress.objects.filter(
        user=user,
        last_reviewed__gte=seven_days_ago
    ).count()
    
    # Subject stats
    subjects = Subject.objects.filter(is_active=True)
    subject_stats = []
    
    for subject in subjects:
        flashcard_ids = Flashcard.objects.filter(
            topic__unit__subject=subject,
            is_active=True
        ).values_list('id', flat=True)
        
        subject_progress = UserFlashcardProgress.objects.filter(
            user=user,
            flashcard_id__in=flashcard_ids
        )
        
        total = subject_progress.count()
        mastered = subject_progress.filter(status='mastered').count()
        
        reviews = subject_progress.filter(total_reviews__gt=0)
        total_rev = sum([p.total_reviews for p in reviews])
        correct_rev = sum([p.correct_reviews for p in reviews])
        
        accuracy = round((correct_rev / total_rev * 100) if total_rev > 0 else 0, 1)
        
        subject_stats.append({
            'id': str(subject.id),
            'name': subject.name,
            'color': subject.color,
            'total_cards': len(flashcard_ids),
            'studied_cards': total,
            'mastered_count': mastered,
            'accuracy': accuracy
        })
    
    # Weak topics
    weak_topics = []
    topic_progress = UserFlashcardProgress.objects.filter(
        user=user,
        total_reviews__gt=2
    ).values('flashcard__topic').annotate(
        total=Count('id'),
        total_rev=Count('total_reviews'),
        correct=Count(Case(
            When(last_rating__gte=3, then=1),
            output_field=IntegerField()
        ))
    )
    
    for item in topic_progress:
        try:
            topic = Topic.objects.get(id=item['flashcard__topic'])
            accuracy = round((item['correct'] / item['total'] * 100) if item['total'] > 0 else 0, 1)
            
            if accuracy < 60:
                weak_topics.append({
                    'id': str(topic.id),
                    'name': topic.name,
                    'subject': topic.unit.subject.name,
                    'accuracy': accuracy,
                    'cards_attempted': item['total']
                })
        except Topic.DoesNotExist:
            pass
    
    weak_topics = sorted(weak_topics, key=lambda x: x['accuracy'])[:5]
    
    # Recent sessions
    recent_sessions = []
    sessions = StudySession.objects.filter(
        user=user,
        ended_at__isnull=False
    ).order_by('-started_at')[:10]
    
    for session in sessions:
        accuracy = round((session.cards_correct / session.cards_reviewed * 100) if session.cards_reviewed > 0 else 0, 1)
        
        recent_sessions.append({
            'id': str(session.id),
            'date': session.started_at.strftime('%Y-%m-%d'),
            'mode': session.mode,
            'cards_reviewed': session.cards_reviewed,
            'accuracy': accuracy,
            'duration_minutes': round(session.duration_seconds / 60, 1),
            'xp_earned': session.xp_earned
        })
    
    return JsonResponse({
        'success': True,
        'data': {
            'mastery_percent': mastery_percent,
            'avg_accuracy': avg_accuracy,
            'cards_reviewed_last_7_days': cards_last_7_days,
            'current_streak': streak.current_streak,
            'longest_streak': streak.longest_streak,
            'total_xp': streak.total_xp,
            'total_cards_studied': streak.total_cards_studied,
            'subject_stats': subject_stats,
            'weak_topics': weak_topics,
            'recent_sessions': recent_sessions
        }
    })

from django.db.models import ExpressionWrapper, FloatField, F, Case, When, Q, Count, Avg
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from .models import (
    Subject, Unit, Topic, Flashcard, 
    UserFlashcardProgress, UserStreak, 
    Badge, UserBadge, StudySession
)

@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_bookmarks_hierarchy(request):
    """
    Get bookmarked flashcards organized by Subject → Unit → Topic hierarchy
    """
    user = request.user
    
    # Get all bookmarked flashcards with related topic, unit, subject
    bookmarks = UserFlashcardProgress.objects.filter(
        user=user,
        is_bookmarked=True
    ).select_related(
        'flashcard__topic__unit__subject'
    ).annotate(
        calculated_accuracy=ExpressionWrapper(
            Case(
                When(total_reviews__gt=0, 
                     then=F('correct_reviews') * 100.0 / F('total_reviews')),
                default=0.0,
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).order_by(
        'flashcard__topic__unit__subject__display_order',
        'flashcard__topic__unit__display_order',
        'flashcard__topic__display_order'
    )
    
    # Organize into hierarchy
    subjects_dict = {}
    
    for bookmark in bookmarks:
        card = bookmark.flashcard
        topic = card.topic
        unit = topic.unit
        subject = unit.subject
        
        # Initialize subject if not exists
        if str(subject.id) not in subjects_dict:
            subjects_dict[str(subject.id)] = {
                'id': str(subject.id),
                'name': subject.name,
                'icon': subject.icon,
                'color': subject.color,
                'bookmark_count': 0,
                'units': {}
            }
        
        # Initialize unit if not exists
        if str(unit.id) not in subjects_dict[str(subject.id)]['units']:
            subjects_dict[str(subject.id)]['units'][str(unit.id)] = {
                'id': str(unit.id),
                'name': unit.name,
                'bookmark_count': 0,
                'topics': {}
            }
        
        # Initialize topic if not exists
        if str(topic.id) not in subjects_dict[str(subject.id)]['units'][str(unit.id)]['topics']:
            subjects_dict[str(subject.id)]['units'][str(unit.id)]['topics'][str(topic.id)] = {
                'id': str(topic.id),
                'name': topic.name,
                'bookmark_count': 0,
                'flashcards': []
            }
        
        # Add flashcard data
        accuracy = bookmark.accuracy
        
        flashcard_data = {
            'id': str(card.id),
            'front_text': card.front_text,
            'back_text': card.back_text,
            'front_image_url': request.build_absolute_uri(card.front_image.url) if card.front_image else None,
            'back_image_url': request.build_absolute_uri(card.back_image.url) if card.back_image else None,
            'difficulty': card.difficulty,
            'card_type': card.card_type,
            'mnemonic': card.mnemonic,
            'key_points': card.key_points,
            'user_note': bookmark.user_note,
            'accuracy': accuracy,
            'status': bookmark.status,
            'next_review': bookmark.next_review.isoformat(),
        }
        
        subjects_dict[str(subject.id)]['units'][str(unit.id)]['topics'][str(topic.id)]['flashcards'].append(flashcard_data)
        
        # Update counts
        subjects_dict[str(subject.id)]['bookmark_count'] += 1
        subjects_dict[str(subject.id)]['units'][str(unit.id)]['bookmark_count'] += 1
        subjects_dict[str(subject.id)]['units'][str(unit.id)]['topics'][str(topic.id)]['bookmark_count'] += 1
    
    # Convert to lists
    subjects_list = []
    for subject_data in subjects_dict.values():
        units_list = []
        for unit_data in subject_data['units'].values():
            topics_list = []
            for topic_data in unit_data['topics'].values():
                topics_list.append(topic_data)
            unit_data['topics'] = topics_list
            units_list.append(unit_data)
        subject_data['units'] = units_list
        subjects_list.append(subject_data)
    
    return JsonResponse({
        'success': True,
        'data': {
            'subjects': subjects_list,
            'total_bookmarks': sum(s['bookmark_count'] for s in subjects_list)
        }
    })


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from payments.models import UserSubscriptionManager


@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_flashcard_access(request):
    """
    Check if user can start flashcard study session based on:
    1. Free sessions remaining (3 sessions limit)
    2. Active subscription status
    """
    try:
        user = request.user
        profile = user.profile
        
        print(f"?? Checking FLASHCARD access")
        print(f"?? User: {user.username}, Free Sessions: {profile.flashcard_sessions_remaining}")
        
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
        
        print(f"? Subscription: {has_active_subscription}")
        
        # User has active subscription - unlimited access
        if has_active_subscription:
            return Response({
                'success': True,
                'access_granted': True,
                'access_type': 'subscription',
                'message': 'Access granted via active subscription',
                'flashcard_sessions_remaining': profile.flashcard_sessions_remaining,
                'has_subscription': True,
                'active_subscriptions': active_subscriptions
            })
        
        # User has free sessions remaining
        if profile.has_flashcard_sessions_left:
            return Response({
                'success': True,
                'access_granted': True,
                'access_type': 'free',
                'message': f'Access granted via free sessions. {profile.flashcard_sessions_remaining - 1} sessions will remain after this one.',
                'flashcard_sessions_remaining': profile.flashcard_sessions_remaining,
                'flashcard_sessions_after': profile.flashcard_sessions_remaining - 1,
                'has_subscription': False
            })
        
        # User doesn't have access - need subscription
        return Response({
            'success': True,
            'access_granted': False,
            'access_type': 'none',
            'message': f'Free session limit reached (3/3). Subscribe to continue unlimited flashcard practice.',
            'flashcard_sessions_remaining': 0,
            'has_subscription': False,
            'redirect_to': 'subscription'
        })
        
    except Exception as e:
        print(f"? Error in check_flashcard_access: {e}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

