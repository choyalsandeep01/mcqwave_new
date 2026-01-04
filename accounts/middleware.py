# Create a file called middleware.py in your app directory
from .models import VisitorCount

class VisitorCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process the request before the view is called
        current_path = request.path
        
        # Optionally filter out certain paths like static files
        if not current_path.startswith('/static/') and not current_path.startswith('/media/'):
            VisitorCount.increment(current_path)
            
            # Also increment the total count by counting the root path as total
            VisitorCount.increment('/')
            
        response = self.get_response(request)
        return response