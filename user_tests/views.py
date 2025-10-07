from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import IntegrityError, transaction 
from django.http import HttpResponse

# IMPORTS
from app.models import QuestionPaper, Question 
from .models import TestRegistration, UserResponse 
from .forms import TestRegistrationForm


def user_register_view(request, link_id):
    """Handles test taker registration."""
    
    try:
        paper_id = int(link_id)
        # Check that the paper exists AND is public
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
    except (ValueError, QuestionPaper.DoesNotExist):
        messages.error(request, "The test link is invalid or deactivated.")
        return redirect("home") 


    registration_id = request.session.get("current_registration_id")
    if registration_id:
        try:
            # Check if registration exists and is NOT completed
            reg = TestRegistration.objects.get(pk=registration_id, question_paper=paper, is_completed=False)
            return redirect("test:user_instructions", link_id=link_id)
        except TestRegistration.DoesNotExist:
            pass # Agar complete ho gaya hai ya ID galat hai, toh aage register hone denge


    if request.method == "POST":
        form = TestRegistrationForm(request.POST) 
        if form.is_valid():
            try:
                registration = form.save(commit=False)
                registration.question_paper = paper
                registration.save()
                
                request.session["current_registration_id"] = registration.id
                request.session.modified = True 
                
                messages.success(request, "Registration successful. Please read instructions.")
                
                return redirect("test:user_instructions", link_id=link_id)
            
            except IntegrityError:
                # Already registered with this email for this paper
                messages.error(request, "You have already registered for this test with this email address.")
                return redirect("test:user_already_submitted") 

    else:
        form = TestRegistrationForm()
    
    context = {
        "form": form,
        "link_id": link_id,
        "paper_title": paper.title,
    }
    return render(request, "user_test/register.html", context)



def user_instruction_view(request, link_id):
    """Shows test details and instructions before starting."""
    
    try:
        paper_id = int(link_id)
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
    except (ValueError, QuestionPaper.DoesNotExist):
        return redirect("home")

    registration_id = request.session.get("current_registration_id")
    if not registration_id:
        return redirect("test:user_register_link", link_id=link_id)

    try:
        # Check if the registration exists and is NOT completed
        reg = TestRegistration.objects.get(pk=registration_id, question_paper=paper, is_completed=False)
    except TestRegistration.DoesNotExist:
        # Agar registration already complete ho gaya hai, toh final page par bhej do
        return redirect("test:user_already_submitted")

    # All checks passed
    return render(request, "user_test/instruction.html", {"link_id": link_id, "paper": paper})



def user_test_view(request, link_id):
    """
    Handles the actual test display (GET) and submission (POST).
    """
    # --- GET ACCESS CHECK ---
    try:
        paper_id = int(link_id)
        paper = get_object_or_404(QuestionPaper, pk=paper_id, is_public_active=True)
        registration_id = request.session.get("current_registration_id")
        
        if not registration_id:
            return redirect("test:user_register_link", link_id=link_id)
            
        # 1. Registration object fetch karein (no initial completion check)
        registration = get_object_or_404(TestRegistration, pk=registration_id, question_paper=paper) 

    except Exception:
        # Koi bhi access ya data error hone par register page par bhej de
        return redirect("test:user_register_link", link_id=link_id)
        
    # ----------------------------------------------------------------------
    # CRITICAL BACK PREVENTION CHECK
    # ----------------------------------------------------------------------
    if registration.is_completed:
        # Agar registration complete hai, toh turant final page par bhej do!
        return redirect("test:user_already_submitted")
    # ----------------------------------------------------------------------

    # --- POST SUBMISSION LOGIC ---
    if request.method == "POST":
        
        with transaction.atomic(): 
            
            # 1. User Responses ko save karein
            for key, value in request.POST.items():
                if key.startswith('question_'):
                    question_id = key.split('_')[1]
                    user_answer = value.strip()
                    
                    try:
                        question = Question.objects.get(pk=question_id)
                        
                        # UserResponse object create karein
                        UserResponse.objects.create(
                            registration=registration, 
                            question=question,         
                            user_answer=user_answer    
                        )
                    except Question.DoesNotExist:
                        continue
                        
            # 2. Test Registration ko COMPLETE mark karein
            registration.is_completed = True
            registration.save()
            
            # 3. Session clean up (important for back prevention)
            if "current_registration_id" in request.session:
                del request.session["current_registration_id"] 
                request.session.modified = True 

        return redirect("test:user_already_submitted")

    # --- GET LOGIC (Rendering Questions) ---
    
    questions = Question.objects.select_related('section').filter(
        section__question_paper=paper
    ).order_by('section__order', 'order')

    sections_with_questions = {}
    
    for q in questions:
        section_title = q.section.title
        
        if section_title not in sections_with_questions:
            sections_with_questions[section_title] = {'title': section_title, 'questions': []}
        
        options_list = q.options if isinstance(q.options, list) else None
        
        # Determine Question Type for rendering
        if options_list:
            q_type = 'MCQ'
        elif q.text and ('write a function' in q.text.lower() or 'code block' in q.text.lower()):
            q_type = 'CODE'
        else:
            q_type = 'SHORT_ANSWER'
            
        sections_with_questions[section_title]['questions'].append({
            'id': q.id,
            'text': q.text,
            'options': options_list,
            'type': q_type 
        })
    
    sections_list = list(sections_with_questions.values())

    context = {
        "paper": paper,
        "sections_list": sections_list, 
        "link_id": link_id,
        "total_duration": paper.duration * 60, 
    }
    return render(request, "user_test/test.html", context)


def user_already_submitted_view(request):
    """
    Shows the final 'Response Recorded' screen.
    (We are using this view name for the final screen).
    """
    # Template name is 'response_recorded.html' now
    return render(request, "user_test/already_submitted.html")