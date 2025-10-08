# app/views.py

import json
import google.generativeai as genai
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import login, logout
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Count
from django.conf import settings
from .forms import QuestionPaperEditForm
from .models import Skill
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

from django.shortcuts import get_object_or_404, render, redirect
from .models import QuestionPaper, Question
from django.contrib import messages
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.models import User
from .forms import (
    LoginForm,
    UserRegistrationForm,
    UserProfileRegistrationForm,
    DepartmentForm,
    SkillForm,
)
from .models import QuestionPaper, PaperSection, Question, Department, Skill


def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard") if request.user.is_staff else redirect("home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("dashboard") if user.is_staff else redirect("home")
    else:
        form = LoginForm()
    return render(request, "login.html", {"form": form, "title": "Login"})


def home(request):
    return render(request, "home.html", {"user": request.user})


def user_logout(request):
    logout(request)
    return redirect("login")


def user_register(request):
    if request.method == "POST":
        user_form = UserRegistrationForm(request.POST)

        if user_form.is_valid():
            user = user_form.save()
            profile_form = UserProfileRegistrationForm(
                request.POST, instance=user.profile
            )
            if profile_form.is_valid():
                profile_form.save()
                return redirect("login")
            else:
                user.delete()
        # Agar form valid nahi hai (ya email duplicate hai), toh code
        # neeche jaakar page ko error ke saath render kar dega.
    else:
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()

    # Yahan UnboundLocalError se bachne ke liye ek chhota sa fix
    if request.method != "POST" or not "user_form" in locals():
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()
    elif "profile_form" not in locals():
        profile_form = UserProfileRegistrationForm(request.POST)

    context = {"user_form": user_form, "profile_form": profile_form}
    return render(request, "registration/register.html", context)


@login_required
def dashboard(request):
    papers = QuestionPaper.objects.filter(created_by=request.user).order_by(
        "-created_at"
    )

    context = {"user": request.user, "title": "User Dashboard", "papers": papers}
    return render(request, "dashboard.html", context)


@login_required
def generate_questions(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            job_title = data.get("job_title")
            min_exp = data.get("min_exp")
            max_exp = data.get("max_exp")
            skills_raw = data.get("skills")
            sections_data = data.get("sections", {})
            total_questions = sum(sections_data.values())

            prompt = f"""
            Generate a technical assessment paper based on the following precise specifications.
            The entire response MUST be a single, valid JSON object. Do not wrap it in markdown backticks.

            1. Job Role: {job_title}
            2. Experience Level: From {min_exp} to {max_exp} years.
            3. Core Skills to Test: {skills_raw}
            4. Total Questions: {total_questions}
            5. Paper Sections and Question Counts: {json.dumps(sections_data)}
            6. **Question & Answer Constraint**: This is the most important rule. All questions must have a concise answer. The answer can be a single word, a number, a short phrase, or **a single, short line of code**. Avoid questions requiring multi-line code or long paragraph explanations.
            - **Good Technical Example:** 'Write a Python list comprehension to generate squares of numbers from 0 to 4.' (Answer: `[x**2 for x in range(5)]`)
            - **Good Aptitude Example:** 'If A is the brother of B, and C is the sister of A, what is the relation of C to B?' (Answer: 'Sister')
            - **Bad Example:** 'Explain the principles of Object-Oriented Programming.'
            7. Output Structure Constraint:
            - The main JSON object MUST have two keys: 'title' (string) and 'sections' (array).
            - Each section object in the 'sections' array must have 'title' and 'questions'.
            - Each question MUST include: 'text', 'answer', and 'type'.
            - The 'type' must be one of the following short codes: 'MCQ', 'SA', 'Code'.
            - If it is a multiple-choice question (MCQ), it MUST also include an 'options' array.

            Generate the paper now.
            """

            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-pro")
            response = model.generate_content(prompt)

            json_text = response.text.strip().lstrip("```json").rstrip("```")
            generated_paper = json.loads(json_text)

            return JsonResponse(generated_paper)
        except json.JSONDecodeError:
            return JsonResponse(
                {"error": "Failed to decode the AI's response into valid JSON."},
                status=500,
            )
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
            return JsonResponse(
                {"error": f"An unexpected error occurred: {str(e)}"}, status=500
            )
    # Fetch all Department objects from the database
    departments = Department.objects.all()
    context = {"departments": departments}
    return render(request, "question_generator/generator.html", context)


@login_required
@require_POST
@transaction.atomic
def save_paper(request):
    """Saves the generated paper and calculates the total question count."""
    try:
        data = json.loads(request.body)

        total_questions_count = 0
        for section_data in data.get("sections", []):
            total_questions_count += len(section_data.get("questions", []))

        paper = QuestionPaper.objects.create(
            created_by=request.user,
            title=data.get("title", "Generated Assessment"),
            job_title=data.get("job_title"),
            department_name=data.get("department"),
            min_exp=data.get("min_exp"),
            max_exp=data.get("max_exp"),
            duration=data.get("duration"),
            is_public_active=False,
            skills_list=(
                ", ".join(data.get("skills", []))
                if isinstance(data.get("skills"), list)
                else data.get("skills")
            ),
            # Add the calculated count to your model instance
            total_questions=total_questions_count,
        )

        for section_index, section_data in enumerate(data.get("sections", [])):
            section = PaperSection.objects.create(
                question_paper=paper,
                title=section_data.get("title"),
                order=section_index,
            )
            for q_index, question_data in enumerate(section_data.get("questions", [])):
                # === YAHAN QUESTION CREATE KARTE SAMAY TYPE ADD KAREIN ===
                Question.objects.create(
                    section=section,
                    text=question_data.get("text"),
                    answer=question_data.get("answer"),
                    options=question_data.get("options"),
                    order=q_index,
                    # .get("type", "UN") yeh default value set karega agar AI type nahi bhejta
                    question_type=question_data.get("type", "UN"),
                )
                # ========================================================

        return JsonResponse(
            {
                "success": True,
                "message": "Paper saved successfully!",
                "redirect_url": "/dashboard/",
            }
        )
    except Exception as e:
        print(f"Error saving paper: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
def list_papers(request):
    papers = QuestionPaper.objects.filter(created_by=request.user).order_by(
        "-created_at"
    )
    return render(request, "question_generator/list_papers.html", {"papers": papers})


def take_paper(request, paper_id):
    """
    Handles the request for a public user to take a question paper.
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id)

    if not paper.is_public_active:
        return render(request, "link_deactivated.html", status=403)

    context = {
        "paper": paper,
    }
    return redirect("test:user_register_link", link_id=str(paper.id))


@login_required
def paper_detail_view(request, paper_id):
    """
    Displays the details of a single question paper, including all its
    sections and questions.
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

    skills = [skill.strip() for skill in paper.skills_list.split(",") if skill.strip()]

    context = {
        "paper": paper,
        "skills": skills,
        "title": f"Details for {paper.title}",  # Dynamic page title
    }
    return render(request, "question_generator/paper_detail.html", context)


@login_required
@transaction.atomic
def paper_edit_view(request, paper_id):
    """
    Handles editing of a question paper's metadata and its questions.
    """
    # Securely fetch the paper, ensuring it belongs to the logged-in user
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

    if request.method == "POST":
        # If the form is submitted, process the data
        form = QuestionPaperEditForm(request.POST, instance=paper)

        if form.is_valid():
            # Save the main paper details
            form.save()

            # Now, iterate through all the questions and update them from the POST data
            for section in paper.paper_sections.all():
                for question in section.questions.all():
                    # Construct the unique name for each input field from the template
                    question_text_name = f"question-text-{question.id}"
                    question_answer_name = f"question-answer-{question.id}"

                    # Update the question and answer if they exist in the submitted data
                    if question_text_name in request.POST:
                        question.text = request.POST[question_text_name]
                    if question_answer_name in request.POST:
                        question.answer = request.POST[question_answer_name]

                    question.save()  # Save each updated question

            # Redirect back to the detail page to see the changes
            return redirect("paper_detail", paper_id=paper.id)

    else:
        # If it's a GET request, just display the form with the current data
        form = QuestionPaperEditForm(instance=paper)

    context = {"form": form, "paper": paper, "title": f"Edit {paper.title}"}
    return render(request, "question_generator/paper_edit.html", context)


# def department_create_view(request):
#     if request.method == "POST":
#         form = DepartmentForm(request.POST)
#         if form.is_valid():
#             form.save()
#             return redirect("dashboard")
#     else:
#         form = DepartmentForm()

#     context = {"form": form}
#     return render(request, "partials/department/department_create.html", context)


import logging

logger = logging.getLogger(__name__)


def department_create_view(request):
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                # Success message dikhayein
                messages.success(request, "Department created successfully!")
                return redirect("dashboard")
            except Exception as e:
                # Agar koi error aaye to usey log karein
                logger.error(f"Error creating department: {e}", exc_info=True)

                # User ko ek helpful error message dikhayein
                messages.error(
                    request,
                    "Could not create the department. Please try again or contact support.",
                )

                # Wapas form par bhej dein
                return redirect("department_create")
        else:
            # Agar form valid nahi hai, to user ko batayein
            messages.warning(request, "Please correct the errors below.")
    else:
        form = DepartmentForm()

    context = {"form": form}
    return render(request, "partials/department/department_create.html", context)


@login_required
def skill_list_view(request):
    """Page load karne aur saare active skills dikhane ke liye."""
    skills = Skill.objects.filter(is_active=True)
    context = {
        "skills": skills,
    }
    return render(request, "partials/skills/skill_list.html", context)


@login_required
@require_POST
def skill_create_view(request):
    """AJAX request se naya skill banane ke liye."""
    try:
        data = json.loads(request.body)
        form = SkillForm(data)
        if form.is_valid():
            skill = form.save()
            return JsonResponse(
                {"status": "success", "skill": {"id": skill.id, "name": skill.name}},
                status=201,
            )
        else:
            return JsonResponse({"status": "error", "errors": form.errors}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)


@login_required
@require_POST
def skill_update_view(request, pk):
    """(Naya View) AJAX request se skill ko edit/update karne ke liye."""
    try:
        skill = get_object_or_404(Skill, pk=pk)
        data = json.loads(request.body)
        form = SkillForm(
            data, instance=skill
        )  # 'instance=skill' batata hai ki hum update kar rahe hain
        if form.is_valid():
            updated_skill = form.save()
            return JsonResponse(
                {
                    "status": "success",
                    "skill": {"id": updated_skill.id, "name": updated_skill.name},
                },
            )
        else:
            return JsonResponse({"status": "error", "errors": form.errors}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)


@login_required
@require_POST
def skill_delete_view(request, pk):
    """AJAX request se skill delete karne ke liye."""
    skill = get_object_or_404(Skill, pk=pk)
    skill.delete()
    return JsonResponse({"status": "success", "message": "Skill deleted successfully."})


User = get_user_model()


from .models import TestRegistration


from django.shortcuts import render, get_object_or_404
from .models import TestRegistration  # User model ki zarurat nahi hai yahan


def user_list(request):
    users = TestRegistration.objects.all().order_by("id")
    return render(request, "partials/users/user_list.html", {"users": users})


# === IS FUNCTION KO UPDATE KAREIN ===
def user_detail(request, user_id):
    # User model ke bajaye TestRegistration model se object fetch karein
    registration = get_object_or_404(TestRegistration, pk=user_id)

    # test_attempts wali logic abhi relevant nahi hai, to use hata dein
    # Kyunki humare paas TestAttempt model nahi hai.

    context = {
        "registration": registration,  # Context ka naam bhi aasan kar dete hain
    }
    return render(request, "partials/users/user_details.html", context)


@login_required
def delete_user(request, user_id):
    user_to_delete = get_object_or_404(User, pk=user_id)

    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect("user_list")

    if user_to_delete.is_superuser:
        messages.error(request, "Superusers cannot be deleted.")
        return redirect("user_list")

    if request.method == "POST":
        user_to_delete.delete()
        messages.success(
            request, f"User '{user_to_delete.username}' has been deleted successfully."
        )
        return redirect("user_list")

    context = {"user_to_delete": user_to_delete}
    return render(request, "partials/users/confirm_user_delete.html", context)


@login_required
def user_profile_view(request, pk):
    profile_user = get_object_or_404(User, pk=pk)

    context = {"profile_user": profile_user}

    return render(request, "partials/users/profile.html", context)


def get_sections_by_department(request, department_id):
    try:
        department = Department.objects.get(pk=department_id)
        sections = department.sections.all().values_list("name", flat=True)
        return JsonResponse({"sections": list(sections)})
    except Department.DoesNotExist:
        return JsonResponse({"sections": []}, status=404)


@login_required
@require_POST
def toggle_paper_public_status(request, paper_id):
    """
    Toggles the public accessibility (is_public_active field) of a QuestionPaper.
    This is called by the JavaScript fetch() from the share modal.
    """
    try:
        paper = QuestionPaper.objects.get(pk=paper_id, created_by=request.user)

        paper.is_public_active = not paper.is_public_active
        paper.save()

        return JsonResponse(
            {
                "status": "success",
                "message": "Paper status updated successfully.",
                "is_public_active": paper.is_public_active,
            }
        )

    except QuestionPaper.DoesNotExist:
        return JsonResponse(
            {
                "status": "error",
                "message": "Paper not found or you do not have permission to modify it.",
            },
            status=404,
        )


# app/views.py

from django.shortcuts import render, get_object_or_404
from .models import (
    TestRegistration,
    UserResponse,
    Question,
)


def test_result(request, registration_id):
    # Get the registration object
    registration = get_object_or_404(TestRegistration, pk=registration_id)

    # Get all user responses for this test
    user_responses = UserResponse.objects.filter(
        registration=registration
    ).select_related("question")

    # Get the total number of questions for the paper
    total_questions = Question.objects.filter(
        section__question_paper=registration.question_paper
    ).count()

    score = 0
    results_data = []

    # Calculate the score
    for response in user_responses:
        is_correct = (
            response.user_answer.strip().lower()
            == response.question.answer.strip().lower()
        )
        if is_correct:
            score += 1

        results_data.append(
            {
                "question_text": response.question.text,
                "user_answer": response.user_answer,
                "correct_answer": response.question.answer,
                "is_correct": is_correct,
            }
        )

    # Calculate incorrect answers
    incorrect_answers = total_questions - score

    # --- FIX: CALCULATE THE PERCENTAGE ---
    # Avoid division by zero if there are no questions
    if total_questions > 0:
        percentage = round((score / total_questions) * 100)
    else:
        percentage = 0
    # ------------------------------------

    context = {
        "registration": registration,
        "results": results_data,
        "score": score,
        "total_questions": total_questions,
        "incorrect_answers": incorrect_answers,
        "percentage": percentage,  # <-- Add percentage to context
        "title": f"Test Report for {registration.email}",
    }

    return render(request, "partials/users/test_report.html", context)


# def test_result(request, registration_id):
#     # Get the registration object
#     registration = get_object_or_404(TestRegistration, pk=registration_id)

#     # Get all user responses for this test
#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")

#     # Get the total number of questions for the paper using the correct query
#     total_questions = Question.objects.filter(
#         section__question_paper=registration.question_paper
#     ).count()

#     score = 0
#     results_data = []

#     # Calculate the score
#     for response in user_responses:
#         is_correct = (
#             response.user_answer.strip().lower()
#             == response.question.answer.strip().lower()
#         )
#         if is_correct:
#             score += 1

#         results_data.append(
#             {
#                 "question_text": response.question.text,
#                 "user_answer": response.user_answer,
#                 "correct_answer": response.question.answer,
#                 "is_correct": is_correct,
#             }
#         )

#     # Calculate incorrect answers
#     incorrect_answers = total_questions - score

#     context = {
#         "registration": registration,
#         "results": results_data,
#         "score": score,
#         "total_questions": total_questions,
#         "incorrect_answers": incorrect_answers,
#         "title": f"Test Report for {registration.email}",
#     }

#     return render(request, "partials/users/test_report.html", context)
