import os
import sys
import django
from datetime import datetime

# Add the project directory to the Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_dir)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')  # Change 'mcqwave2' to your project name if different
django.setup()

# Import Django models after setting up Django
from django.contrib.auth.models import User

def export_users_to_txt():
    """
    Exports all registered users to a text file sorted by join date (newest first).
    The file is saved as 'user_registrations.txt' in the current directory.
    """
    try:
        # Get all users ordered by date joined (newest first)
        users = User.objects.all().order_by('-date_joined')
        
        # Create or open the file in write mode
        with open('user_registrations.txt', 'w') as file:
            # Write header
            file.write("USER REGISTRATION REPORT\n")
            file.write("Generated on: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            file.write("-" * 80 + "\n\n")
            
            # Write user information
            for index, user in enumerate(users, 1):
                # Get additional profile information
                profile = user.profile if hasattr(user, 'profile') else None
                email_verified = "Yes" if profile and profile.is_email_verified else "No"
                
                # Format user details
                user_info = [
                    f"User #{index}",
                    f"Username: {user.username}",
                    f"Email: {user.email}",
                    f"Full Name: {user.get_full_name() or 'Not provided'}",
                    f"Date Joined: {user.date_joined.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Last Login: {user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never'}",
                    f"Email Verified: {email_verified}",
                    f"Active Status: {'Active' if user.is_active else 'Inactive'}",
                ]
                
                # Write user details to file
                file.write("\n".join(user_info))
                file.write("\n" + "-" * 40 + "\n")
        
        print(f"Successfully exported {users.count()} users to user_registrations.txt")
        
    except Exception as e:
        print(f"Error exporting users: {str(e)}")

if __name__ == "__main__":
    export_users_to_txt()