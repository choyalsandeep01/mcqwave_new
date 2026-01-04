import os
import django
from decimal import Decimal
from collections import defaultdict

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.contrib.auth.models import User
from mcqs.models import TestSession  # Update with your actual app name

def calculate_user_rankings():
    """
    Calculate total scores, total questions, and overall percentage per user
    for all submitted tests and save rankings to a text file.
    """
    # Get all submitted test sessions
    submitted_tests = TestSession.objects.filter(submitted=True)
    
    # Dictionary to store aggregated user results
    user_totals = defaultdict(lambda: {
        'username': '',
        'total_score': Decimal('0'),
        'total_questions': Decimal('0'),
        'total_time': Decimal('0'),
        'test_count': 0
    })
    
    # Aggregate scores for each user
    for test in submitted_tests:
        user_data = user_totals[test.user.id]
        user_data['username'] = test.user.username
        user_data['total_score'] += test.score
        user_data['total_questions'] += test.total_questions
        user_data['total_time'] += test.timetaken
        user_data['test_count'] += 1
    
    # Calculate percentages and prepare for ranking
    user_rankings = []
    for user_id, data in user_totals.items():
        if data['total_questions'] > 0:
            overall_percentage = (data['total_score'] / data['total_questions']) * 100
        else:
            overall_percentage = Decimal('0')
            
        user_rankings.append({
            'username': data['username'],
            'total_score': float(data['total_score']),
            'total_questions': float(data['total_questions']),
            'overall_percentage': float(overall_percentage),
            'average_time': float(data['total_time'] / data['test_count']),
            'tests_taken': data['test_count']
        })
    
    # Sort by overall percentage (descending) and average time (ascending)
    ranked_results = sorted(
        user_rankings,
        key=lambda x: (-x['overall_percentage'], x['average_time'])
    )
    
    # Write results to file
    with open('user_rankings.txt', 'w') as f:
        f.write("USER OVERALL RANKINGS REPORT\n")
        f.write("===========================\n\n")
        
        # Write overall statistics
        f.write(f"Total Users: {len(ranked_results)}\n")
        if ranked_results:
            avg_overall = sum(r['overall_percentage'] for r in ranked_results) / len(ranked_results)
            f.write(f"Average Overall Score: {avg_overall:.2f}%\n")
        f.write("\n")
        
        # Write individual rankings
        f.write("RANKINGS BY OVERALL PERCENTAGE\n")
        f.write("=============================\n")
        
        for rank, result in enumerate(ranked_results, 1):
            f.write(f"\nRank #{rank}\n")
            f.write(f"Username: {result['username']}\n")
            f.write(f"Total Score: {result['total_score']}/{result['total_questions']}\n")
            f.write(f"Overall Percentage: {result['overall_percentage']:.2f}%\n")
            f.write(f"Tests Taken: {result['tests_taken']}\n")
            f.write(f"Average Time per Test: {result['average_time']:.2f} seconds\n")
            f.write("-" * 50 + "\n")

if __name__ == "__main__":
    try:
        calculate_user_rankings()
        print("User rankings have been calculated and saved to 'user_rankings.txt'")
    except Exception as e:
        print(f"An error occurred: {str(e)}")