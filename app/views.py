# app/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import LoginForm,UserRegistrationForm,UserProfileRegistrationForm 

def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard') # Agar pehle se logged in hai to dashboard pe bhej do
        
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                # User mil gaya aur password sahi hai
                login(request, user)
                return redirect('dashboard')
            else:
                # Authentication fail
                form.add_error(None, "Invalid email or password.")
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form, 'title': 'Login'})

@login_required # Sirf logged in users hi access kar payenge
def dashboard(request):
    context = {
        'user': request.user,
        'title': 'User Dashboard',
        'content': 'Welcome to your secured dashboard!'
    }
    return render(request, 'dashboard.html', context)

def user_logout(request):
    logout(request)
    return redirect('login')


def user_register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        # Dono forms ko handle karein
        user_form = UserRegistrationForm(request.POST)
        profile_form = UserProfileRegistrationForm(request.POST)
        
        if user_form.is_valid() and profile_form.is_valid():
            # 1. Default User banao (Isse signal chalta hai aur Profile bhi ban jaati hai)
            user = user_form.save() 
            
            # 2. Profile details update karo
            profile = user.profile
            profile.phone_number = profile_form.cleaned_data['phone_number']
            profile.address = profile_form.cleaned_data['address']
            profile.save()
            
            # 3. User ko turant login kar do
            login(request, user)
            return redirect('dashboard')
        
    else:
        # GET request: Khaali forms dikhao
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()
        
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'title': 'User Registration'
    }
    return render(request, 'registration/register.html', context)
