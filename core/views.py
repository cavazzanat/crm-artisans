from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

@login_required
def dashboard(request):
    # Vue temporaire simple pour tester
    return HttpResponse("<h1>Bienvenue dans votre CRM Artisans !</h1><p>Utilisateur connecté: " + request.user.username + "</p>")