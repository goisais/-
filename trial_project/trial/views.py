from django.shortcuts import render

def index(request):
    return render(request, '.html')

# Create your views here.
