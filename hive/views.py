from django.shortcuts import render,redirect
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import ConnectionRequest, Connection

# Create your views here.
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q  # Import Q for complex queries
from .models import ConnectionRequest, Connection  # Import your models

@login_required(login_url='/')
def hive_home(request, email_token):
    # Get the current user
    user = request.user

    # Fetch connected users in both directions
    connections = Connection.objects.filter(
        Q(user=user) | Q(connected_user=user)  # Use Q for OR queries
    ).select_related('user', 'connected_user')

    # Fetch pending connection requests
    pending_requests = ConnectionRequest.objects.filter(to_user=user)

    # Prepare the list of connected users, handling both directions
    connected_users = []
    for connection in connections:
        if connection.user == user:
            connected_users.append(connection.connected_user)
        else:
            connected_users.append(connection.user)

    # Render the HIVE home template
    context = {
        'connected_users': connected_users,  # Updated variable name
        'pending_requests': pending_requests
    }
    return render(request, 'hive/hive_home.html', context)


from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import Connection, ConnectionRequest
import json
@login_required(login_url='/')
def send_connection_request(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')

        # Check if the username provided is the same as the logged-in user
        if username == request.user.username:
            return JsonResponse({'error': 'You cannot send a connection request to yourself.'}, status=400)

        try:
            # Check if the user exists
            to_user = User.objects.get(username=username)

            # Check if the users are already connected
            if Connection.objects.filter(user=request.user, connected_user=to_user).exists() or \
               Connection.objects.filter(user=to_user, connected_user=request.user).exists():
                return JsonResponse({'error': 'You are already connected with this user.'}, status=400)

            # Check if the current user has already received a request from the target user
            if ConnectionRequest.objects.filter(from_user=to_user, to_user=request.user).exists():
                return JsonResponse({'error': f'You have already received a connection request from {username}.'}, status=400)

            # Check if the current user has already sent a request to the target user
            if ConnectionRequest.objects.filter(from_user=request.user, to_user=to_user).exists():
                return JsonResponse({'error': 'You have already sent a connection request to this user.'}, status=400)

            # Create a new connection request if no issues
            ConnectionRequest.objects.create(from_user=request.user, to_user=to_user)

            return JsonResponse({'success': True})
        
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

    return JsonResponse({'error': 'Invalid request.'}, status=400)



from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import ConnectionRequest, Connection, User
import json

@login_required(login_url='/')
def handle_connection_request(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        from_username = data.get('from_username')
        action = data.get('action')  # Either 'accept' or 'decline'

        try:
            # Get the user who sent the request
            from_user = User.objects.get(username=from_username)
            # Check if there is a pending connection request
            connection_request = ConnectionRequest.objects.get(from_user=from_user, to_user=request.user)

            if action == 'accept':
                # Add the connection and remove the request
                Connection.objects.create(user=request.user, connected_user=from_user)
                connection_request.delete()  # Remove from pending requests
                return JsonResponse({'success': True, 'message': 'Connection accepted.'})

            elif action == 'decline':
                # Remove the request without creating a connection
                connection_request.delete()
                return JsonResponse({'success': True, 'message': 'Connection request declined.'})

        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)
        except ConnectionRequest.DoesNotExist:
            return JsonResponse({'error': 'Connection request not found.'}, status=404)

    return JsonResponse({'error': 'Invalid request.'}, status=400)




import json
import uuid
from django.http import JsonResponse
from django.contrib.auth.models import User
from mcqs.models import MCQ  # Ensure your MCQ model is imported
from .models import Shared_Bookmark  # Ensure your Shared_Bookmark model is imported
@login_required(login_url='/')
def share_bookmark(request, bookmark_id):
    print(bookmark_id)
    if request.method == 'POST':
        try:
            # Validate if the bookmark_id is a valid UUID
            try:
                bookmark_id = uuid.UUID(bookmark_id)
            except ValueError:
                return JsonResponse({
                    'error': True,
                    'details': [{
                        'username': 'System',
                        'success': False,
                        'message': 'Invalid bookmark ID. It must be a valid UUID.'
                    }]
                }, status=400)

            # Parse the JSON data
            data = json.loads(request.body)
            user_ids = data.get('users', [])
            print(user_ids)
            
            sender = request.user

            # Check if MCQ exists
            try:
                mcq = MCQ.objects.get(uid=bookmark_id)
            except MCQ.DoesNotExist:
                return JsonResponse({
                    'error': True,
                    'details': [{
                        'username': 'System',
                        'success': False,
                        'message': 'MCQ not found'
                    }]
                }, status=404)

            # Store results for each user
            sharing_results = []

            # Process each user
            for user_id in user_ids:
                try:
                    recipient = User.objects.get(id=user_id)

                    # Check for existing shares
                    existing_shared = Shared_Bookmark.objects.filter(
                        mcq=mcq,
                        sender__in=[sender, recipient],
                        recipient__in=[sender, recipient]
                    ).first()

                    if existing_shared:
                        # Format existing share information
                        existing_share_time = existing_shared.shared_at.isoformat()  # Send as ISO format
                        sharing_results.append({
                            'username': recipient.username,
                            'success': False,
                            'message': 'Already shared',
                            'shared_at': existing_share_time  # Add the timestamp separately
                        })
                        continue

                    # Create new share
                    sb_uid = str(uuid.uuid4())
                    Shared_Bookmark.objects.create(
                        sb_uid=sb_uid,
                        mcq=mcq,
                        sender=sender,
                        recipient=recipient
                    )
                    
                    # Add success result
                    sharing_results.append({
                        'username': recipient.username,
                        'success': True,
                        'message': 'Successfully shared'
                    })

                except User.DoesNotExist:
                    sharing_results.append({
                        'username': f'User {user_id}',
                        'success': False,
                        'message': 'User not found'
                    })

            # Return all results
            return JsonResponse({
                'error': False,
                'details': sharing_results
            }, status=200)

        except json.JSONDecodeError:
            return JsonResponse({
                'error': True,
                'details': [{
                    'username': 'System',
                    'success': False,
                    'message': 'Invalid data format'
                }]
            }, status=400)
    else:
        return JsonResponse({
            'error': True,
            'details': [{
                'username': 'System',
                'success': False,
                'message': 'Invalid request method'
            }]
        }, status=405)



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from .models import Shared_Test, TestSession
from mcqs.models import TestSession
import json
@login_required(login_url='/')
@csrf_exempt  # For simplicity in development, but use CSRF tokens properly in production
def share_test(request, test_id):
    if request.method == 'POST':
        try:
            # Parse JSON data from the request
            data = json.loads(request.body)
            user_ids = data.get('users', [])
            
            if not user_ids:
                return JsonResponse({
                    'error': True,
                    'details': [{
                        'username': 'System',
                        'success': False,
                        'message': 'No users selected'
                    }]
                }, status=400)
            
            # Get the test session
            try:
                test_session = TestSession.objects.get(test_id=test_id)
            except TestSession.DoesNotExist:
                return JsonResponse({
                    'error': True,
                    'details': [{
                        'username': 'System',
                        'success': False,
                        'message': 'Test session not found'
                    }]
                }, status=404)
            
            # Get the sender
            sender = request.user
            
            # Store results for each user
            sharing_results = []
            
            # Process each user
            for user_id in user_ids:
                try:
                    recipient = User.objects.get(id=user_id)
                    
                    # Check if already shared
                    existing_share = Shared_Test.objects.filter(
                        test_session=test_session,
                        sender=sender,
                        recipient=recipient
                    ).first()
                    
                    if existing_share:
                        # Add to results with already shared status
                        existing_share_time = existing_share.shared_at.isoformat()  # Send as ISO format
                        sharing_results.append({
                            'username': recipient.username,
                            'success': False,
                            'message': 'Already shared',
                            'shared_at': existing_share_time  # Add the timestamp separately
                        })
                    else:
                        # Create new share
                        st_uid = str(uuid.uuid4())
                        Shared_Test.objects.create(
                            st_uid=st_uid,
                            test_session=test_session,
                            sender=sender,
                            recipient=recipient
                        )
                        
                        # Add success result
                        sharing_results.append({
                            'username': recipient.username,
                            'success': True,
                            'message': 'Successfully shared'
                        })
                        
                except User.DoesNotExist:
                    sharing_results.append({
                        'username': f'User {user_id}',
                        'success': False,
                        'message': 'User not found'
                    })
            
            # Return all results
            return JsonResponse({
                'error': False,
                'details': sharing_results
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({
                'error': True,
                'details': [{
                    'username': 'System',
                    'success': False,
                    'message': 'Invalid JSON data'
                }]
            }, status=400)
    
    return JsonResponse({
        'error': True,
        'details': [{
            'username': 'System',
            'success': False,
            'message': 'Invalid request method'
        }]
    }, status=405)

from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from itertools import chain
from operator import attrgetter
from .models import Shared_Bookmark, Shared_Test, Connection
from mcqs.models import MCQ
from mcqs.models import TestSession  # Assuming you have a TestSession model
@login_required(login_url='/')
def shared(request, userId):
    connected_user = get_object_or_404(User, id=userId)

    # Check if a connection exists
    connection_exists = Connection.objects.filter(
        Q(user=request.user, connected_user=connected_user) |
        Q(user=connected_user, connected_user=request.user)
    ).exists()

    if not connection_exists:
        return render(request, 'hive/error.html', {'message': 'You are not connected to this user.'})

    # Fetch shared MCQs
    shared_mcqs = Shared_Bookmark.objects.filter(
        Q(sender=request.user, recipient=connected_user) |
        Q(sender=connected_user, recipient=request.user)
    )

    # Fetch shared Test Sessions
    shared_tests = Shared_Test.objects.filter(
        Q(sender=request.user, recipient=connected_user) |
        Q(sender=connected_user, recipient=request.user)
    )

    # Combine and sort the shared items by 'shared_at'
    shared_items = sorted(
        chain(shared_mcqs, shared_tests),
        key=attrgetter('shared_at')
    )

    items = []
    for shared_item in shared_items:
        if isinstance(shared_item, Shared_Bookmark):
            # Fetch detailed MCQ data
            mcq = MCQ.objects.get(uid=shared_item.mcq.uid)
            items.append({
                'type': 'mcq',
                'data': {
                    'id': mcq.uid,
                    'text': mcq.text,
                    'image': mcq.image.url if mcq.image else None,
                    'options': [mcq.option_1, mcq.option_2, mcq.option_3, mcq.option_4],
                    'correct_option': mcq.correct_option,
                    'explanation': mcq.explanation,
                    'difficulty': mcq.difficulty.name if mcq.difficulty else 'N/A',
                    'type': mcq.types.types if mcq.types else 'N/A',
                    'hierarchy': f"{mcq.topic.chapter.unit.subject.name} > {mcq.topic.chapter.unit.name} > {mcq.topic.chapter.name} > {mcq.topic.name}",
                    'shared_by': 'me' if shared_item.sender == request.user else connected_user.username,
                    'shared_at': shared_item.shared_at
                }
            })
        elif isinstance(shared_item, Shared_Test):
            # Prepare test session data, only showing the test_id
            items.append({
                'type': 'test_session',
                'data': {
                    'test_id': shared_item.test_session.test_id,  # Show only test_id
                    'shared_by': 'me' if shared_item.sender == request.user else connected_user.username,
                    'shared_at': shared_item.shared_at,
                    'st_uid':shared_item.st_uid
                }
            })

    return render(request, 'hive/hive_share.html', {
        'connected_user': connected_user,
        'items': items
    })
from mcqs.models import TestSession,TestAnswer
from mcqs.serializers import MCQSerializer,MCQSubmitSerializer
from django.contrib import messages

@login_required(login_url='/')
def start_shared_test(request, test_id):
    stUid = request.GET.get('stUid')
    shared_test = get_object_or_404(Shared_Test, st_uid=stUid)

    if request.user == shared_test.sender:
        messages.error(request, "Sender cannot start the test.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
    # Check if user already has a current test
    profile = request.user.profile
    if profile.current_test:
        return redirect('cont', test_id=profile.current_test)
    
    if shared_test.started:
        messages.error(request, "This test has already been started.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    # Get the original test session
    original_test_session = get_object_or_404(TestSession, test_id=test_id)
    mode = original_test_session.mode if hasattr(original_test_session, 'mode') else 'test'
    # Get all MCQs from the original test answers
    original_answers = TestAnswer.objects.filter(test_session=original_test_session)
    mcq_uids = [answer.mcq_uid for answer in original_answers]
    mcqs = MCQ.objects.filter(uid__in=mcq_uids)
    
    if not mcqs:
        messages.error(request, "No MCQs found for this test.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
    
    # Create new test session for current user
    new_test_id = str(uuid.uuid4())
    new_test_session = TestSession.objects.create(
        user=request.user,
        test_id=new_test_id,
        total_questions=original_test_session.total_questions,
        selections=original_test_session.selections,
        totaltime=original_test_session.totaltime,
        mode = mode
    )
    
    # Create test answers for all MCQs
    for mcq_uid in mcq_uids:
        TestAnswer.objects.create(
            test_session=new_test_session,
            mcq_uid=mcq_uid
        )
    
    # Update user's current test
    profile.current_test = new_test_id
    profile.save()
    
    shared_test.started = True
    shared_test.save()
    shared_test.new_test = new_test_id
    shared_test.save()
    # Serialize MCQs for the template
    serializer = MCQSerializer(mcqs, many=True)
    total_time_minutes = original_test_session.totaltime / 60  # Convert seconds to minutes
    
    messages.success(request, "Starting shared test...")
    if mode=='test':
        return render(request, 'mcq/mcq.html', {
            'mcqs': json.dumps(serializer.data),
            'count': len(mcqs),
            'test_id': new_test_id,
            'total_time': total_time_minutes,
            'mode': mode
        })
    else:
        return render(request, 'mcq/mcq2.html', {
            'mcqs': json.dumps(serializer.data),
            'count': len(mcqs),
            'test_id': new_test_id,
            'total_time': total_time_minutes,
            'mode': mode
        })
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required

@login_required(login_url='/')
def test_session_details(request, test_id):
    try:
        # First get the Shared_Test by stUid
        st_uid = request.GET.get('stUid')
        if not st_uid:
            return JsonResponse({'error': 'stUid parameter is required'}, status=400)
        
        # Get the shared test by stUid
        shared_test = get_object_or_404(Shared_Test, st_uid=st_uid)
        print(shared_test)
        # Verify if the test_id matches
        if shared_test.test_session.test_id != test_id:
            return JsonResponse({'error': 'Invalid test ID for this shared test'}, status=400)
        
        # Check if user is either sender or recipient
        if request.user not in [shared_test.sender, shared_test.recipient]:
            raise PermissionDenied
        
        test_session = shared_test.test_session
        
        # Convert totaltime from seconds to minutes
        total_minutes = float(test_session.totaltime) / 60
        
        # Process selections
        selections_text = []
        if test_session.selections:
            # Handle selections as a list of strings
            if isinstance(test_session.selections, list):
                selections_text = test_session.selections
            else:
                # Handle any unexpected data structure
                raise ValueError("Invalid selections format")
        
        return JsonResponse({
            'total_questions': float(test_session.total_questions),
            'totaltime': round(total_minutes, 1),  # Round to 1 decimal place
            'mode': test_session.mode or 'test',
            'selections': selections_text
        })
        
    except Shared_Test.DoesNotExist:
        return JsonResponse({'error': 'Shared test not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
@login_required(login_url='/')
def shared_test_status(request, st_uid):
    try:
        print(st_uid)
        print("status mila")
        shared_test = get_object_or_404(Shared_Test, st_uid=st_uid)
        
        # Check if user is either sender or recipient
        if request.user not in [shared_test.sender, shared_test.recipient]:
            raise PermissionDenied
            
        return JsonResponse({
            'started': shared_test.started
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

@login_required(login_url='/')
def get_test_status(request, st_uid):
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        raise PermissionDenied
    
    # Get the shared test object
    shared_test = get_object_or_404(Shared_Test, st_uid=st_uid)
    
    # Check if user is either sender or recipient
    if request.user not in [shared_test.sender, shared_test.recipient]:
        raise PermissionDenied
    
    test_session = get_object_or_404(TestSession, test_id=shared_test.new_test)
    
    # Convert totaltime from seconds to minutes
    total_minutes = float(test_session.totaltime) / 60
    
    # Process selections
    selections_text = []
    if test_session.selections:
        try:
            if isinstance(test_session.selections, list):
                selections_text = test_session.selections
            else:
                selections_text = []  # Handle empty or invalid selections gracefully
        except Exception as e:
            selections_text = []
            print(f"Error processing selections: {e}")
    
    # Prepare response data
    response_data = {
        'total_questions': float(test_session.total_questions),
        'test_id': shared_test.new_test,
        'total_minutes': total_minutes,
        'selections': selections_text,
        'mode': test_session.mode or 'test',
        'is_submitted': test_session.submitted if hasattr(test_session, 'submitted') else False
    }
    
    return JsonResponse(response_data)

@login_required(login_url='/')
def continue_test(request, test_id):
    return redirect('cont', test_id=test_id)

    
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode
from accounts.models import Profile
from django.contrib.auth.models import User
@login_required(login_url='/')
def review_test(request,test_id):
   
    user = request.user
    profile = user.profile
    tkn = profile.email_token
    print(tkn)

    base_url = reverse('test_review', kwargs={'email_token': tkn})
    query_string = urlencode({'test_id': test_id})
    url = f'{base_url}?{query_string}'
    return redirect(url)