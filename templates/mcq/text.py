from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
import random
from .models import MCQ
from .serializers import MCQSerializer

@login_required(login_url='/')
def test(request, email_token):
    # Retrieve the selections from the GET request
    selections_json = request.GET.get('selections')
    print("selection_json:", selections_json)
    selections = json.loads(selections_json) if selections_json else []
    print("Selections:", selections)
    question_type = request.GET.get('questionType')
    difficulty_level = request.GET.get('difficultyLevel')

    # Start building the query
    mcq_query = Q()

    for selection in selections:
        parts = selection.split('-')
        subject_name = parts[0]

        if len(parts) == 1:
            mcq_query |= Q(topic__chapter__unit__subject__name=subject_name)
        elif len(parts) == 2:
            unit_name = parts[1]
            mcq_query |= Q(topic__chapter__unit__subject__name=subject_name, topic__chapter__unit__name=unit_name)
        elif len(parts) == 3:
            unit_name = parts[1]
            chapter_name = parts[2]
            mcq_query |= Q(topic__chapter__unit__subject__name=subject_name, topic__chapter__unit__name=unit_name, topic__chapter__name=chapter_name)
        elif len(parts) == 4:
            unit_name = parts[1]
            chapter_name = parts[2]
            topic_name = parts[3]
            mcq_query |= Q(topic__chapter__unit__subject__name=subject_name, topic__chapter__unit__name=unit_name, topic__chapter__name=chapter_name, topic__name=topic_name)

    # Filter the MCQs based on the built query
    mcqs = MCQ.objects.filter(mcq_query)

    if question_type != "mixed":
        mcqs = mcqs.filter(types__types__contains=question_type)

    if difficulty_level != "mixed":
        mcqs = mcqs.filter(difficulty__name__contains=difficulty_level)

    # Convert the queryset to a list and shuffle it
    mcqs = list(mcqs)
    random.shuffle(mcqs)

    # Save the ordered list of MCQ IDs in the session
    request.session['mcq_order'] = [mcq.id for mcq in mcqs]

    # Serialize the MCQs without sensitive fields like correct_option and explanation
    serializer = MCQSerializer(mcqs, many=True, context={'show_sensitive': False})
    mcqs_data = serializer.data

    return render(request, 'mcq/mcq.html', {'mcqs': json.dumps(mcqs_data), 'count': len(mcqs)})

@login_required(login_url='/')
def review_mcqs(request, email_token):
    # Retrieve the list of MCQ IDs from the session
    mcq_order = request.session.get('mcq_order', [])

    if not mcq_order:
        return JsonResponse({'error': 'No quiz found to review.'}, status=400)

    # Retrieve the MCQs based on the saved order
    mcqs = MCQ.objects.filter(id__in=mcq_order)
    mcq_dict = {mcq.id: mcq for mcq in mcqs}

    # Reorder MCQs to match the saved order
    ordered_mcqs = [mcq_dict[mcq_id] for mcq_id in mcq_order if mcq_id in mcq_dict]

    # Serialize with sensitive fields included
    serializer = MCQSerializer(ordered_mcqs, many=True, context={'show_sensitive': True})
    mcqs_data = serializer.data

    return JsonResponse({'mcqs': mcqs_data})



js------------------------------------------------------

    function showReviewMode() {
        // Hide result section and show MCQ container
        isReviewMode = true; // Enter review mode
        document.getElementById('results-section').style.display = 'none'; // Hide results section
        document.querySelector('.mcq-container').style.display = 'block'; // Show MCQ container
        ensureScroll();
        const footer = document.querySelector('.mcq-footer');
        
        footer.classList.add('review-mode');
        
        // Make AJAX request to review_mcqs view
        const emailToken = 'your-email-token'; // Replace with actual email_token value
    
        fetch(`/review_mcqs/${emailToken}/`)
            .then(response => response.json())
            .then(data => {
                // Assume the data contains the mcqs in the same format as in the 'test' view
                mcqs = data.mcqs; // Replace the current MCQs with the reviewed ones
                currentQuestionIndex = 0;
                loadQuestion(currentQuestionIndex);
            })
            .catch(error => {
                console.error('Error fetching review data:', error);
            });
    }

urls.py===================================
from django.urls import path
from . import views

urlpatterns = [
    # Other URL patterns...

    # Add the URL pattern for the review_mcqs view
    path('review_mcqs/<str:email_token>/', views.review_mcqs, name='review_mcqs'),
]


views.py----------------review mcq-----------------------------

    @login_required(login_url='/')
def review_mcqs(request, email_token):
    # Retrieve the list of MCQ IDs from the session
    mcq_order = request.session.get('mcq_order', [])

    if not mcq_order:
        return JsonResponse({'error': 'No quiz found to review.'}, status=400)

    # Retrieve the MCQs based on the saved order
    mcqs = MCQ.objects.filter(id__in=mcq_order)
    mcq_dict = {mcq.id: mcq for mcq in mcqs}

    # Reorder MCQs to match the saved order
    ordered_mcqs = [mcq_dict[mcq_id] for mcq_id in mcq_order if mcq_id in mcq_dict]

    # Serialize with sensitive fields included
    serializer = MCQSerializer(ordered_mcqs, many=True, context={'show_sensitive': True})
    mcqs_data = serializer.data

    return JsonResponse({'mcqs': mcqs_data})





serializer.py----------------------------------------------------------------------

    from rest_framework import serializers
from .models import MCQ

class MCQSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQ
        fields = ['uid', 'text', 'option_1', 'option_2', 'option_3', 'option_4', 'correct_option', 'explanation', 'image']

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Check context to determine if we should include sensitive data
        show_sensitive = self.context.get('show_sensitive', False)
        
        if not show_sensitive:
            # Remove sensitive fields if not in a review context
            representation.pop('correct_option')
            representation.pop('explanation')

        return representation


python manage.py shell -c "from bakmann import update_mcq_explanations; update_mcq_explanations('Gynecology')"
