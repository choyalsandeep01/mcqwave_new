# import imp
# from django.conf import settings
# from django.core.mail import send_mail
# import smtplib



# def send_account_activation_email(email , email_token):

#     message = f'Hi, click on the link to activate your account http://51.20.4.28/accounts/activate/{email_token}'
    





#     smtp_server = 'smtp.gmail.com'
#     port = 587  # For starttls
#     sender_email = 'travelphoto85@gmail.com'
#     password = 'dtlxsqpoacwhmbzw'
#     receiver_email = email
#     message = message

#     try:
#         server = smtplib.SMTP(smtp_server, port)
#         server.ehlo()  # Can be omitted
#         server.starttls()  # Secure the connection
#         server.ehlo()  # Can be omitted
#         server.login(sender_email, password)
#         server.sendmail(sender_email, receiver_email, message)
#         server.close()
#         print("Email sent successfully")
#         print(message)
#     except Exception as e:
#         print(f"Error: {e}")


from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_account_activation_email(email, email_token):
    try:
        # Email content
        subject = "Account Activation"
        
        # Create HTML content
        html_message = render_to_string('email/activation_email.html', {
            'activation_link': f"https://mcqwave.com/accounts/activate/{email_token}",
        })
        
        # Create plain text content
        plain_message = strip_tags(html_message)
        
        # Send email using Django's send_mail
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL, 
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        
        print("Email sent successfully")
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False