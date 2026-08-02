from django.shortcuts import render

def index(request):
    return render(request, "trial/login.html")

def host_setup(request):
    return render(request, "trial/host_setup.html")

def join_waiting(request):
    return render(request, "trial/join_waiting.html")