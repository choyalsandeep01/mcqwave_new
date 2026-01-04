from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Profile, MedicalCollege
import json
import re

@csrf_exempt
@require_http_methods(["POST"])
def mobile_login(request):
    """Mobile app login API with robust error handling"""
    try:
        data = json.loads(request.body)
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password')
        
        # Validation
        if not username_or_email or not password:
            return JsonResponse({
                'success': False,
                'message': 'Username/email and password are required'
            }, status=400)
        
        # Determine if input is email or username
        is_email = '@' in username_or_email
        user_obj = None
        
        # Try to find user by email or username
        if is_email:
            try:
                user_obj = User.objects.get(email__iexact=username_or_email)
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'No account found with this email address'
                }, status=404)
        else:
            try:
                user_obj = User.objects.get(username__iexact=username_or_email)
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'No account found with this username'
                }, status=404)
        
        # Now authenticate with the found username
        authenticated_user = authenticate(username=user_obj.username, password=password)
        
        if authenticated_user:
            # Login the user to create session
            login(request, authenticated_user)
            
            return JsonResponse({
                'success': True,
                'message': 'Login successful',
                'user': {
                    'id': authenticated_user.id,
                    'username': authenticated_user.username,
                    'email': authenticated_user.email,
                    'first_name': authenticated_user.first_name,
                    'last_name': authenticated_user.last_name,
                    'uuid': str(authenticated_user.profile.email_token),
                    'email_token': str(authenticated_user.profile.email_token),
                }
            }, status=200)
        else:
            # User exists but password is wrong
            return JsonResponse({
                'success': False,
                'message': 'Incorrect password. Please try again.'
            }, status=401)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid request format'
        }, status=400)
    except Exception as e:
        print(f"Login error: {str(e)}")  # Log for debugging
        return JsonResponse({
            'success': False,
            'message': 'An error occurred during login. Please try again.'
        }, status=500)
@csrf_exempt
@require_http_methods(["POST"])
def mobile_signup(request):
    """Mobile app signup API"""
    try:
        data = json.loads(request.body)
        
        # Extract data
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        username = data.get('username', '').strip().lower()
        email = data.get('email', '').strip().lower()
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        medical_college_id = data.get('medical_college_id', '')
        other_college = data.get('other_college', '').strip()
        
        # Validation
        errors = {}
        
        if not first_name:
            errors['firstName'] = 'First name is required'
        elif len(first_name) < 2:
            errors['firstName'] = 'First name must be at least 2 characters'
            
        if not last_name:
            errors['lastName'] = 'Last name is required'
        elif len(last_name) < 2:
            errors['lastName'] = 'Last name must be at least 2 characters'
            
        if not username:
            errors['username'] = 'Username is required'
        elif not re.match(r'^[a-z0-9_]+$', username):
            errors['username'] = 'Username can only contain lowercase letters, numbers, and underscores'
        elif User.objects.filter(username=username).exists():
            errors['username'] = 'Username is already taken'
        
        if not email:
            errors['email'] = 'Email is required'
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors['email'] = 'Please enter a valid email address'
        elif User.objects.filter(email__iexact=email).exists():
            errors['email'] = 'Email is already registered'
        
        if not password:
            errors['password'] = 'Password is required'
        elif len(password) < 6:
            errors['password'] = 'Password must be at least 6 characters'
            
        if not confirm_password:
            errors['confirmPassword'] = 'Please confirm your password'
        elif password != confirm_password:
            errors['confirmPassword'] = 'Passwords do not match'
        
        # Return validation errors with 400 status code
        if errors:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors',
                'errors': errors
            }, status=400)
        
        # Create user
        user_obj = User.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            username=username
        )
        user_obj.set_password(password)
        user_obj.save()
        
        # Update medical college info
        if medical_college_id and medical_college_id != 'other':
            try:
                college = MedicalCollege.objects.get(id=medical_college_id)
                user_obj.profile.medical_college = college
            except MedicalCollege.DoesNotExist:
                pass
        elif other_college:
            user_obj.profile.other_medical_college = other_college
        
        user_obj.profile.save()
        
        # Return success with 201 status code
        return JsonResponse({
            'success': True,
            'message': 'Registration successful! Please login to continue.',
            'user': {
                'id': user_obj.id,
                'username': user_obj.username,
                'email': user_obj.email,
                'first_name': user_obj.first_name,
                'last_name': user_obj.last_name
            }
        }, status=201)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def mobile_medical_colleges(request):
    """Get medical colleges for mobile app"""
    try:
        colleges = MedicalCollege.objects.select_related('state').all().order_by('state__name', 'name')
        colleges_data = []
        
        for college in colleges:
            colleges_data.append({
                'id': college.id,
                'name': college.name,
                'location': college.location,
                'state': college.state.name if college.state else '',
                'full_name': f"{college.name}, {college.location}, {college.state.name if college.state else ''}"
            })
        
        return JsonResponse({
            'success': True,
            'colleges': colleges_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error fetching colleges: {str(e)}'
        })

@csrf_exempt
@require_http_methods(["GET"])
def mobile_app_stats(request):
    """Get app statistics for homepage"""
    try:
        # Import here to avoid circular imports
        from mcqs.models import MCQ
        
        total_mcqs = MCQ.objects.count()
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_mcqs': total_mcqs,
                'high_yield_mcqs': 15000,  # Your stated number
                'pyqs': 10000,  # Your stated number
                'exams': ['NEET PG', 'INICET', 'FMGE', 'UPSC CMS']
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error fetching stats: {str(e)}'
        })


from rest_framework.decorators import api_view
from rest_framework.response import Response
from accounts.models import AppVersion

@api_view(['GET'])
def check_app_version(request):
    """
    Check if the current app version is up to date
    """
    platform = request.GET.get('platform', 'android').lower()
    current_version = request.GET.get('current_version', '1.0.0')
    
    try:
        app_version = AppVersion.objects.get(platform=platform)
        
        # Check maintenance mode
        if app_version.is_maintenance:
            return Response({
                'success': True,
                'is_maintenance': True,
                'maintenance_message': app_version.maintenance_message,
                'force_update': False
            })
        
        # Compare versions using the compare_versions method
        comparison = AppVersion.compare_versions(
            app_version.current_version, 
            current_version
        )
        
        # If server version > current version
        needs_update = comparison > 0
        
        # Check if it's a force update
        min_comparison = AppVersion.compare_versions(
            current_version,
            app_version.minimum_version
        )
        force_update = min_comparison < 0 or app_version.force_update
        
        return Response({
            'success': True,
            'needs_update': needs_update,
            'force_update': force_update,
            'current_version': app_version.current_version,
            'minimum_version': app_version.minimum_version,
            'download_url': app_version.download_url,
            'update_message': app_version.update_message,
            'whats_new': app_version.whats_new,
            'is_maintenance': False
        })
        
    except AppVersion.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Version info not found'
        }, status=404)


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from accounts.models import Contact

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_contact_form(request):
    """
    Handle contact form submission from mobile app
    """
    try:
        # ? FIX: Use request.data directly (DRF handles JSON parsing)
        # Don't use request.body - it causes the error
        subject = request.data.get('subject')
        message = request.data.get('message')
        
        # Validation
        if not subject or subject not in ['technical', 'billing', 'account', 'other']:
            return Response({
                'success': False,
                'error': 'Please select a valid subject'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not message or not message.strip():
            return Response({
                'success': False,
                'error': 'Please enter a message'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if len(message.strip()) < 10:
            return Response({
                'success': False,
                'error': 'Message must be at least 10 characters long'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create contact entry
        contact = Contact.objects.create(
            user=request.user,
            name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
            email=request.user.email,
            subject=subject,
            message=message.strip()
        )
        
        # Optional: Send email notification to admin
        # send_contact_notification_email(contact)
        
        return Response({
            'success': True,
            'message': 'Your message has been sent successfully. We will respond shortly.',
            'contact_id': contact.id
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        print(f"? Contact form error: {str(e)}")  # For debugging
        return Response({
            'success': False,
            'error': 'An error occurred while submitting your request. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_contacts(request):
    """
    Get user's contact history
    """
    try:
        contacts = Contact.objects.filter(user=request.user).order_by('-created_at')[:10]
        
        contact_list = [{
            'id': contact.id,
            'subject': contact.get_subject_display(),
            'subject_value': contact.subject,
            'message': contact.message,
            'created_at': contact.created_at.isoformat(),
            'is_resolved': contact.is_resolved
        } for contact in contacts]
        
        return Response({
            'success': True,
            'contacts': contact_list,
            'count': len(contact_list)
        })
        
    except Exception as e:
        print(f"? Contact history error: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to fetch contact history'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

