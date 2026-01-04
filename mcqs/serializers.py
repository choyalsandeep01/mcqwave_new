from rest_framework import serializers
from .models import MCQ

class MCQSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQ
        fields = ['uid', 'text', 'option_1', 'option_2', 'option_3', 'option_4', 'image']

class MCQSubmitSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQ
        fields = ['uid', 'text', 'option_1', 'option_2', 'option_3', 'option_4', 'image', 'correct_option', 'explanation']