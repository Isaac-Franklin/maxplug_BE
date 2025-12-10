from django.shortcuts import redirect
from django.http import HttpResponseRedirect


ALLOWED_IPS = ['105.113.33.186', '127.0.0.1']
REDIRECT_URL = 'https://maxplug.com/'  

class RestrictAdminByIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = request.META.get('REMOTE_ADDR')

        if request.path.startswith('/admin/') and ip not in ALLOWED_IPS:
            # return redirect(REDIRECT_URL)
            return HttpResponseRedirect(REDIRECT_URL)


        return self.get_response(request)