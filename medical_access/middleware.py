from django.shortcuts import render
from django.http import Http404
from django.conf import settings

class Custom404Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # If the response is a 404, render our custom 404 template
        if response.status_code == 404:
            try:
                return render(request, '404.html', status=404)
            except:
                # Fallback to default 404 if our template fails
                pass
        
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            try:
                return render(request, '404.html', status=404)
            except:
                # Fallback to default 404 if our template fails
                pass
        return None
