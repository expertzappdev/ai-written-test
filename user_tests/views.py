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
from .forms import TestRegistrationForm

# --- USER TEST FLOW VIEWS (MOVED HERE) ---

def user_instruction_view(request, link_id):
    # NOTE: Ab yeh view TestRegistration model use karega.
    
    # 1. Paper check (Error handling ke liye)
    try:
        paper_id = int(link_id)
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
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
    Step 3: Actual test-taking page. Fetches paper details and questions.
    """
    # 1. Paper and Registration check
    try:
        paper_id = int(link_id)
        # 1.1 Paper existence and public status check
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
        registration_id = request.session.get("current_registration_id")
        
        # 1.2 Session check: Agar session nahi hai toh register page par bhej de
        if not registration_id:
            return redirect("test:user_register_link", link_id=link_id)
            
        # 1.3 Registration status check: Check karein ki user ne abhi tak submit nahi kiya hai
        registration = get_object_or_404(TestRegistration, pk=registration_id, question_paper=paper, is_completed=False)

    except Exception:
        # Koi bhi error hone par register page par bhej de
        return redirect("test:user_register_link", link_id=link_id)

    # ----------------------------------------------------------------------
    # --- DATA FETCHING AND GROUPING LOGIC ---
    # ----------------------------------------------------------------------
    
    # 2. Questions aur unke sections ko ek hi query mein fetch karein
    questions = Question.objects.select_related('section').filter(
        section__question_paper=paper
    ).order_by('section__order', 'order')

    # 3. Questions ko sections mein group karne ke liye dictionary use karein
    sections_with_questions = {}
    
    for q in questions:
        # Section title ko group key banaayein
        section_title = q.section.title
        
        if section_title not in sections_with_questions:
            sections_with_questions[section_title] = {
                'title': section_title,
                'questions': []
            }
        
        # Options ko check karein ki woh list/JSON field mein hain ya nahi
        # isse template mein options display karna aasan ho jaata hai
        options_list = q.options if isinstance(q.options, list) else None
        
        sections_with_questions[section_title]['questions'].append({
            'id': q.id,
            'text': q.text,
            'options': options_list # Options ko template mein bheja
        })
    
    # Dictionary values (sections) ko list mein badle
    sections_list = list(sections_with_questions.values())

    # ----------------------------------------------------------------------
    # --- POST SUBMISSION LOGIC ---
    # ----------------------------------------------------------------------
    
    if request.method == "POST":
        # Handle test submission 
        # TODO: Yahan answers ko save karne ka complex logic aayega
        
        # Temp: Registration complete mark karein
        registration.is_completed = True
        registration.save()
        
        # Session clean up
        del request.session["current_registration_id"] 
        request.session.modified = True 

        return redirect("test:user_already_submitted")

    # ----------------------------------------------------------------------
    # --- GET (RENDER PAGE) LOGIC ---
    # ----------------------------------------------------------------------
    
    # Context mein saara zaroori data bhejein
    context = {
        "paper": paper, # Title, Duration (paper.duration), etc. ismein hai
        "sections_list": sections_list, # Grouped Questions aur options
        "link_id": link_id,
        "total_duration": paper.duration * 60, # Timer ke liye minutes ko seconds mein badle
    }
    return render(request, "user_test/test.html", context)

def user_already_submitted_view(request):
    """
    Step 4: Shown when user has already submitted the test.
    """
    return render(request, "user_test/already_submitted.html")

# user_tests/views.py (user_register_view)

def user_register_view(request, link_id):
    
    # 1. Question Paper ID ko fetch aur validate karna
    try:
        paper_id = int(link_id)
        # Check that the paper exists AND is public
        # Agar yeh line fail hoti hai, toh yeh exception catch ho jaega.
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
    except (ValueError, QuestionPaper.DoesNotExist):
        # Is block mein koi issue nahi hai, yeh sahi se 404 ya redirect handle karta hai.
        messages.error(request, "The test link is invalid or deactivated.")
        return redirect("home") 


    # 2. Session check: Agar candidate already registered hai toh seedha instructions par bhej dein
    registration_id = request.session.get("current_registration_id")
    if registration_id:
        try:
            reg = TestRegistration.objects.get(pk=registration_id, question_paper=paper, is_completed=False)
            return redirect("test:user_instructions", link_id=link_id)
        except TestRegistration.DoesNotExist:
            pass


    if request.method == "POST":
        # 3. Form handling aur database mein save
        form = TestRegistrationForm(request.POST) 
        if form.is_valid():
            try:
                # ... (Database saving logic) ...
                registration = form.save(commit=False)
                registration.question_paper = paper
                registration.save()
                
                request.session["current_registration_id"] = registration.id
                request.session.modified = True 
                
                messages.success(request, "Registration successful...")
                
                # Naye, sahi namespace ke saath redirect karein
                return redirect("test:user_instructions", link_id=link_id)
            
            except IntegrityError:
                messages.error(request, "You have already registered...")
                return redirect("test:user_already_submitted") 
        # else: Agar form invalid hai, toh woh neeche context ke saath render ho jaega.

    else:
        # GET Request: Initial form render
        form = TestRegistrationForm()
    
    # **Yahan, agar form invalid hua (POST request), toh yeh context use hoga.**
    context = {
        "form": form,
        "link_id": link_id,
        "paper_title": paper.title,
    }
    return render(request, "user_test/register.html", context)