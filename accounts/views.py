from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect,HttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate , login , logout
from .models import Profile,MedicalCollege
from django.urls import reverse
import re
from base.email import send_account_activation_email
import re
import json
from django.shortcuts import redirect, render
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

@require_http_methods(["GET", "POST"])
def sign_up(request):
    if request.user.is_authenticated:
        user_uuid = request.user.profile.email_token
        return redirect(reverse('go_to_home', kwargs={'uuid': user_uuid}))
    
    medical_colleges = MedicalCollege.objects.select_related('state').all().order_by('state__name', 'name')


    if request.method == 'POST':
        # Check if it's an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        username = request.POST.get('username', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        conf_password = request.POST.get('confirm_password')
        
        medical_college_id = request.POST.get('medical_college', '')
        other_college = request.POST.get('other_college', '').strip().capitalize()

        errors = {}

        if medical_college_id == 'other' and other_college:
            # Just store the city name as specified
            city_name = other_college
        # Validate required fields
        if not all([first_name, last_name, username, email, password, conf_password]):
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': {
                    'first_name': '' if first_name else 'First name is required',
                    'last_name': '' if last_name else 'Last name is required',
                    'username': '' if username else 'Username is required',
                    'email': '' if email else 'Email is required',
                    'password': '' if password else 'Password is required',
                    'confirm_password': '' if conf_password else 'Please confirm your password'
                }
            }) if is_ajax else HttpResponseRedirect(request.path_info)
        
        # Username validation
        if not re.match(r'^[a-z0-9]+$', username):
            errors['username'] = 'Username can only contain lowercase letters and numbers, without spaces or special characters.'
        
        # Email validation
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors['email'] = 'Please enter a valid email address.'
        
        # Check if username exists
        if User.objects.filter(username=username).exists():
            errors['username'] = 'Username is already taken.'
        
        # Check if email exists
        if User.objects.filter(email=email).exists():
            errors['email'] = 'Email is already taken.'
        
        # Check password match
        if password != conf_password:
            errors['confirm_password'] = 'Passwords do not match.'
        
        # If there are any errors, return them
        if errors:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors below.',
                'errors': errors
            }) if is_ajax else HttpResponseRedirect(request.path_info)
        
        try:
            # Create user
            user_obj = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                username=username
            )
            user_obj.set_password(password)
            user_obj.save()
            if medical_college_id:
                if medical_college_id != 'other':
                    try:
                        college = MedicalCollege.objects.get(id=medical_college_id)
                        user_obj.profile.medical_college = college
                    except MedicalCollege.DoesNotExist:
                        pass
                elif other_college:
                    # For "other" option, just store the city name in a field
                    # You may need to add this field to your Profile model
                    user_obj.profile.other_medical_college = other_college
                
                user_obj.profile.save()
            success_message = 'Registration completed. Log in now!'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('login')
                })
            else:
                messages.success(request, 'Registration completed successfully!')
                return render(request, 'accounts/signup.html', {'medical_colleges': medical_colleges})
                
        except Exception as e:
            error_message = 'An error occurred during registration. Please try again.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })
            else:
                messages.error(request, error_message)
                return HttpResponseRedirect(request.path_info)
    
    # GET request
    return render(request, 'accounts/signup.html',{'medical_colleges': medical_colleges})


from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.urls import reverse
from django.db.models import Q

def log_in(request):
    if request.user.is_authenticated:
        user_uuid = request.user.profile.email_token
        return redirect(reverse('go_to_home', kwargs={'uuid': user_uuid}))
        
    if request.method == 'POST':
        # Get username/email and normalize it
        username_or_email = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password')
        
        # Check if AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Determine if input is email or username
        is_email = '@' in username_or_email
        
        # Check if user exists
        if is_email:
            user_exists = User.objects.filter(email__iexact=username_or_email).exists()
        else:
            user_exists = User.objects.filter(username__iexact=username_or_email).exists()
            
        if not user_exists:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No account found with these credentials'
                })
            return render(request, 'accounts/login.html', {'error': 'No account found with these credentials'})
        
        # Get the actual username if email was provided
        if is_email:
            try:
                username = User.objects.get(email__iexact=username_or_email).username
            except User.DoesNotExist:
                # This shouldn't happen due to the earlier check, but just in case
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': 'User not found'
                    })
                return render(request, 'accounts/login.html', {'error': 'User not found'})
        else:
            username = username_or_email
            
        # Attempt authentication with the username
        user_obj = authenticate(username=username, password=password)
        
        if user_obj:
            login(request, user_obj)
            user_uuid = user_obj.profile.email_token
            redirect_url = reverse('go_to_home', kwargs={'uuid': user_uuid})
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'redirect_url': redirect_url
                })
            return redirect(redirect_url)
        
        # Invalid password
        if is_ajax:
            return JsonResponse({
                'success': False,
                'message': 'Incorrect password'
            })
        return render(request, 'accounts/login.html', {'error': 'Incorrect password'})
    
    return render(request, 'accounts/login.html')


def activate_email(request , email_token):
    try:
        user = Profile.objects.get(email_token= email_token)
        user.is_email_verified = True
        user.save()
        messages.warning(request, 'Your account is verified.')

        return redirect('login')
    except Exception as e:
        return HttpResponse('Invalid Email token')


import uuid
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Profile
from django.core.mail import send_mail
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str

def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        user = User.objects.filter(email=email).first()

        if user:
            # Generate a unique token
            token = str(uuid.uuid4())
            profile = user.profile
            profile.reset_token = token
            profile.save()
            usernme= user.username
            # Send reset email
            reset_link = request.build_absolute_uri(reverse('password_reset_confirm', args=[token]))
            send_mail(
                'Password Reset Request',
                f'Click the link to reset your password: {reset_link} for username: {usernme}',
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, 'A password reset link has been sent to your email.')
            return redirect('login')
        else:
            messages.error(request, 'No account found with that email.')

    return render(request, 'accounts/password_reset_request.html')

def password_reset_confirm(request, token):
    profile = Profile.objects.filter(reset_token=token).first()

    if not profile:
        messages.error(request, 'Invalid or expired reset token.')
        return redirect('password_reset_request')

    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if new_password == confirm_password:
            user = profile.user
            user.set_password(new_password)
            user.save()
            profile.reset_token = None  # Invalidate the token
            profile.save()
            messages.success(request, 'Password reset successfully. You can now log in.')
            return redirect('login')
        else:
            messages.error(request, 'Passwords do not match.')

    return render(request, 'accounts/password_reset_confirm.html', {'token': token})

from django.shortcuts import redirect, render
from django.contrib import messages
from .models import Profile
from django.core.exceptions import ObjectDoesNotExist
import uuid

def resend_email(request):
    if request.method == "POST":
        email = request.POST.get('email')
        
        try:
            # Check if the email exists
            user = User.objects.get(email=email)
            profile = user.profile
            
            # Check if the email is already verified
            if profile.is_email_verified:
                messages.error(request, "This email is already verified. You can log in.")
                return redirect('resend_email')

            # Generate a new token
            new_token = str(uuid.uuid4())
            profile.email_token = new_token
            profile.save()

            # Resend the activation email
            send_account_activation_email(email, new_token)
            
            messages.success(request, "A new verification email has been sent.")
            return redirect('resend_email')
        except ObjectDoesNotExist:
            messages.error(request, "No account found with this email address.")
            return redirect('resend_email')

    return render(request, 'accounts/resend_email.html')

# views.py (your landing view)
from django.shortcuts import render, redirect
from django.urls import reverse
from accounts.models import AppVersion


def landing(request):
    if request.user.is_authenticated:
        user_uuid = request.user.profile.email_token
        return redirect(reverse('go_to_home', kwargs={'uuid': user_uuid}))
    
    # Get Android app version info
    try:
        android_version = AppVersion.objects.get(platform='android')
    except AppVersion.DoesNotExist:
        android_version = None
    
    context = {
        'android_version': android_version,
    }
    
    return render(request, 'home/landing.html', context)
        
from django.http import JsonResponse
from django.db.models import Count
from mcqs.models import MCQ, mcq_types

def get_mcq_stats(request):
    try:
        # Get total count of MCQs
        total_mcqs = MCQ.objects.count()
        
        # Get count of Clinical type MCQs
        # Assuming there's a type named "Clinical" in mcq_types
        clinical_type = mcq_types.objects.filter(types__iexact='Clinical').first()
        clinical_mcqs = MCQ.objects.filter(types=clinical_type).count() if clinical_type else 0
        response_data = {
            'totalMCQs': total_mcqs,
            'clinicalMCQs': clinical_mcqs,
            
            
        }
        
        return JsonResponse(response_data)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Feedback,Contact

@login_required
@require_http_methods(["POST"])
def submit_feedback(request):
    try:
        feedback = Feedback.objects.create(
            user=request.user,
            category=request.POST.get('category'),
            rating=request.POST.get('rating'),
            message=request.POST.get('message'),
        )
        return JsonResponse({
            'status': 'success',
            'message': 'Thank you for your feedback!'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


@require_http_methods(["POST"])
def submit_feedback(request):
    try:
        feedback = Feedback.objects.create(
            user=request.user,
            category=request.POST.get('category'),
            rating=request.POST.get('rating'),
            message=request.POST.get('message'),
        )
        return JsonResponse({
            'status': 'success',
            'message': 'Thank you for your feedback!'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@require_http_methods(["POST"])
def contact_submit(request):
    print("Hiiii - request received")  # Debugging message
    
    try:
        print("Request Body:", request.body)  # Log request body
        data = json.loads(request.body)

        subject = data.get('subject')
        message = data.get('message')

        if not subject or not message:
            return JsonResponse({'status': 'error', 'message': 'Subject and message are required'}, status=400)

        contact = Contact(subject=subject, message=message)

        if request.user.is_authenticated:
            contact.user = request.user
            contact.name = request.user.username
            contact.email = request.user.email
        else:
            name = data.get('name')
            email = data.get('email')
            if not name or not email:
                return JsonResponse({'status': 'error', 'message': 'Name and email are required for non-logged-in users'}, status=400)
            contact.name = name
            contact.email = email

        contact.save()
        print("Contact saved successfully!")  # Debugging check

        return JsonResponse({'status': 'success', 'message': 'Your message has been sent successfully!'})

    except json.JSONDecodeError:
        print("Error: Invalid JSON received")  # Debugging check
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)

    except Exception as e:
        print(f"Unexpected error: {e}")  # Debugging check
        return JsonResponse({'status': 'error', 'message': f'Error: {str(e)}'}, status=500)

        
def profile_settings(request):
    """
    Render the profile settings page
    """
    return render(request, 'accounts/setting.html')

def medical_colleges_api(request):
    """API endpoint to get all medical colleges"""
    print("medical college list")
    colleges = MedicalCollege.objects.all().values('id', 'name', 'location', 'state__name')
    colleges_list = []
    
    for college in colleges:
        colleges_list.append({
            'id': college['id'],
            'name': college['name'],
            'location': college['location'],
            'state': college['state__name']
        })
        
    return JsonResponse(colleges_list, safe=False)

@login_required
def update_medical_college(request):
    """View to update user's medical college"""

    if request.method == 'POST':
        try:
            profile = request.user.profile
            
            # Get form data
            medical_college_id = request.POST.get('medical_college_id', '')
            other_medical_college = request.POST.get('other_city', '').strip().capitalize()
            
            # Update profile
            if medical_college_id:
                profile.medical_college_id = medical_college_id
                profile.other_medical_college = ''
            else:
                profile.medical_college = None
                profile.other_medical_college = other_medical_college
                
            profile.save()
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def mobile_verification_view(request):
    """Main view for mobile verification card"""
    profile = request.user.profile  # Using your existing profile relationship
    
    context = {
        'profile': profile,
        'user': request.user
    }
    return render(request, 'accounts/mobile_verification.html', context)

@csrf_exempt
@require_POST
@login_required
def send_otp(request):
    """Send OTP to mobile number"""
    try:
        data = json.loads(request.body)
        mobile_number = data.get('mobile_number', '').strip()
        
        # Validate mobile number format (Indian mobile number format)
        if not re.match(r'^(\+91|91)?[6-9]\d{9}$', mobile_number):
            return JsonResponse({
                'success': False, 
                'message': 'Please enter a valid Indian mobile number (10 digits starting with 6-9)'
            })
        
        # Normalize mobile number
        if mobile_number.startswith('+91'):
            mobile_number = mobile_number[3:]
        elif mobile_number.startswith('91'):
            mobile_number = mobile_number[2:]
        
        # Delete any existing OTP for this user
        OTPVerification.objects.filter(user=request.user).delete()
        
        # Create new OTP
        otp_obj = OTPVerification.objects.create(
            user=request.user,
            mobile_number=mobile_number
        )
        
        # In a real application, you would integrate with SMS gateway like:
        # - MSG91, TextLocal, Twilio, AWS SNS, etc.
        # For demo purposes, we'll just log the OTP
        print(f"OTP for +91{mobile_number}: {otp_obj.otp_code}")
        
        return JsonResponse({
            'success': True, 
            'message': f'OTP sent to +91{mobile_number}',
            'otp_for_demo': otp_obj.otp_code  # Remove this in production
        })
        
    except Exception as e:
        print(f"Error sending OTP: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'Failed to send OTP. Please try again.'
        })

@csrf_exempt
@require_POST
@login_required
def verify_otp(request):
    """Verify OTP and update mobile number"""
    try:
        data = json.loads(request.body)
        otp_code = data.get('otp_code', '').strip()
        
        if not otp_code:
            return JsonResponse({
                'success': False, 
                'message': 'Please enter OTP code'
            })
        
        # Get the latest OTP for this user
        try:
            otp_obj = OTPVerification.objects.filter(
                user=request.user, 
                is_verified=False
            ).latest('created_at')
        except OTPVerification.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'message': 'No OTP found. Please request a new one.'
            })
        
        # Check if OTP is expired
        if otp_obj.is_expired():
            return JsonResponse({
                'success': False, 
                'message': 'OTP has expired. Please request a new one.'
            })
        
        # Verify OTP
        if otp_obj.otp_code != otp_code:
            return JsonResponse({
                'success': False, 
                'message': 'Invalid OTP code. Please try again.'
            })
        
        # Mark OTP as verified
        otp_obj.is_verified = True
        otp_obj.save()
        
        # Update user profile (using your existing Profile model)
        profile = request.user.profile
        profile.mobile_number = f"+91{otp_obj.mobile_number}"
        profile.is_mobile_verified = True
        profile.save()
        
        return JsonResponse({
            'success': True, 
            'message': 'Mobile number verified successfully!',
            'mobile_number': profile.mobile_number
        })
        
    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'Verification failed. Please try again.'
        })

@csrf_exempt
@require_POST
@login_required
def remove_mobile(request):
    """Remove mobile number from profile"""
    try:
        profile = request.user.profile
        profile.mobile_number = None
        profile.is_mobile_verified = False
        profile.save()
        
        # Delete any pending OTPs
        OTPVerification.objects.filter(user=request.user).delete()
        
        return JsonResponse({
            'success': True, 
            'message': 'Mobile number removed successfully!'
        })
        
    except Exception as e:
        print(f"Error removing mobile: {e}")
        return JsonResponse({
            'success': False, 
            'message': 'Failed to remove mobile number. Please try again.'
        })
