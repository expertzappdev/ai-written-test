# user_tests/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import IntegrityError # DB error handling ke liye
from django.http import HttpResponse

# IMPORTS FROM OTHER APPS/FILES
# QuestionPaper model ko 'app' se import karna hoga
from app.models import QuestionPaper, Question 
# TestRegistration model is new app mein hoga, lekin forms aur baki models ko theek karna hoga
from .models import TestRegistration # TestRegistration isi app mein hai

# ASSUMPTION: Aapne TestRegistrationForm ko bhi 'user_tests' app mein move kar diya hoga ya bana diya hoga
# Ab TestRegistrationForm ko is app mein import karein
# from .forms import TestRegistrationForm 
# Agar forms ko separate app 'user_tests' mein nahi banaya hai, toh uska path theek karein (e.g., from app.forms import TestRegistrationForm)

# Main man raha hu ki aapne TestRegistrationForm ko bhi is app mein bana liya hai ya uska import theek kar diya hai.
# Agar form app/forms.py mein hai toh:
# from app.forms import TestRegistrationForm

# --- USER TEST FLOW VIEWS (MOVED HERE) ---

def user_instruction_view(request, link_id):
    # NOTE: Ab yeh view TestRegistration model use karega.
    
    # 1. Paper check (Error handling ke liye)
    try:
        paper_id = int(link_id)
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public=True)
    except (ValueError, QuestionPaper.DoesNotExist):
        return redirect("home")

    # 2. Registration check
    registration_id = request.session.get("current_registration_id")
    if not registration_id:
        return redirect("user_register_link", link_id=link_id)

    try:
        # Check if the registration exists and is for this paper
        reg = TestRegistration.objects.get(pk=registration_id, question_paper=paper, is_completed=False)
    except TestRegistration.DoesNotExist:
        # Agar registration ID galat hai, ya test complete ho gaya hai
        return redirect("user_register_link", link_id=link_id)

    # All checks passed, render instructions
    return render(request, "user_test/instruction.html", {"link_id": link_id, "paper": paper})


def user_test_view(request, link_id):
    """
    Step 3: Actual test-taking page.
    """
    # NOTE: Is view ko bhi TestRegistration aur QuestionPaper ki zarurat hogi.

    # 1. Paper and Registration check (Repeat logic from instruction view for safety)
    try:
        paper_id = int(link_id)
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public=True)
        registration_id = request.session.get("current_registration_id")
        
        if not registration_id:
            return redirect("user_register_link", link_id=link_id)
            
        registration = get_object_or_404(TestRegistration, pk=registration_id, question_paper=paper, is_completed=False)

    except Exception:
        return redirect("user_register_link", link_id=link_id)

    if request.method == "POST":
        # Handle test submission (Yahan aapko answers save karne ka logic likhna hai)
        # TODO: Save user answers and mark registration as completed
        registration.is_completed = True
        registration.save()
        
        # Session se registration ID hata dein, taki user dobara register na ho sake
        del request.session["current_registration_id"] 
        request.session.modified = True 

        return redirect("user_already_submitted")

    # Fetch questions for this paper
    questions = Question.objects.filter(section__question_paper=paper).order_by('section__order', 'order')

    return render(request, "user_test/test.html", {"questions": questions, "paper": paper, "link_id": link_id})


def user_already_submitted_view(request):
    """
    Step 4: Shown when user has already submitted the test.
    """
    return render(request, "user_test/already_submitted.html")


# Final aur complete user_register_view
def user_register_view(request, link_id):
    """
    Handles registration for test takers using the unique link_id (QuestionPaper PK).
    Checks for repetition using the TestRegistration model's unique_together constraint.
    """
    
    # 1. Question Paper ID ko fetch aur validate karna
    try:
        # link_id QuestionPaper's primary key (ID) hai.
        paper_id = int(link_id)
        # Check that the paper exists AND is public
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public=True)
    except (ValueError, QuestionPaper.DoesNotExist):
        messages.error(request, "The test link is invalid or deactivated.")
        return redirect("home") 


    # 2. Session check: Agar candidate already registered hai toh seedha instructions par bhej dein
    registration_id = request.session.get("current_registration_id")
    if registration_id:
        try:
            # Agar session ID is paper ke liye hai aur test complete nahi hua hai
            reg = TestRegistration.objects.get(pk=registration_id, question_paper=paper, is_completed=False)
            return redirect("user_instructions", link_id=link_id)
        except TestRegistration.DoesNotExist:
            pass


    if request.method == "POST":
        # 3. Form handling aur database mein save
        # Yahan aapko yeh assume karna hoga ki TestRegistrationForm import ho gaya hai
        form = TestRegistrationForm(request.POST) 
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                registration.question_paper = paper
                registration.save()
                
                request.session["current_registration_id"] = registration.id
                request.session.modified = True 
                
                messages.success(request, "Registration successful. Please read the instructions carefully.")
                
                return redirect("user_instructions", link_id=link_id)
            
            except IntegrityError:
                # unique_together constraint fail hua (Email + Paper ID already exists).
                messages.error(request, "You have already registered for this test with this email address.")
                return redirect("user_already_submitted") 

    else:
        # GET Request: Initial form render
        form = TestRegistrationForm()
    
    context = {
        "form": form,
        "link_id": link_id,
        "paper_title": paper.title,
    }
    return render(request, "user_test/register.html", context)