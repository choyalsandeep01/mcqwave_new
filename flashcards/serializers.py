from rest_framework import serializers
from .models import (
    Subject, Unit, Topic, Flashcard, UserFlashcardProgress,
    UserStreak, Badge, UserBadge, StudySession
)

class SubjectSerializer(serializers.ModelSerializer):
    units_count = serializers.IntegerField(read_only=True)
    flashcards_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Subject
        fields = ['id', 'name', 'icon', 'color', 'display_order', 
                 'units_count', 'flashcards_count']

class UnitSerializer(serializers.ModelSerializer):
    topics_count = serializers.IntegerField(read_only=True)
    flashcards_count = serializers.IntegerField(read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    
    class Meta:
        model = Unit
        fields = ['id', 'subject', 'subject_name', 'name', 'display_order',
                 'topics_count', 'flashcards_count']

class TopicSerializer(serializers.ModelSerializer):
    flashcards_count = serializers.IntegerField(read_only=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    
    class Meta:
        model = Topic
        fields = ['id', 'unit', 'unit_name', 'name', 'display_order', 
                 'flashcards_count']

class FlashcardSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    unit_name = serializers.CharField(source='topic.unit.name', read_only=True)
    subject_name = serializers.CharField(source='topic.unit.subject.name', read_only=True)
    
    class Meta:
        model = Flashcard
        fields = ['id', 'topic', 'topic_name', 'unit_name', 'subject_name',
                 'card_type', 'difficulty', 'front_text', 'back_text',
                 'front_image', 'back_image', 'mnemonic', 'key_points',
                 'references', 'linked_mcq_uids', 'created_at']

class UserFlashcardProgressSerializer(serializers.ModelSerializer):
    flashcard_data = FlashcardSerializer(source='flashcard', read_only=True)
    is_due = serializers.BooleanField(read_only=True)
    accuracy = serializers.FloatField(read_only=True)
    
    class Meta:
        model = UserFlashcardProgress
        fields = ['id', 'flashcard', 'flashcard_data', 'ease_factor', 'repetitions',
                 'interval', 'status', 'last_rating', 'last_reviewed', 'next_review',
                 'total_reviews', 'correct_reviews', 'is_due', 'accuracy']

class UserStreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserStreak
        fields = ['current_streak', 'longest_streak', 'last_study_date',
                 'total_xp', 'total_cards_studied']

class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ['id', 'name', 'description', 'icon', 'color', 'xp_reward']

class UserBadgeSerializer(serializers.ModelSerializer):
    badge_data = BadgeSerializer(source='badge', read_only=True)
    
    class Meta:
        model = UserBadge
        fields = ['id', 'badge', 'badge_data', 'earned_at']

class StudySessionSerializer(serializers.ModelSerializer):
    accuracy = serializers.SerializerMethodField()
    
    class Meta:
        model = StudySession
        fields = ['id', 'cards_reviewed', 'cards_correct', 'duration_seconds',
                 'xp_earned', 'started_at', 'ended_at', 'accuracy']
    
    def get_accuracy(self, obj):
        if obj.cards_reviewed == 0:
            return 0
        return (obj.cards_correct / obj.cards_reviewed) * 100
