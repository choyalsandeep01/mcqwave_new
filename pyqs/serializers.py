from rest_framework import serializers
from .models import PYQ


class PYQSerializer(serializers.ModelSerializer):
    exam_display = serializers.SerializerMethodField()
    exam_type = serializers.CharField(source='pyq_cat', read_only=True)
    exam_year = serializers.CharField(source='pyq_year', read_only=True)
    exam_month = serializers.CharField(source='pyq_month', read_only=True)
    
    class Meta:
        model = PYQ
        fields = ['uid', 'text', 'option_1', 'option_2', 'option_3', 'option_4', 'image', 
                  'exam_display', 'exam_type', 'exam_year', 'exam_month']
    
    def get_exam_display(self, obj):
        return obj.get_exam_display()


class PYQSubmitSerializer(serializers.ModelSerializer):
    exam_display = serializers.SerializerMethodField()
    exam_type = serializers.CharField(source='pyq_cat', read_only=True)
    exam_year = serializers.CharField(source='pyq_year', read_only=True)
    exam_month = serializers.CharField(source='pyq_month', read_only=True)
    
    class Meta:
        model = PYQ
        fields = ['uid', 'text', 'option_1', 'option_2', 'option_3', 'option_4', 'image', 
                  'correct_option', 'explanation', 'exam_display', 'exam_type', 'exam_year', 'exam_month']
    
    def get_exam_display(self, obj):
        return obj.get_exam_display()
