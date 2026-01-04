from django.shortcuts import render
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from mcqs.models import Subject, Unit, Chapter, Topic
from django.http import JsonResponse
from mcqs.models import MCQ,TestSession, TestAnswer, difficulties
import json
from django.db.models import Q
# Create your views here.
from django.core.serializers import serialize
from rest_framework.renderers import JSONRenderer
from mcqs.serializers import MCQSerializer,MCQSubmitSerializer
import random
import uuid
from django.views.decorators.csrf import csrf_exempt
from collections import defaultdict

# Create your views here.
@login_required(login_url='/')
def pom_home(request,email_token):
    return render(request, 'pom_home/pom_home.html')

@login_required(login_url='/')
def  pom_overall(request, email_token):
    return render(request, 'pom_overall/pom_overall.html')

from django.shortcuts import render
from django.db.models import Avg, F, Func
from django.db.models.functions import Cast
from django.db.models import UUIDField
from mcqs.models import TestSession, TestAnswer, MCQ, difficulties

@login_required(login_url='/')
def analysis_by_difficulty(request, email_token):
    difficulties_list = ['Easy', 'Medium', 'Tough']

    if request.method == 'POST':
        selected_difficulty = request.POST.get('difficulty')
        if selected_difficulty in difficulties_list:
            # Convert mcq_uid to UUID for comparison - UPDATED: Add pyq=False filter
            test_answers = TestAnswer.objects.annotate(
                mcq_uid_as_uuid=Cast('mcq_uid', output_field=UUIDField())
            ).filter(
                test_session__user=request.user,
                test_session__pyq=False,  # ADDED: Only MCQ sessions
                mcq_uid_as_uuid__in=MCQ.objects.filter(
                    difficulty__name=selected_difficulty
                ).values_list('uid', flat=True),
                timespent__gt=0  # Filter out records where timespent is 0 or negative
            )

            total_questions = test_answers.count()
            correct_questions = test_answers.filter(correct=True).count()
            incorrect_questions = total_questions - correct_questions
            average_time = test_answers.aggregate(average_time=Avg('timespent'))['average_time']

            # UPDATED: Add pyq=False filter
            test_sessions = TestSession.objects.filter(
                user=request.user,
                pyq=False,  # ADDED: Only MCQ sessions
                test_id__in=test_answers.values_list('test_session__test_id', flat=True)
            )

            test_session_details = []
            for session in test_sessions:
                session_answers = test_answers.filter(test_session=session)
                session_details = {
                    'session': session,
                    'total_questions': session_answers.count(),
                    'correct': session_answers.filter(correct=True).count(),
                    'incorrect': session_answers.filter(correct=False).count(),
                    'average_time': session_answers.aggregate(average_time=Avg('timespent'))['average_time']
                }
                test_session_details.append(session_details)

            # Data for the graph
            graph_data = {
                'labels': [str(session.test_id) for session in test_sessions],
                'total_questions': [session_details['total_questions'] for session_details in test_session_details],
                'correct': [session_details['correct'] for session_details in test_session_details],
                'incorrect': [session_details['incorrect'] for session_details in test_session_details],
                'average_time': [session_details['average_time'] for session_details in test_session_details]
            }

            context = {
                'difficulty': selected_difficulty,
                'total_questions': total_questions,
                'correct_questions': correct_questions,
                'incorrect_questions': incorrect_questions,
                'average_time': average_time,
                'test_sessions': test_session_details,
                'graph_data': graph_data
            }
            context.update({'difficulties': difficulties_list})

            return render(request, 'ana/ana.html', context)

    return render(request, 'ana/ana.html', {'difficulties': difficulties_list})

# views.py
from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer
from django.db.models import Avg, Count, Case, When, IntegerField
from decimal import Decimal

@login_required(login_url='/')
def get_accuracy_data(request):
    # Get all test sessions that are submitted - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    ).order_by('created_at')
    
    accuracy_data = []
    
    # Process each test session individually
    for i, session in enumerate(test_sessions):
        correct_answers = TestAnswer.objects.filter(
            test_session=session,
            correct=True
        ).count()
        
        # Calculate accuracy for this session
        accuracy = 0
        if session.total_questions > 0:
            accuracy = float((Decimal(correct_answers) / session.total_questions) * 100)
        
        # Append data to the list with blank label
        accuracy_data.append({
            'label': '',  # Empty label for x-axis
            'accuracy': accuracy,
            'selections': list(session.selections)  # Convert to list for use in template
        })
    
    return accuracy_data

@login_required(login_url='/')
def accuracy_vs_tests(request, email_token):
    accuracy_data = get_accuracy_data(request)
    return render(request, 'graph/acc_test.html', {'accuracy_data': accuracy_data})

from django.shortcuts import render
from mcqs.models import Subject, MCQ, TestAnswer
from django.db.models import Count

@login_required(login_url='/')
def analysis_view_sub_acc(request, email_token):
    # Step 1: Filter TestAnswers for the current user's submitted sessions - UPDATED: Add pyq=False filter
    user_submitted_answers = TestAnswer.objects.filter(
        test_session__submitted=True,
        test_session__user=request.user,
        test_session__pyq=False  # ADDED: Only MCQ sessions
    )
    
    # Step 2: Get all unique MCQ UIDs from the user's submitted answers
    user_mcq_uids = user_submitted_answers.values_list('mcq_uid', flat=True).distinct()
    
    # Step 3: Get all MCQs based on these UIDs
    related_mcqs = MCQ.objects.filter(uid__in=user_mcq_uids)
    
    # Step 4: Get related Subjects by accessing the chain of relationships
    subjects = Subject.objects.filter(
        units__chapters__topics__in=related_mcqs.values_list('topic', flat=True)
    ).distinct()
    
    # Prepare lists for chart data
    labels = []
    attempted = []
    correct = []
    total_questions = []
    not_attempted = []
    incorrect = []
    
    for subject in subjects:
        # Get all MCQs related to this subject
        subject_mcqs = MCQ.objects.filter(topic__chapter__unit__subject=subject).values_list('uid', flat=True)
        total_questions_count = user_submitted_answers.filter(mcq_uid__in=subject_mcqs).count()

        # Count attempts for the current user on MCQs related to this subject with time spent > 0
        attempts_count = user_submitted_answers.filter(mcq_uid__in=subject_mcqs, is_attempted=True).count()
        
        # Count correct answers for the current user on MCQs related to this subject
        correct_count = user_submitted_answers.filter(mcq_uid__in=subject_mcqs, correct=True).count()
        not_attempted_count = total_questions_count - attempts_count
        
        # Count incorrect answers (attempted but not correct)
        incorrect_count = user_submitted_answers.filter(mcq_uid__in=subject_mcqs, is_attempted=True, correct=False).count()
        
        # Add data to lists
        labels.append(subject.name)
        attempted.append(attempts_count)
        correct.append(correct_count)
        total_questions.append(total_questions_count)
        not_attempted.append(not_attempted_count)
        incorrect.append(incorrect_count)
    
    # Render data to the template
    context = {
        'labels': labels,
        'attempted': attempted,
        'correct': correct,
        'total_questions': total_questions,
        'not_attempted': not_attempted,
        'incorrect': incorrect,
    }
    
    return render(request, 'graph/sub_acc.html', context)

# views.py
from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ
from django.db.models import Prefetch
import json

@login_required(login_url='/')
def get_performance_data(request):
    # Fetch all submitted test sessions with efficient querying - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )

    # Prepare a dictionary to store correct and total counts per subject
    subject_performance = {}

    # Iterate through each test session
    for session in test_sessions:
        # Fetch all related test answers efficiently
        answers = TestAnswer.objects.filter(test_session=session)

        for answer in answers:
            try:
                # Get the associated MCQ using UUID
                mcq = MCQ.objects.get(uid=answer.mcq_uid)
                subject_name = mcq.topic.chapter.unit.subject.name

                # Initialize counters if not already present
                if subject_name not in subject_performance:
                    subject_performance[subject_name] = {'correct': 0, 'total': 0}

                # Increment total count
                subject_performance[subject_name]['total'] += 1

                # Increment correct count if the answer is correct
                if answer.correct:
                    subject_performance[subject_name]['correct'] += 1

            except MCQ.DoesNotExist:
                # Handle case where MCQ doesn't exist for the UUID
                continue

    # Calculate performance percentage for each subject
    subject_percentage = {
        subject: (data['correct'] / data['total']) * 100
        for subject, data in subject_performance.items()
        if data['total'] > 0
    }

    return subject_percentage

@login_required(login_url='/')
def performance_radar_view(request, email_token):
    performance_data = get_performance_data(request)
    labels = list(performance_data.keys())
    data = [round(value, 2) for value in performance_data.values()]
    
    context = {
        'labels': json.dumps(labels),
        'data': json.dumps(data),
    }

    return render(request, 'graph/radar.html', context)

from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ

@login_required(login_url='/')
def get_difficulty_data(request):
   # Data structure to hold count and total time for each difficulty
   difficulty_data = {
       'Easy': {'total_questions': 0, 'attempted': 0, 'correct': 0, 'total_time': 0, 'avg_time': 0},
       'Medium': {'total_questions': 0, 'attempted': 0, 'correct': 0, 'total_time': 0, 'avg_time': 0},
       'Tough': {'total_questions': 0, 'attempted': 0, 'correct': 0, 'total_time': 0, 'avg_time': 0}
   }

   # Fetch test sessions where submitted=True - UPDATED: Add pyq=False filter
   test_sessions = TestSession.objects.filter(
       user=request.user, 
       submitted=True, 
       pyq=False  # ADDED: Only MCQ sessions
   )

   for session in test_sessions:
       # Fetch all answers for the current session
       test_answers = TestAnswer.objects.filter(test_session=session)
       
       for answer in test_answers:
           try:
               # Fetch the corresponding MCQ using mcq_uid
               mcq = MCQ.objects.get(uid=answer.mcq_uid)
               
               # Get the difficulty level of the MCQ
               difficulty = mcq.difficulty.name
               
               # Update total questions
               difficulty_data[difficulty]['total_questions'] += 1
               
               # Update attempted and time if timespent > 0
               if answer.timespent > 0:
                   difficulty_data[difficulty]['attempted'] += 1
                   difficulty_data[difficulty]['total_time'] += answer.timespent
               
               # Update correct answers
               if answer.correct:
                   difficulty_data[difficulty]['correct'] += 1
           
           except MCQ.DoesNotExist:
               continue

   # Calculate average time for attempted questions
   for difficulty, data in difficulty_data.items():
       if data['attempted'] > 0:
           data['avg_time'] = round(data['total_time'] / data['attempted'], 2)
       else:
           data['avg_time'] = 0

   return difficulty_data

@login_required(login_url='/')
def difficulty_vs_time_view(request, email_token):
   # Get the difficulty data
   difficulty_data = get_difficulty_data(request)

   # Prepare context to pass to the template
   context = {
       'difficulty_data': difficulty_data
   }

   # Render the HTML template with the context data
   return render(request, "graph/diff_vs_time.html", context)

from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ
from collections import defaultdict
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from collections import defaultdict
import json
from decimal import Decimal

def decimal_to_json(obj):
   if isinstance(obj, Decimal):
       return float(obj)
   raise TypeError

@login_required(login_url='/')
def type_vs_time(request, email_token):
   # Get all submitted test sessions - UPDATED: Add pyq=False filter
   test_sessions = TestSession.objects.filter(
       user=request.user, 
       submitted=True, 
       pyq=False  # ADDED: Only MCQ sessions
   )
   
   # Initialize a dictionary to hold the total count of questions and the total time spent per type
   type_data = defaultdict(lambda: {
       'total_questions': 0, 
       'attempted': 0, 
       'total_time': 0,
       'correct': 0
   })
   
   # Loop through all test answers in the submitted test sessions
   for session in test_sessions:
       test_answers = TestAnswer.objects.filter(test_session=session)
       
       for answer in test_answers:
           # Retrieve the related MCQ for the current answer
           mcq = MCQ.objects.filter(uid=answer.mcq_uid).first()
           
           if mcq and mcq.types:
               mcq_type = mcq.types.types
               
               # Update total questions for the type
               type_data[mcq_type]['total_questions'] += 1
               
               # Update attempted and time if timespent > 0
               if answer.timespent > 0:
                   type_data[mcq_type]['attempted'] += 1
                   type_data[mcq_type]['total_time'] += answer.timespent
               
               # Update correct answers
               if answer.correct:
                   type_data[mcq_type]['correct'] += 1
   
   # Prepare the data for the frontend
   chart_data = []
   for mcq_type, data in type_data.items():
       attempted = data['attempted']
       avg_time = round(data['total_time'] / attempted, 2) if attempted > 0 else 0
       
       chart_data.append({
           'label': mcq_type,
           'total_questions': data['total_questions'],
           'attempted': attempted,
           'correct': data['correct'],
           'avg_time': avg_time
       })
   
   # Separate lists for chart.js
   labels = [item['label'] for item in chart_data]
   total_questions = [item['total_questions'] for item in chart_data]
   attempted = [item['attempted'] for item in chart_data]
   correct = [item['correct'] for item in chart_data]
   avg_times = [item['avg_time'] for item in chart_data]
   
   context = {
       'chart_data': chart_data,
       'labels': json.dumps(labels),
       'total_questions': json.dumps(total_questions),
       'attempted': json.dumps(attempted),
       'correct': json.dumps(correct),
       'avg_times': json.dumps(avg_times, default=decimal_to_json)
   }
   
   return render(request, "graph/type_vs_time.html", context)

def decimal_to_json(obj):
    if isinstance(obj, Decimal):
        return float(obj)  # or str(obj) if you prefer
    raise TypeError("Object of type Decimal is not JSON serializable")

from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ
from collections import defaultdict
import json

@login_required(login_url='/')
def diff_corr_incorr(request, email_token):
    # Get all the test sessions where submitted=True - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )
    
    # Dictionary to track metrics by difficulty level
    difficulty_data = defaultdict(lambda: {
        'total_questions': 0,
        'attempted': 0,
        'not_attempted': 0,
        'correct': 0,
        'incorrect': 0,  # New field for incorrect attempts
        'accuracy': 0
    })
    
    # Loop through each test session
    for session in test_sessions:
        # Get all answers for the current session
        test_answers = TestAnswer.objects.filter(test_session=session)
        
        # Loop through each answer
        for answer in test_answers:
            try:
                # Retrieve the corresponding MCQ using the UUID
                mcq = MCQ.objects.get(pk=answer.mcq_uid)
                difficulty_level = mcq.difficulty.name
                
                # Update total questions
                difficulty_data[difficulty_level]['total_questions'] += 1
                
                # Track attempted and not attempted
                if answer.is_attempted:
                    difficulty_data[difficulty_level]['attempted'] += 1
                    
                    # Count incorrect attempts
                    if not answer.correct:
                        difficulty_data[difficulty_level]['incorrect'] += 1
                else:
                    difficulty_data[difficulty_level]['not_attempted'] += 1
                
                # Count correct answers
                if answer.correct:
                    difficulty_data[difficulty_level]['correct'] += 1
                
            except MCQ.DoesNotExist:
                continue
    
    # Calculate accuracy and prepare table data
    table_data = []
    difficulty_order = ['Easy', 'Medium', 'Tough']
    labels = []
    total_questions = []
    attempted = []
    not_attempted = []
    correct = []
    incorrect = []  # New list for incorrect attempts
    accuracy = []
    
    for difficulty in difficulty_order:
        if difficulty in difficulty_data:
            data = difficulty_data[difficulty]
            
            # Calculate accuracy
            if data['total_questions'] > 0:
                data['accuracy'] = round((data['correct'] / data['total_questions']) * 100, 2)
            
            table_data.append({
                'difficulty': difficulty,
                'total_questions': data['total_questions'],
                'attempted': data['attempted'],
                'not_attempted': data['not_attempted'],
                'correct': data['correct'],
                'incorrect': data['incorrect'],  # Add incorrect to table data
                'accuracy': data['accuracy']
            })
            
            # Prepare data for chart
            labels.append(difficulty)
            total_questions.append(data['total_questions'])
            attempted.append(data['attempted'])
            not_attempted.append(data['not_attempted'])
            correct.append(data['correct'])
            incorrect.append(data['incorrect'])  # Add incorrect to chart data
            accuracy.append(data['accuracy'])
    
    context = {
        'labels': json.dumps(labels),
        'total_questions': json.dumps(total_questions),
        'attempted': json.dumps(attempted),
        'not_attempted': json.dumps(not_attempted),
        'correct': json.dumps(correct),
        'incorrect': json.dumps(incorrect),  # Add incorrect to context
        'accuracy': json.dumps(accuracy),
        'table_data': table_data
    }
    
    return render(request, 'graph/diff_corr_incorr.html', context)

from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ
from collections import defaultdict
import json

@login_required(login_url='/')
def type_corr_incorr(request, email_token):
    # Get all the test sessions where submitted=True - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )
    
    # Dictionary to track comprehensive metrics by MCQ type
    mcq_type_metrics = defaultdict(lambda: {
        'total_questions': 0,
        'attempted': 0,
        'not_attempted': 0,
        'correct': 0,
        'incorrect': 0,  # New metric to track incorrect answers
        'accuracy': 0.0
    })
    
    # Loop through each test session
    for session in test_sessions:
        # Get all answers for the current session
        test_answers = TestAnswer.objects.filter(test_session=session)
        
        # Loop through each answer
        for answer in test_answers:
            try:
                # Retrieve the corresponding MCQ using the UUID
                mcq = MCQ.objects.get(pk=answer.mcq_uid)
                
                # Check if mcq.types is not None before accessing its 'types' attribute
                if mcq.types:
                    mcq_type = mcq.types.types  # Get the MCQ type name
                    
                    # Increment total questions for this type
                    mcq_type_metrics[mcq_type]['total_questions'] += 1
                    
                    # Track attempted vs not attempted
                    if answer.is_attempted:
                        mcq_type_metrics[mcq_type]['attempted'] += 1
                        
                        # Track correct and incorrect answers
                        if answer.correct:
                            mcq_type_metrics[mcq_type]['correct'] += 1
                        else:
                            mcq_type_metrics[mcq_type]['incorrect'] += 1
                    else:
                        mcq_type_metrics[mcq_type]['not_attempted'] += 1
                    
            except MCQ.DoesNotExist:
                # Handle case where the MCQ is missing
                continue
    
    # Calculate accuracy for each MCQ type
    for mcq_type, metrics in mcq_type_metrics.items():
        total = metrics['total_questions']
        correct = metrics['correct']
        metrics['accuracy'] = (correct / total * 100) if total > 0 else 0.0
    
    # Prepare data for frontend
    context = {
        'mcq_type_metrics': json.dumps({
            mcq_type: {
                'total_questions': metrics['total_questions'],
                'attempted': metrics['attempted'],
                'not_attempted': metrics['not_attempted'],
                'correct': metrics['correct'],
                'incorrect': metrics['incorrect'],
                'accuracy': round(metrics['accuracy'], 2)
            }
            for mcq_type, metrics in mcq_type_metrics.items()
        })
    }
    
    return render(request, 'graph/type_corr_incorr.html', context)

@login_required(login_url='/')
def pom_sub_home(request,email_token):
    subjects = Subject.objects.all().order_by('order')  # Fetch all subjects ordered by 'order'
    return render(request, 'pom_sub_home/pom_sub_home.html', {'subjects': subjects})

@login_required(login_url='/')
def performance_analysis_view(request, email_token):
    # Get the subject from query parameters by name
    subject_name = request.GET.get('subject')
    print(subject_name)
    if not subject_name:
        return render(request, 'error.html', {'message': 'Subject not provided'})

    try:
        # Query the subject by name
        subject = Subject.objects.get(name=subject_name)
    except Subject.DoesNotExist:
        return render(request, 'error.html', {'message': 'Subject not found'})

    # Get all test sessions submitted by the user - UPDATED: Add pyq=False filter
    user = request.user
    test_sessions = TestSession.objects.filter(
        user=user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )

    # Get all the UUIDs of MCQs related to the selected subject via hierarchy
    mcqs_in_subject = MCQ.objects.filter(topic__chapter__unit__subject=subject)
    mcq_uuids = mcqs_in_subject.values_list('uid', flat=True)

    # Filter test sessions to only include those that have MCQs from the subject
    relevant_sessions = test_sessions.filter(testanswer__mcq_uid__in=mcq_uuids).distinct()

    # Initialize counters for attempts, correct answers, and time spent by difficulty and type
    attempts_by_difficulty = defaultdict(int)
    correct_by_difficulty = defaultdict(int)
    attempts_by_type = defaultdict(int)
    correct_by_type = defaultdict(int)

    total_time_by_difficulty = defaultdict(float)
    count_by_difficulty = defaultdict(int)  # Count for average time calculation

    total_time_by_type = defaultdict(float)
    count_by_type = defaultdict(int)  # Count for average time calculation

    # Get all TestAnswers for the user's relevant test sessions
    test_answers = TestAnswer.objects.filter(test_session__in=relevant_sessions, mcq_uid__in=mcq_uuids)

    # Analyze the test answers to categorize by difficulty and type
    for answer in test_answers:
        try:
            mcq = MCQ.objects.get(uid=answer.mcq_uid)
        except MCQ.DoesNotExist:
            continue

        # Count attempts and correct answers by difficulty
        difficulty = mcq.difficulty.name if mcq.difficulty else 'Unknown'
        attempts_by_difficulty[difficulty] += 1
        if answer.correct:
            correct_by_difficulty[difficulty] += 1

        # Count attempts and correct answers by MCQ type
        mcq_type = mcq.types.types if mcq.types else 'Unknown'
        attempts_by_type[mcq_type] += 1
        if answer.correct:
            correct_by_type[mcq_type] += 1

        # Calculate total time spent by difficulty and type (only if time spent > 0)
        time_spent = float(answer.timespent)
        if time_spent > 0:
            total_time_by_difficulty[difficulty] += time_spent
            count_by_difficulty[difficulty] += 1
            total_time_by_type[mcq_type] += time_spent
            count_by_type[mcq_type] += 1

    # Prepare data for the charts
    difficulty_levels = ['Easy', 'Medium', 'Tough']
    mcq_types_labels = ['General', 'Clinical', 'Image']

    # Build chart data arrays for attempts and correct answers
    attempts_data_difficulty = [attempts_by_difficulty[level] for level in difficulty_levels]
    correct_data_difficulty = [correct_by_difficulty[level] for level in difficulty_levels]

    attempts_data_type = [attempts_by_type[type_label] for type_label in mcq_types_labels]
    correct_data_type = [correct_by_type[type_label] for type_label in mcq_types_labels]

    # Calculate average time spent per MCQ by difficulty and type
    average_time_difficulty = [
        total_time_by_difficulty[level] / count_by_difficulty[level] if count_by_difficulty[level] > 0 else 0
        for level in difficulty_levels
    ]

    average_time_type = [
        total_time_by_type[type_label] / count_by_type[type_label] if count_by_type[type_label] > 0 else 0
        for type_label in mcq_types_labels
    ]

    # Subject-wise performance data for the line chart
    performance_data = []

    for session in relevant_sessions:
        # Get TestAnswers for this session
        session_answers = TestAnswer.objects.filter(test_session=session)

        # Filter MCQs related to the subject
        mcqs = MCQ.objects.filter(uid__in=session_answers.values_list('mcq_uid', flat=True), topic__chapter__unit__subject=subject)
        
        total_mcqs = mcqs.count()
        correct_mcqs = session_answers.filter(correct=True, mcq_uid__in=mcqs.values_list('uid', flat=True)).count()

        accuracy_percentage = (correct_mcqs / total_mcqs * 100) if total_mcqs > 0 else 0
        performance_data.append({
            'session': session.test_id,
            'accuracy': accuracy_percentage
        })

    # Group performance data
    grouped_data = group_performance_data(performance_data)

    # Pass all the data to the template for rendering the charts
    context = {
        'attempts_data_difficulty': attempts_data_difficulty,
        'correct_data_difficulty': correct_data_difficulty,
        'attempts_data_type': attempts_data_type,
        'correct_data_type': correct_data_type,
        'average_time_difficulty': average_time_difficulty,  # Average time by difficulty for chart
        'average_time_type': average_time_type,  # Average time by type for chart
        'performance_data': grouped_data,
        "subject":subject_name  # Line chart data for subject-wise performance
    }

    return render(request, 'pom_sub_home/pom_sub_ana.html', context)

def group_performance_data(performance_data):
    # Sort the data by session ID
    performance_data.sort(key=lambda x: x['session'])
    
    # Determine group size
    total_sessions = len(performance_data)
    if total_sessions < 5:
        group_size = 1
    elif total_sessions <= 10:
        group_size = 2
    elif total_sessions <= 20:
        group_size = 4
    else:
        group_size = 10
    
    # Group data and calculate average accuracy for each group
    grouped_data = []
    num_groups = (total_sessions + group_size - 1) // group_size  # Calculate number of groups
    
    for i in range(num_groups):
        group = performance_data[i * group_size:(i + 1) * group_size]
        average_accuracy = sum(item['accuracy'] for item in group) / len(group) if group else 0
        group_label = f"Test {i * group_size + 1}-{min((i + 1) * group_size, total_sessions)}"
        grouped_data.append({
            'label': group_label,
            'accuracy': average_accuracy
        })
    
    return grouped_data

from django.shortcuts import render
from mcqs.models import TestSession

@login_required(login_url='/')
def custome_ana_view(request, email_token):
    # Fetch all submitted TestSession records, ordered from newest to oldest - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    ).order_by('-created_at')
    
    if request.user.is_authenticated:
        if email_token==request.user.profile.email_token:
            data = {}

            subjects = Subject.objects.all()
            for subject in subjects:
                units = Unit.objects.filter(subject=subject)
                data[subject.name] = {}

                for unit in units:
                    chapters = Chapter.objects.filter(unit=unit)
                    data[subject.name][unit.name] = {}

                    for chapter in chapters:
                        topics = Topic.objects.filter(chapter=chapter)
                        data[subject.name][unit.name][chapter.name] = [topic.name for topic in topics]

    context = {
        'test_sessions': test_sessions,
        'data': data
    }
    
    return render(request, 'pom_cus/pom_cus_home.html', context)

from django.http import HttpResponse  # Make sure to import HttpResponse
from django.shortcuts import render, get_object_or_404
from mcqs.models import TestSession, TestAnswer, MCQ

@login_required(login_url='/')
def test_wise_parti(request, email_token):
    # Fetch the test_id from the request
    test_id = request.GET.get('test_id')

    # Fetch the test session for the current user using the test_id - UPDATED: Add pyq=False filter
    test_session = get_object_or_404(
        TestSession, 
        test_id=test_id, 
        user=request.user, 
        pyq=False  # ADDED: Only MCQ sessions
    )
    test_session.timetaken_minutes = round(test_session.timetaken / 60, 2)
    test_answers = TestAnswer.objects.filter(test_session=test_session)

    question_data = []
    total_correct = total_incorrect = total_not_attempted = 0
    type_counts = {"clinical": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0},
                   "image": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0},
                   "general": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0}}
    difficulty_counts = {"easy": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0},
                         "medium": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0},
                         "tough": {"correct": 0, "incorrect": 0, "not_attempted": 0, "total": 0}}

    # Loop through each test answer to calculate counts for analysis
    for answer in test_answers:
        mcq = get_object_or_404(MCQ, uid=answer.mcq_uid)

        topic = mcq.topic
        chapter = topic.chapter
        unit = chapter.unit
        subject = unit.subject
        hierarchy = f"{subject.name} - Unit {unit.name} - Chapter {chapter.name} - Topic {topic.name}"

        is_correct = answer.correct
        is_attempted = answer.is_attempted

        # Count for total questions
        if is_correct:
            total_correct += 1
        elif is_attempted:
            total_incorrect += 1
        else:
            total_not_attempted += 1

        # Type-wise counts
        mcq_type = mcq.types.types.lower() if mcq.types else "gen"
        if mcq_type in type_counts:
            type_counts[mcq_type]["total"] += 1  # Count total questions for the type
            if is_correct:
                type_counts[mcq_type]["correct"] += 1
            elif is_attempted:
                type_counts[mcq_type]["incorrect"] += 1
            else:
                type_counts[mcq_type]["not_attempted"] += 1

        # Difficulty-level counts
        difficulty_level = mcq.difficulty.name.lower() if mcq.difficulty else "medium"
        if difficulty_level in difficulty_counts:
            difficulty_counts[difficulty_level]["total"] += 1  # Count total questions for the difficulty
            if is_correct:
                difficulty_counts[difficulty_level]["correct"] += 1
            elif is_attempted:
                difficulty_counts[difficulty_level]["incorrect"] += 1
            else:
                difficulty_counts[difficulty_level]["not_attempted"] += 1

        # Question data for template
        question_details = {
            'question_text': mcq.text,
            'options': [mcq.option_1, mcq.option_2, mcq.option_3, mcq.option_4],
            'correct_option': mcq.correct_option,
            'explanation': mcq.explanation,
            'image': mcq.image.url if mcq.image else None,
            'hierarchy': hierarchy,
            'difficulty': mcq.difficulty.name if mcq.difficulty else "Unknown",
            'type': mcq.types.types if mcq.types else "Unknown",
            'user_answer': answer.selected_optiontext,
            'is_correct': is_correct,
            'is_attempted': is_attempted,
            'time_spent': answer.timespent,
            'correct_attempts':mcq.correct_attempts,
            'incorrect_attempts':mcq.incorrect_attempts
        }
        question_data.append(question_details)

    # Prepare context with question data and analysis counts
    context = {
        'test_session': test_session,
        'questions': question_data,
        'total_correct': total_correct,
        'total_incorrect': total_incorrect,
        'total_not_attempted': total_not_attempted,
        'type_counts': type_counts,
        'difficulty_counts': difficulty_counts,
    }

    return render(request, 'pom_cus/pom_cus_test_wise.html', context)

from django.http import JsonResponse
from mcqs.models import Subject, Unit, Chapter, Topic

@login_required(login_url='/')
def get_units(request):
    subject_id = request.GET.get('subject_id')
    units = Unit.objects.filter(subject_id=subject_id).order_by('order')
    units_data = [{'id': unit.id, 'name': unit.name} for unit in units]
    return JsonResponse(units_data, safe=False)

@login_required(login_url='/')
def get_chapters(request):
    unit_id = request.GET.get('unit_id')
    chapters = Chapter.objects.filter(unit_id=unit_id).order_by('order')
    chapters_data = [{'id': chapter.id, 'name': chapter.name} for chapter in chapters]
    return JsonResponse(chapters_data, safe=False)

@login_required(login_url='/')
def get_topics(request):
    chapter_id = request.GET.get('chapter_id')
    topics = Topic.objects.filter(chapter_id=chapter_id).order_by('order')
    topics_data = [{'id': topic.id, 'name': topic.name} for topic in topics]
    return JsonResponse(topics_data, safe=False)

from django.shortcuts import render
from mcqs.models import TestSession, TestAnswer, MCQ
from collections import defaultdict
import json

@login_required(login_url='/')
def pom_cus_cus(request, email_token):
    # Get user and query parameters
    user = request.user
    subject_name = request.GET.get('subject')
    unit_name = request.GET.get('unit')
    chapter_name = request.GET.get('chapter', None)
    topic_name = request.GET.get('topic', None)

    # Filter MCQs based on subject, unit, and optionally chapter and topic
    mcqs = MCQ.objects.filter(topic__chapter__unit__subject__name=subject_name,
                              topic__chapter__unit__name=unit_name)
    if chapter_name:
        mcqs = mcqs.filter(topic__chapter__name=chapter_name)
    if topic_name:
        mcqs = mcqs.filter(topic__name=topic_name)
    mcq_ids = mcqs.values_list('uid', flat=True)  # Get the MCQ IDs

    # Get all relevant test sessions for the user - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )

    # For Performance Over Time (Line Chart)
    session_data = []
    for session in test_sessions:
        answers = TestAnswer.objects.filter(test_session=session, mcq_uid__in=mcq_ids)
        if answers.exists():
            total_questions = len(answers)
            correct_answers = answers.filter(correct=True).count()
            accuracy = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
            session_data.append({
                'session': session,
                'accuracy': accuracy
            })

    # Sort session data by test session creation date
    session_data.sort(key=lambda x: x['session'].created_at)
    total_sessions = len(session_data)

    # Group sessions and calculate average accuracy for performance chart
    if total_sessions < 5:
        accuracy_data = [{'label': f'Test {i + 1}', 'accuracy': data['accuracy']} for i, data in enumerate(session_data)]
    else:
        if total_sessions <= 10:
            group_size = 2
        elif total_sessions <= 20:
            group_size = 4
        else:
            group_size = 10
        grouped_data = []
        num_groups = (total_sessions + group_size - 1) // group_size
        for i in range(num_groups):
            group = session_data[i * group_size:(i + 1) * group_size]
            avg_accuracy = sum(item['accuracy'] for item in group) / len(group) if group else 0
            group_label = f"Test {i * group_size + 1}-{min((i + 1) * group_size, total_sessions)}"
            grouped_data.append({
                'label': group_label,
                'accuracy': avg_accuracy
            })
        accuracy_data = grouped_data

    # For Attempts by Type and Difficulty (Pie Charts)
    attempts_by_type = defaultdict(int)
    correct_by_type = defaultdict(int)
    attempts_by_difficulty = defaultdict(int)
    correct_by_difficulty = defaultdict(int)

    # For Average Time by Type and Difficulty (New Feature)
    time_by_type = defaultdict(list)
    time_by_difficulty = defaultdict(list)

    for session in test_sessions:
        answers = TestAnswer.objects.filter(test_session=session, mcq_uid__in=mcq_ids)
        for answer in answers:
            mcq = MCQ.objects.filter(uid=answer.mcq_uid).first()
            if mcq:
                # Track attempts and correctness by type and difficulty
                if mcq.types:
                    question_type = mcq.types.types
                    attempts_by_type[question_type] += 1
                    if answer.correct:
                        correct_by_type[question_type] += 1
                    if answer.timespent > 0:
                        time_by_type[question_type].append(answer.timespent)

                if mcq.difficulty:
                    difficulty = mcq.difficulty.name
                    attempts_by_difficulty[difficulty] += 1
                    if answer.correct:
                        correct_by_difficulty[difficulty] += 1
                    if answer.timespent > 0:
                        time_by_difficulty[difficulty].append(answer.timespent)

    # Calculate average time spent by type and difficulty
    average_time_data = {
    'General': float(sum(time_by_type['General'])) / len(time_by_type['General']) if time_by_type['General'] else 0,
    'Image': float(sum(time_by_type['Image'])) / len(time_by_type['Image']) if time_by_type['Image'] else 0,
    'Clinical': float(sum(time_by_type['Clinical'])) / len(time_by_type['Clinical']) if time_by_type['Clinical'] else 0,
    # Add for difficulties as well
    'Easy': float(sum(time_by_difficulty['Easy'])) / len(time_by_difficulty['Easy']) if time_by_difficulty['Easy'] else 0,
    'Medium': float(sum(time_by_difficulty['Medium'])) / len(time_by_difficulty['Medium']) if time_by_difficulty['Medium'] else 0,
    'Tough': float(sum(time_by_difficulty['Tough'])) / len(time_by_difficulty['Tough']) if time_by_difficulty['Tough'] else 0,
}
    # Prepare data for the frontend (attempts and accuracy for type & difficulty)
    type_labels = ['General', 'Image', 'Clinical']
    difficulty_labels = ['Easy', 'Medium', 'Tough']
    attempts_data_type = [attempts_by_type[label] for label in type_labels]
    correct_data_type = [correct_by_type[label] for label in type_labels]
    attempts_data_difficulty = [attempts_by_difficulty[label] for label in difficulty_labels]
    correct_data_difficulty = [correct_by_difficulty[label] for label in difficulty_labels]

    context = {
        'subject_name': subject_name,
        'unit_name': unit_name,
        'chapter_name': chapter_name,
        'topic_name': topic_name,
        # Performance data
        'accuracy_data': json.dumps(accuracy_data),
        # Attempts by Type & Difficulty
        'attempts_data_type': json.dumps(attempts_data_type),
        'correct_data_type': json.dumps(correct_data_type),
        'attempts_data_difficulty': json.dumps(attempts_data_difficulty),
        'correct_data_difficulty': json.dumps(correct_data_difficulty),
        # Average time per type and difficulty
         'average_time_data': json.dumps(average_time_data)
    }

    return render(request, 'pom_cus/pom_cus_cus.html', context)

from django.db.models import Count, Q, Avg
from django.shortcuts import render
from decimal import Decimal
from mcqs.models import TestSession, TestAnswer, Topic, MCQ, Subject, Unit, Chapter, difficulties, mcq_types

@login_required(login_url='/')
def pom_cus_top_comp(request, email_token):
    # Get the subject, unit, and chapter from the GET parameters
    subject_name = request.GET.get('subject')
    unit_name = request.GET.get('unit')
    chapter_name = request.GET.get('chapter')

    # Fetch subject, unit, and chapter
    try:
        subject = Subject.objects.get(name=subject_name)
        unit = Unit.objects.get(name=unit_name, subject=subject)
        chapter = Chapter.objects.get(name=chapter_name, unit=unit)
    except (Subject.DoesNotExist, Unit.DoesNotExist, Chapter.DoesNotExist):
        return render(request, 'error.html', {'message': 'Invalid Subject, Unit, or Chapter'})

    # Fetch all submitted test sessions for the user - UPDATED: Add pyq=False filter
    test_sessions = TestSession.objects.filter(
        user=request.user, 
        submitted=True, 
        pyq=False  # ADDED: Only MCQ sessions
    )

    # Fetch all test answers from the user's submitted test sessions
    test_answers = TestAnswer.objects.filter(test_session__in=test_sessions)

    # Fetch all topics related to the chapter
    topics = Topic.objects.filter(chapter=chapter)

    # Initialize data lists for topic-wise stats
    topic_labels = []
    total_faced_data = []
    correct_data = []
    incorrect_data = []
    not_attempted_data = []

    # Get all difficulty levels and MCQ types dynamically from the models
    all_difficulties = difficulties.objects.all()
    all_mcq_types = mcq_types.objects.all()

    # Initialize data structure for difficulty-wise and type-wise stats
    difficulty_stats = {difficulty.name: {'total_faced': [], 'correct': [], 'incorrect': [], 'not_attempted': [], 'average_time': []}
                        for difficulty in all_difficulties}
    type_stats = {mcq_type.types: {'total_faced': [], 'correct': [], 'incorrect': [], 'not_attempted': [], 'average_time': []}
                  for mcq_type in all_mcq_types}

    # Iterate over each topic in the chapter
    for topic in topics:
        # Get MCQs under the current topic
        mcqs = MCQ.objects.filter(topic=topic)

        # Test answers related to the MCQs of the current topic
        answers = test_answers.filter(mcq_uid__in=mcqs.values_list('uid', flat=True))

        # Total questions faced in this topic
        total_faced = answers.count()

        # Correct answers in this topic
        correct = answers.filter(correct=True).count()

        # Incorrect answers in this topic (attempted but incorrect)
        incorrect = answers.filter(Q(correct=False) & Q(is_attempted=True)).count()

        # Not attempted questions in this topic
        not_attempted = answers.filter(is_attempted=False).count()

        # Append data for this topic (topic-wise stats)
        topic_labels.append(topic.name)
        total_faced_data.append(total_faced)
        correct_data.append(correct)
        incorrect_data.append(incorrect)
        not_attempted_data.append(not_attempted)

        # For each difficulty level, gather test answer stats including average time spent
        for difficulty in all_difficulties:
            # Get the MCQs with this difficulty level under the current topic
            mcqs_for_difficulty = mcqs.filter(difficulty=difficulty)

            # Get the test answers for these MCQs
            answers_for_difficulty = test_answers.filter(mcq_uid__in=mcqs_for_difficulty.values_list('uid', flat=True))

            # Exclude answers where time_spent is 0 before calculating average time
            answers_for_difficulty_with_time = answers_for_difficulty.exclude(timespent=0)

            # Calculate total faced, correct, incorrect, not attempted, and average time spent
            total_faced_difficulty = answers_for_difficulty.count()
            correct_difficulty = answers_for_difficulty.filter(correct=True).count()
            incorrect_difficulty = answers_for_difficulty.filter(Q(correct=False) & Q(is_attempted=True)).count()
            not_attempted_difficulty = answers_for_difficulty.filter(is_attempted=False).count()
            average_time_difficulty = answers_for_difficulty_with_time.aggregate(average_time=Avg('timespent'))['average_time'] or Decimal('0')

            # Convert to string for JavaScript
            difficulty_stats[difficulty.name]['total_faced'].append(total_faced_difficulty)
            difficulty_stats[difficulty.name]['correct'].append(correct_difficulty)
            difficulty_stats[difficulty.name]['incorrect'].append(incorrect_difficulty)
            difficulty_stats[difficulty.name]['not_attempted'].append(not_attempted_difficulty)
            difficulty_stats[difficulty.name]['average_time'].append(str(average_time_difficulty))

        # For each MCQ type, gather test answer stats including average time spent
        for mcq_type in all_mcq_types:
            # Get the MCQs of this type under the current topic
            mcqs_for_type = mcqs.filter(types=mcq_type)

            # Get the test answers for these MCQs
            answers_for_type = test_answers.filter(mcq_uid__in=mcqs_for_type.values_list('uid', flat=True))

            # Exclude answers where time_spent is 0 before calculating average time
            answers_for_type_with_time = answers_for_type.exclude(timespent=0)

            # Calculate total faced, correct, incorrect, not attempted, and average time spent
            total_faced_type = answers_for_type.count()
            correct_type = answers_for_type.filter(correct=True).count()
            incorrect_type = answers_for_type.filter(Q(correct=False) & Q(is_attempted=True)).count()
            not_attempted_type = answers_for_type.filter(is_attempted=False).count()
            average_time_type = answers_for_type_with_time.aggregate(average_time=Avg('timespent'))['average_time'] or Decimal('0')

            # Convert to string for JavaScript
            type_stats[mcq_type.types]['total_faced'].append(total_faced_type)
            type_stats[mcq_type.types]['correct'].append(correct_type)
            type_stats[mcq_type.types]['incorrect'].append(incorrect_type)
            type_stats[mcq_type.types]['not_attempted'].append(not_attempted_type)
            type_stats[mcq_type.types]['average_time'].append(str(average_time_type))

    # Pass the data to the template for rendering (topic-wise, difficulty-wise, type-wise stats, and average time)
    context = {
        'topic_labels': topic_labels,
        'total_faced_data': total_faced_data,
        'correct_data': correct_data,
        'incorrect_data': incorrect_data,
        'not_attempted_data': not_attempted_data,
        'difficulty_stats': difficulty_stats,
        'type_stats': type_stats,
    }

    return render(request, 'pom_cus/pom_cus_top_comp.html', context)
