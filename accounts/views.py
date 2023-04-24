from django.shortcuts import render

def login(request):
    return render(request, 'accounts/login.html')
