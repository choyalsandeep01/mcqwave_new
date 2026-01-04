from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

def send_payment_success_email(user, transaction, subscription):
    """Send payment success email to user"""
    subject = f'Payment Successful - {transaction.plan.name} Activated'
    
    html_content = render_to_string('payments/emails/payment_success.html', {
        'user': user,
        'transaction': transaction,
        'subscription': subscription,
        'site_name': 'MCQwave'
    })
    
    text_content = strip_tags(html_content)
    
    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False
        )
        return True
    except Exception as e:
        print(f"Error sending payment success email: {e}")
        return False

def send_payment_failure_email(user, transaction):
    """Send payment failure email to user"""
    subject = 'Payment Failed - MCQwave'
    
    html_content = render_to_string('payments/emails/payment_failure.html', {
        'user': user,
        'transaction': transaction,
        'site_name': 'MCQwave'
    })
    
    text_content = strip_tags(html_content)
    
    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False
        )
        return True
    except Exception as e:
        print(f"Error sending payment failure email: {e}")
        return False

def send_subscription_expiry_reminder(user, subscription):
    """Send subscription expiry reminder email"""
    subject = 'Subscription Expiring Soon - MCQwave'
    
    html_content = render_to_string('payments/emails/subscription_reminder.html', {
        'user': user,
        'subscription': subscription,
        'site_name': 'MCQwave'
    })
    
    text_content = strip_tags(html_content)
    
    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False
        )
        return True
    except Exception as e:
        print(f"Error sending subscription reminder email: {e}")
        return False