# app/views.py

import json
import google.generativeai as genai
from django.contrib.auth import login, logout
from django.views.decorators.http import require_POST
from django.db import transaction
from django.conf import settings
from .forms import QuestionPaperEditForm
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, render, redirect
from .models import QuestionPaper, Question
from django.contrib.auth.models import User
from .forms import (
    LoginForm,
    UserRegistrationForm,
    UserProfileRegistrationForm,
    DepartmentForm,
    SkillForm,
)
import csv  # <-- ADD THIS LINE
from .models import QuestionPaper, PaperSection, Question, Department, Skill
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from .models import (
    TestRegistration,
    UserResponse,
)
from django.views.decorators.csrf import csrf_exempt

from django.contrib import messages


def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard") if request.user.is_staff else redirect("home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(
                request,
                f"Welcome back, {user.username}! You've successfully logged in. 🎉",
            )

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

    else:
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()

    if request.method != "POST" or not "user_form" in locals():
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()
    elif "profile_form" not in locals():
        profile_form = UserProfileRegistrationForm(request.POST)

    context = {"user_form": user_form, "profile_form": profile_form}
    return render(request, "registration/register.html", context)


@login_required
def dashboard(request):
    status_filter = request.GET.get("status", "all")
    experience_filter = request.GET.get("experience", "all")

    papers_query = QuestionPaper.objects.filter(created_by=request.user, is_active=True)

    if status_filter == "active":
        papers_query = papers_query.filter(is_public_active=True)
    elif status_filter == "inactive":
        papers_query = papers_query.filter(is_public_active=False)

    if experience_filter and experience_filter != "all":
        if "+" in experience_filter:  # e.g. "6+"
            lower_bound = int(experience_filter.replace("+", ""))
            papers_query = papers_query.filter(min_exp__gte=lower_bound)
        elif "-" in experience_filter:  # e.g. "0-2"
            min_exp, max_exp = experience_filter.split("-")
            papers_query = papers_query.filter(
                min_exp__lte=int(max_exp), max_exp__gte=int(min_exp)
            )

    all_papers_list = papers_query.annotate(
        participant_count=Count("testregistration")
    ).order_by("-created_at")

    paginator = Paginator(all_papers_list, 10)
    page_number = request.GET.get("page")
    papers_on_page = paginator.get_page(page_number)

    context = {
        "user": request.user,
        "title": "User Dashboard",
        "papers": papers_on_page,
        "selected_status": status_filter,
        "selected_experience": experience_filter,
    }
    return render(request, "dashboard.html", context)


@login_required
def generate_questions(request):
    """
    Generates a fixed, hardcoded technical assessment paper in JSON format
    on POST request, or renders the page on GET request.

    This function has been modified to strictly return the user-provided
    question set to ensure a consistent test paper.
    """

    # --- 1. Handle POST Request (Generate/Return Paper) ---
    if request.method == "POST":
        try:
            # Load input data (kept for original function structure, though not used for generation)
            data = json.loads(request.body)
            job_title = data.get("job_title", "Software Engineer")
            max_exp = data.get("max_exp", "5")

            seniority = "Mid-Level"
            if int(max_exp) > 5:
                seniority = "Senior"
            elif int(max_exp) <= 2:
                seniority = "Junior"

            # --- Fixed, Hardcoded Paper Content (STRICT OUTPUT) ---
            fixed_paper_json = {
                "title": f"Technical Assessment ({seniority} - {job_title})",
                "sections": [
                    {
                        "title": "Aptitude",
                        "questions": [
                            {
                                "text": "A background job processes tasks from a queue. It processes 5 tasks in the first minute, 8 tasks in the second minute, 11 in the third, and so on, increasing its throughput by 3 tasks each minute. How many total tasks will have been processed after 5 minutes?",
                                "answer": "65",
                                "type": "SA",
                            },
                            {
                                "text": "A machine produces 6 items in the first hour, 10 items in the second hour, 14 items in the third hour, and continues increasing by 4 items every hour. How many total items will it produce in 5 hours?",
                                "answer": "70",
                                "type": "SA",
                            },
                            {
                                "text": "Pointing to a photograph, Ramesh said, “He is the son of my grandfather’s only son.” How is the person in the photograph related to Ramesh?",
                                "answer": "He is Ramesh’s brother.",
                                "type": "SA",
                            },
                            {
                                "text": "A man walks 4 km towards the North. Then he turns right and walks 3 km. Again, he turns right and walks 2 km. Finally, he turns left and walks 1 km. In which direction is he facing now, and how far is he from the starting point?",
                                "answer": "Facing East, and 2√5 km (≈ 4.47 km) from the starting point.",
                                "type": "SA",
                            },
                            {
                                "text": "In a certain code, “BIRD” is written as “CJSE”. Using the same code, how is “FARM” written?",
                                "answer": "GBSN",
                                "type": "SA",
                            },
                        ],
                    },
                    {
                        "title": "Programming",
                        "questions": [
                            {
                                "text": "Write a JavaScript function called `sumPositiveNumbers` that takes an array of numbers as an argument. The function should return the sum of all the positive numbers in the array. Negative numbers and zero should be ignored. Example Input: [1, -4, 7, 12, -9, 0] Expected Output: 20",
                                "answer": "function sumPositiveNumbers(arr) { let sum = 0; for (let i = 0; i < arr.length; i++) { if (arr[i] > 0) { sum += arr[i]; } } return sum; }",
                                "type": "CODE",
                            },
                            {
                                "text": "Reverse a list without using built-in reverse functions/methods. (Use Python as the language for the answer).",
                                "answer": "lst = [1, 2, 3, 4, 5]\\nreversed_list = lst[::-1]\\nprint(reversed_list)",
                                "type": "CODE",
                            },
                            {
                                "text": "In MongoDB, which index type supports searching inside arrays of embedded documents?",
                                "answer": "Multikey Index",
                                "type": "SA",
                            },
                            {
                                "text": "Write a function to rotate an array to the right by K elements. (Use Python as the language for the answer).",
                                "answer": "def rotate(arr, k):\\n    k = k % len(arr)\\n    return arr[-k:] + arr[:-k]",
                                "type": "CODE",
                            },
                            {
                                "text": "Write an SQL query to display the customer name along with their highest order amount.",
                                "answer": "SELECT c.customer_name, MAX(o.total_amount) AS highest_order\\nFROM customers c\\nJOIN orders o ON c.customer_id = o.customer_id\\nGROUP BY c.customer_name;",
                                "type": "CODE",
                            },
                            {
                                "text": "Merge two unsorted arrays and return the sorted result. (Use Python as the language for the answer).",
                                "answer": "def merge_and_sort(a, b):\\n    return sorted(a + b)",
                                "type": "CODE",
                            },
                            {
                                "text": "In a REST API, what is the main difference between PUT and PATCH?",
                                "answer": "PUT updates entire resource, PATCH updates part of it",
                                "type": "SA",
                            },
                            {
                                "text": "Write a function to move all zeros in a list to the end, maintaining the order of the non-zero elements. (Use Python as the language for the answer).",
                                "answer": "def move_zeros(lst):\\n    return [x for x in lst if x != 0] + [0] * lst.count(0)",
                                "type": "CODE",
                            },
                        ],
                    },
                    {
                        "title": "Situation_Based",
                        "questions": [
                            {
                                "text": "You are working on a feature and discover a small, unrelated bug in a piece of code written by a senior engineer. The bug doesn't affect your current task, but it could cause issues later. What is the most appropriate first step?",
                                "answer": "Create a new ticket in the project management system, detailing the bug, how to reproduce it, and assign it to the senior engineer.",
                                "type": "SA",
                            },
                            {
                                "text": "Your code works on your machine but fails on the production server. What will you do?",
                                "answer": "I’ll start by reproducing the issue in a controlled test environment. Then I’ll check differences between my local and production environments — like OS, dependencies, versions, or configuration files. I’ll use logs or debug prints to trace the issue. Once identified, I’ll fix the root cause and document it to prevent recurrence.",
                                "type": "SA",
                            },
                            {
                                "text": "You are stuck on a bug for hours and the deadline is near. What will you do?",
                                "answer": "I’ll take a short break, recheck the logic with a fresh mind, and then simplify or isolate the problem. If still stuck, I’ll clearly explain what I’ve tried and seek help from a teammate or senior — focusing on collaboration rather than wasting time alone. I’ll also inform my lead about the delay early.",
                                "type": "SA",
                            },
                            {
                                "text": "You are working on two important tasks and both have tight deadlines. How will you manage?",
                                "answer": "I’ll prioritize tasks based on urgency and business impact. Then I’ll communicate with my lead to set realistic expectations. I’ll plan a schedule, maybe splitting time between both tasks, ensuring transparency and quality in delivery.",
                                "type": "SA",
                            },
                            {
                                "text": "You made a change that caused a production issue. What will you do?",
                                "answer": "I’ll take responsibility immediately and inform my lead. I’ll roll back or patch the issue quickly to minimize impact, then analyze what went wrong — whether it was lack of testing or configuration mistake. I’ll document the lesson and add preventive checks to avoid it in the future.",
                                "type": "SA",
                            },
                            {
                                "text": "A company wants to automate its customer support process. They design a system that: Reads customer complaints from emails, Identifies product issues using AI, Automatically issues refunds for verified cases, and Escalates complex cases to a human agent. Which type of system best represents this automation approach?",
                                "answer": "Cognitive Automation (AI system that learns and makes decisions)",
                                "type": "SA",
                            },
                        ],
                    },
                ],
            }

            # SUCCESS: Directly return the fixed JSON response
            return JsonResponse(fixed_paper_json)

        except json.JSONDecodeError as e:
            # Handle error if the input JSON from the request body is invalid
            return JsonResponse(
                {"error": "Failed to decode the input JSON from the request body."},
                status=400,
            )
        except Exception as e:
            # Handle any other unexpected errors during POST
            print(f"An unexpected error occurred: {str(e)}")
            return JsonResponse(
                {"error": f"An unexpected error occurred during POST: {str(e)}"},
                status=500,
            )

    # --- 2. Handle GET Request (Render Page) ---
    # This block executes if the request method is not POST (e.g., GET, which was causing the error)
    # It MUST return an HttpResponse object (like render) to fix the ValueError.
    else:
        # Context preparation (replace 'Department.objects.all()' with actual logic if needed)
        try:
            # Uncomment the lines below if 'Department' model and its imports are correctly set up
            departments = Department.objects.all()
            context = {"departments": departments}
        # Use an empty context if the Department model is not immediately needed
        except NameError:
            context = {}  # Fallback if Department is not imported

        return render(request, "question_generator/generator.html", context)


# ... (keep all other views as they are) ...
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
            is_active=True,
            duration=data.get("duration"),
            is_public_active=False,
            skills_list=(
                ", ".join(data.get("skills", []))
                if isinstance(data.get("skills"), list)
                else data.get("skills")
            ),
            total_questions=total_questions_count,
        )

        for section_index, section_data in enumerate(data.get("sections", [])):
            section = PaperSection.objects.create(
                question_paper=paper,
                title=section_data.get("title"),
                order=section_index,
            )
            for q_index, question_data in enumerate(section_data.get("questions", [])):

                Question.objects.create(
                    section=section,
                    text=question_data.get("text"),
                    answer=question_data.get("answer"),
                    options=question_data.get("options"),
                    order=q_index,
                    question_type=question_data.get("type", "UN"),
                )

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


from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import QuestionPaper, TestRegistration

# app/views.py

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import QuestionPaper, TestRegistration


from .models import UserResponse


@login_required
def paper_detail_view(request, paper_id):
    """
    Displays the details of a single question paper.
    This version RE-CALCULATES the score for each participant to ensure
    consistency with the test report. (FIXED LOGIC BELOW)
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)
    status_filter = request.GET.get("status", "all")
    shortlist_filter = request.GET.get("shortlist_status", "all")

    skills = [skill.strip() for skill in paper.skills_list.split(",") if skill.strip()]

    all_participants = list(
        TestRegistration.objects.filter(question_paper=paper).order_by("-start_time")
    )

    # ▼▼▼ THE FINAL, CORRECTED LOGIC IS HERE ▼▼▼
    for p in all_participants:
        if p.is_completed:
            user_responses = UserResponse.objects.filter(registration=p)
            correct_answers_count = 0

            for response in user_responses:
                question = response.question
                user_answer = response.user_answer.strip()
                is_correct = False

                if not user_answer:
                    # Unattempted answers are always incorrect (score-wise)
                    is_correct = False
                elif question and question.answer:
                    # 1. MCQ: Direct comparison
                    if question.question_type == "MCQ":
                        is_correct = (
                            user_answer.lower() == question.answer.strip().lower()
                        )
                    # 2. SA/CODE/TF: AI Evaluation
                    else:
                        # Map internal question type to evaluator type
                        qtype = question.question_type.upper()
                        if qtype in ("CODE", "CODING"):
                            evaluator_type = "coding"
                        elif qtype in ("SA", "SHORT", "SUBJECTIVE"):
                            evaluator_type = "short"
                        elif qtype in ("TF", "TRUE_FALSE", "BOOLEAN"):
                            evaluator_type = "true_false"
                        else:
                            evaluator_type = "short"

                        # Use the smart AI evaluation
                        is_correct, _ = evaluate_answer_with_ai(
                            question_text=question.text,
                            user_answer=user_answer,
                            model_answer=question.answer.strip(),
                            question_type=evaluator_type,
                        )

                if is_correct:
                    correct_answers_count += 1

            # 3. Calculate the percentage score live
            total_questions = p.question_paper.total_questions
            live_percentage = 0
            if total_questions > 0:
                live_percentage = round((correct_answers_count / total_questions) * 100)

            # 4. Use this live percentage for the status check
            cutoff = p.question_paper.cutoff_score
            p.score = live_percentage  # Attach live score for comparison/display

            if cutoff is not None:
                if live_percentage >= cutoff:
                    p.status = "pass"
                else:
                    p.status = "fail"
            else:
                p.status = "pass"  # No cutoff means any completed test is a pass
        else:
            p.status = "pending"
    # ▲▲▲ END OF CORRECTED LOGIC ▲▲▲

    # --- The filtering logic remains the same ---
    if status_filter != "all":
        filtered_participants = [
            p for p in all_participants if p.status == status_filter
        ]
    else:
        filtered_participants = all_participants

    if shortlist_filter == "shortlisted":
        final_participants = [p for p in filtered_participants if p.is_shortlisted]
    elif shortlist_filter == "not_shortlisted":
        final_participants = [p for p in filtered_participants if not p.is_shortlisted]
    else:
        final_participants = filtered_participants

    context = {
        "paper": paper,
        "skills": skills,
        "participants": final_participants,
        "title": f"Details for {paper.title}",
        "selected_status": status_filter,
        "selected_shortlist_status": shortlist_filter,
    }
    return render(request, "question_generator/paper_detail.html", context)


@login_required
@transaction.atomic
def paper_edit_view(request, paper_id):
    """
    Handles editing of a question paper's metadata and its questions.
    """

    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

    if request.method == "POST":
        form = QuestionPaperEditForm(request.POST, instance=paper)

        if form.is_valid():
            form.save()

            for section in paper.paper_sections.all():
                for question in section.questions.all():
                    question_text_name = f"question-text-{question.id}"
                    question_answer_name = f"question-answer-{question.id}"

                    if question_text_name in request.POST:
                        question.text = request.POST[question_text_name]
                    if question_answer_name in request.POST:
                        question.answer = request.POST[question_answer_name]

                    question.save()
                    # **NEW: Add the success message here**
            messages.success(request, "Paper updated successfully!")
            return redirect("/dashboard/")

    else:
        form = QuestionPaperEditForm(instance=paper)

    context = {"form": form, "paper": paper, "title": f"Edit {paper.title}"}
    return render(request, "question_generator/paper_edit.html", context)


import logging

logger = logging.getLogger(__name__)


def department_create_view(request):
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            try:
                form.save()

                messages.success(request, "Department created successfully!")
                return redirect("dashboard")
            except Exception as e:

                logger.error(f"Error creating department: {e}", exc_info=True)

                messages.error(
                    request,
                    "Could not create the department. Please try again or contact support.",
                )

                return redirect("department_create")
        else:

            messages.warning(request, "Please correct the errors below.")
    else:
        form = DepartmentForm()

    context = {"form": form}
    return render(request, "partials/department/department_create.html", context)


@login_required
def get_skills_json(request):
    """Returns a JSON list of all active skills."""
    skills = Skill.objects.filter(is_active=True).values("id", "name")
    return JsonResponse({"skills": list(skills)})


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
                {
                    "status": "success",
                    "skill": {
                        "id": skill.id,
                        "name": skill.name,
                        "is_active": skill.is_active,
                    },
                },
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
        form = SkillForm(data, instance=skill)
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


def user_list(request):
    users = TestRegistration.objects.all().order_by("id")
    return render(request, "partials/users/user_list.html", {"users": users})


def user_detail(request, user_id):
    registration = get_object_or_404(TestRegistration, pk=user_id)

    context = {
        "registration": registration,
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


def test_result(request, registration_id):
    """
    Displays test results with clear indication of unattempted questions.
    """
    registration = get_object_or_404(TestRegistration, pk=registration_id)
    user_responses = UserResponse.objects.filter(
        registration=registration
    ).select_related("question")

    paper = registration.question_paper
    total_questions = paper.total_questions
    cutoff_score = paper.cutoff_score

    score = 0
    results_data = []
    unattempted_count = 0  # ✅ NEW: Track unattempted questions

    for response in user_responses:
        question = response.question
        user_answer = response.user_answer.strip()
        is_correct = False
        attempt_status = "incorrect"  # ✅ NEW: Default status

        # ✅ Check if question was attempted
        if not user_answer:
            attempt_status = "unattempted"
            unattempted_count += 1
        else:
            # Question attempt kiya gaya hai, ab evaluate karo
            if question.question_type == "MCQ":
                model_answer = question.answer.strip()
                is_correct = user_answer.lower() == model_answer.lower()
            else:
                # Map internal question type to evaluator type
                qtype = question.question_type.upper()
                if qtype in ("CODE", "CODING"):
                    evaluator_type = "coding"
                elif qtype in ("SA", "SHORT", "SUBJECTIVE"):
                    evaluator_type = "short"
                elif qtype in ("TF", "TRUE_FALSE", "BOOLEAN"):
                    evaluator_type = "true_false"
                else:
                    evaluator_type = "short"

                # evaluate_answer_with_ai returns (is_correct, details)
                is_correct, _ = evaluate_answer_with_ai(
                    question_text=question.text,
                    user_answer=user_answer,
                    model_answer=question.answer.strip(),
                    question_type=evaluator_type,
                )

            # Set status based on correctness
            if is_correct:
                score += 1
                attempt_status = "correct"
            else:
                attempt_status = "incorrect"

        results_data.append(
            {
                "question_text": response.question.text,
                "user_answer": (
                    response.user_answer if user_answer else "Not Attempted"
                ),  # ✅ NEW
                "correct_answer": response.question.answer,
                "is_correct": is_correct,
                "attempt_status": attempt_status,  # ✅ NEW: Pass status to template
            }
        )

    incorrect_answers = total_questions - score - unattempted_count  # ✅ UPDATED
    percentage = round((score / total_questions) * 100) if total_questions > 0 else 0

    status = "Pass" if percentage >= cutoff_score else "Fail"

    context = {
        "registration": registration,
        "results": results_data,
        "score": score,
        "total_questions": total_questions,
        "incorrect_answers": incorrect_answers,
        "unattempted_count": unattempted_count,  # ✅ NEW
        "percentage": percentage,
        "title": f"Test Report for {registration.email}",
        "status": status,
        "cutoff_score": cutoff_score,
    }

    return render(request, "partials/users/test_report.html", context)


@csrf_exempt
def partial_update_view(request, paper_id):
    if request.method == "POST":
        try:
            paper = QuestionPaper.objects.get(pk=paper_id)
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"status": "error", "message": "Invalid JSON payload."}, status=400
                )

            if "job_title" in data:
                paper.job_title = data["job_title"] or paper.job_title
            if "duration" in data:
                paper.duration = data["duration"] or paper.duration
            if "skills_list" in data:
                skills_list = data["skills_list"]
                if isinstance(skills_list, list):
                    paper.skills = ",".join(skills_list)
                else:
                    return JsonResponse(
                        {"status": "error", "message": "skills_list must be a list."},
                        status=400,
                    )

            paper.save()

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Paper updated successfully!",
                    "updated_data": {
                        "job_title": paper.job_title,
                        "duration": paper.duration,
                        "skills_list": paper.skills.split(",") if paper.skills else [],
                    },
                }
            )

        except QuestionPaper.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Paper not found."}, status=404
            )
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    return JsonResponse(
        {"status": "error", "message": "Invalid request method."}, status=405
    )


@require_POST
def regenerate_question(request):
    try:
        data = json.loads(request.body)
        job_title = data.get("job_title")
        skills = data.get("skills")
        section_title = data.get("section_title")
        question_type = data.get("question_type")
        question_text = data.get("question_text")

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-pro")

        prompt = f"""
        As an expert technical recruiter, generate ONE new and different interview question based on the following context.
        The previous question was: "{question_text}". Do not repeat this question.

        CONTEXT:
        - Job Title: {job_title}
        - Required Skills: {skills}
        - Test Section: {section_title}
        - Question Type: {question_type}

        Generate a completely new question that assesses a similar concept but is not identical.
        
        Provide the output in a strict JSON format with no extra text or markdown formatting.
        The JSON object must have these keys: "text" (string), "type" (string, e.g., "MCQ"), "options" (an array of 4 strings for MCQ, or null for other types), and "answer" (string).
        
        Example for MCQ:
        {{
            "text": "What is the primary purpose of a virtual environment in Python?",
            "type": "MCQ",
            "options": ["To run Python code faster", "To isolate project dependencies", "To share code easily", "To write Python code"],
            "answer": "To isolate project dependencies"
        }}
        """

        response = model.generate_content(prompt)
        cleaned_response = (
            response.text.strip().replace("```json", "").replace("```", "")
        )
        new_question = json.loads(cleaned_response)

        return JsonResponse(new_question)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def deactivate_paper(request, paper_id):
    """
    Soft deletes a question paper by setting its is_active flag to False.
    """
    try:

        paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

        paper.is_active = False
        paper.save()

        return JsonResponse(
            {
                "status": "success",
                "message": f'Paper "{paper.title}" has been deactivated successfully.',
            }
        )

    except QuestionPaper.DoesNotExist:
        return JsonResponse(
            {
                "status": "error",
                "message": "Paper not found or you do not have permission to perform this action.",
            },
            status=404,
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


from django.contrib.auth import get_user_model


@login_required
def export_participants_csv(request, paper_id):
    """
    Exports a detailed list of participants to a CSV file.
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)
    User = get_user_model()  # Get the active User model

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="participants_{paper.job_title.replace(" ", "_")}_{paper.id}.csv"'
    )

    writer = csv.writer(response)

    # Updated header row
    writer.writerow(["Full Name", "Email", "Phone Number", "Username", "Test Status"])

    participants = TestRegistration.objects.filter(question_paper=paper).order_by(
        "-start_time"
    )

    for participant in participants:
        status = "Completed" if participant.is_completed else "Pending"

        # --- FIX STARTS HERE ---
        # Instead of checking for 'participant.user', we try to find a user
        # by matching the email address.
        try:
            user = User.objects.get(email__iexact=participant.email)
            # If a user is found, get their details
            full_name = user.get_full_name() or user.username
            username = user.username
        except User.DoesNotExist:
            # If no user is found with that email, they are a guest
            full_name = "Guest User"
            username = "N/A"
        # --- FIX ENDS HERE ---

        # Write the data to the CSV row
        writer.writerow(
            [full_name, participant.email, participant.phone_number, username, status]
        )

    return response


from django.utils import timezone


from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import TestRegistration


@login_required
@require_POST
def toggle_shortlist(request, registration_id):
    """
    TestRegistration ke liye is_shortlisted status ko toggle karta hai aur
    change ko database mein SAVE karta hai.
    """
    registration = get_object_or_404(TestRegistration, id=registration_id)

    # Boolean value ko ulta karein (True se False, False se True)
    registration.is_shortlisted = not registration.is_shortlisted

    # ▼▼▼ YEH LINE SABSE ZARURI HAI ▼▼▼
    # Change ko database mein save karein.
    registration.save(update_fields=["is_shortlisted"])
    # ▲▲▲ YAHI FIX HAI ▲▲▲

    # Naye status ke saath success response return karein
    return JsonResponse(
        {"status": "success", "is_shortlisted": registration.is_shortlisted}
    )


import json
import re
from typing import Tuple, Dict, Any
import google.generativeai as genai
from django.conf import settings


def evaluate_answer_with_ai(
    question_text: str,
    user_answer: str,
    model_answer: str,
    question_type: str = "short",
) -> Tuple[bool, Dict[str, Any]]:
    """
    Uses Gemini AI to evaluate if a user's answer is conceptually correct.

    Args:
        question_text: The question being asked
        user_answer: User's submitted answer
        model_answer: Correct/reference answer
        question_type: Type of question - "mcq", "short", "coding", "true_false"

    Returns:
        Tuple of (is_correct: bool, details: dict with confidence and reason)
    """
    # Empty answer check
    if not user_answer or not user_answer.strip():
        return False, {
            "is_correct": False,
            "confidence": 100,
            "reason": "Answer is empty",
        }

    # Normalize inputs
    user_answer = user_answer.strip()
    model_answer = model_answer.strip()

    try:
        # Quick checks for specific question types before AI call
        if question_type.lower() == "mcq":
            return _evaluate_mcq(user_answer, model_answer)

        elif question_type.lower() in ["true_false", "boolean"]:
            return _evaluate_boolean(user_answer, model_answer)

        # AI evaluation for short answer and coding
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")

        # Different prompts for different question types
        if question_type.lower() == "coding":
            prompt = _get_coding_prompt(question_text, user_answer, model_answer)
        else:
            prompt = _get_short_answer_prompt(question_text, user_answer, model_answer)

        response = model.generate_content(prompt)
        cleaned_text = response.text.strip()

        # Remove markdown code blocks if present
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        result = json.loads(cleaned_text)

        is_correct = result.get("is_correct", False)
        return is_correct, result

    except json.JSONDecodeError as e:

        return _fallback_evaluation(user_answer, model_answer, question_type)

    except Exception as e:
        print(f"AI Evaluation Error: {e}")
        return _fallback_evaluation(user_answer, model_answer, question_type)


def _get_short_answer_prompt(
    question_text: str, user_answer: str, model_answer: str
) -> str:
    """Generate prompt for short answer evaluation"""
    return f"""You are an expert technical evaluator. Evaluate if the user's answer demonstrates understanding of the concept.

**Question:**
{question_text}

**Reference Answer:**
{model_answer}

**User's Answer:**
{user_answer}

**Evaluation Criteria:**
1. Check if the user's answer conveys the CORE CONCEPT correctly
2. Accept answers that are at least 50% conceptually correct
3. Ignore minor grammar mistakes, typos, spelling errors, or extra/missing articles
4. Accept synonyms, paraphrases, and alternative explanations if conceptually correct
5. Accept answers in different languages (Hindi/English/Hinglish) if meaning is correct
6. Focus on understanding, not exact word matching
7. Accept partial answers if they cover the main points
8. Be lenient with formatting, structure, and presentation
9. Accept additional correct information beyond the reference answer
10. Ignore irrelevant extra words if core concept is present

**Examples of Acceptable Variations:**
- Technical terms with synonyms: "function" = "method", "array" = "list", "variable" = "identifier"
- Word order changes that preserve meaning
- Additional explanations, examples, or context
- Simpler or more complex language that captures the concept
- Missing articles (a, an, the), conjunctions, or prepositions
- Common abbreviations: "func", "var", "obj", "arr"
- Different sentence structures expressing same idea
- Casual/conversational tone vs formal tone

**Scoring Guide:**
- is_correct: true if answer demonstrates understanding (50%+ concept match)
- is_correct: false if answer is fundamentally wrong or irrelevant
- confidence: 90-100% for excellent answers
- confidence: 70-89% for good answers with minor issues
- confidence: 50-69% for acceptable answers covering basics
- confidence: below 50% for incorrect/incomplete answers

Respond with ONLY a valid JSON object (no markdown, no extra text):
{{
    "is_correct": true/false,
    "confidence": 0-100,
    "reason": "brief explanation in one line"
}}"""


def _get_coding_prompt(question_text: str, user_code: str, model_code: str) -> str:
    """Generate prompt for coding evaluation with stricter criteria."""
    return f"""You are an expert programming instructor. Evaluate if the user's code correctly solves the problem.

**Question:**
{question_text}

**Reference Solution (Use for context, but do not require exact matching):**
```
{model_code}
```

**User's Code:**
```
{user_code}
```

**Evaluation Criteria:**
1. **CRITICAL: The user's code MUST solve the specific problem described in the Question.**
2. **If the question specifies a language (e.g., 'Write a JavaScript function...'), a solution in a different, incompatible language (e.g., Python for a JavaScript-specific task) should result in is_correct: false.** If the logic is sound and easily translatable, you may be lenient, but prioritize the requested language.
3. The core logic must be sound, even if the implementation style differs.
4. Accept different approaches: loops vs. comprehensions, recursion vs. iteration.
5. Accept different but correct algorithms.
6. Ignore minor syntax variations: spacing, indentation, bracket styles.
7. Accept more efficient or optimized solutions.
8. Accept solutions with additional features (error handling, edge cases).

**What to REJECT (This must result in is_correct: false):**
- **Code that solves a COMPLETELY DIFFERENT PROBLEM than the one asked.**
- **Code that is in a different language when the question explicitly requires a specific one.**
- Logic errors that produce incorrect output.
- Missing critical functionality.
- Code that would crash or throw errors on valid inputs.

**Scoring Guide:**
- is_correct: true if code would work and solve the problem (50%+ functionality)
- is_correct: false if code has fundamental logic errors or solves the wrong problem
- confidence: 90-100% for perfect or near-perfect solutions
- confidence: 70-89% for working solutions with minor issues
- confidence: 50-69% for solutions that mostly work
- confidence: below 50% for non-working code or solutions to the wrong problem

Respond with ONLY valid JSON (no markdown, no extra text):
{{
    "is_correct": true/false,
    "confidence": 0-100,
    "reason": "brief explanation"
}}"""


def _evaluate_mcq(user_answer: str, model_answer: str) -> Tuple[bool, Dict]:
    """Evaluate MCQ answers with flexibility for different formats"""

    # Normalize both answers
    user_clean = re.sub(r"[^\w\s]", "", user_answer.lower()).strip()
    model_clean = re.sub(r"[^\w\s]", "", model_answer.lower()).strip()

    # Direct match
    if user_clean == model_clean:
        return True, {"is_correct": True, "confidence": 100, "reason": "Exact match"}

    # Extract option letters (A, B, C, D)
    option_patterns = [
        r"^([a-d])\)?\.?\s*",  # A, A), A.
        r"option\s*([a-d])",  # Option A
        r"^([a-d])\s*[-:]\s*",  # A - something, A: something
        r"\(([a-d])\)",  # (A)
        r"answer\s*:?\s*([a-d])",  # Answer: A
    ]

    user_option = None
    model_option = None

    for pattern in option_patterns:
        if not user_option:
            user_match = re.search(pattern, user_answer.lower())
            if user_match:
                user_option = user_match.group(1)

        if not model_option:
            model_match = re.search(pattern, model_answer.lower())
            if model_match:
                model_option = model_match.group(1)

    # Compare extracted options
    if user_option and model_option:
        if user_option == model_option:
            return True, {
                "is_correct": True,
                "confidence": 95,
                "reason": f"Correct option: {user_option.upper()}",
            }
        else:
            return False, {
                "is_correct": False,
                "confidence": 100,
                "reason": f"Wrong option: {user_option.upper()} (correct: {model_option.upper()})",
            }

    # Full text comparison (if user wrote full option text)
    if len(user_clean) > 3 and len(model_clean) > 3:
        if user_clean in model_clean or model_clean in user_clean:
            return True, {
                "is_correct": True,
                "confidence": 90,
                "reason": "Answer matches option text",
            }

        # Word overlap check
        user_words = set(user_clean.split())
        model_words = set(model_clean.split())
        if len(model_words) > 0:
            overlap = len(user_words & model_words) / len(model_words)
            if overlap > 0.7:
                return True, {
                    "is_correct": True,
                    "confidence": int(overlap * 100),
                    "reason": f"High text similarity: {overlap:.0%}",
                }

    return False, {"is_correct": False, "confidence": 100, "reason": "Incorrect option"}


def _evaluate_boolean(user_answer: str, model_answer: str) -> Tuple[bool, Dict]:
    """Evaluate True/False questions with support for multiple formats"""

    # Define variants for True
    true_variants = [
        "true",
        "t",
        "yes",
        "y",
        "1",
        "correct",
        "right",
        "sahi",
        "han",
        "haan",
        "sach",
        "theek",
        "✓",
        "tick",
        "check",
    ]

    # Define variants for False
    false_variants = [
        "false",
        "f",
        "no",
        "n",
        "0",
        "incorrect",
        "wrong",
        "galat",
        "nahi",
        "nai",
        "jhoot",
        "ghalat",
        "✗",
        "cross",
        "x",
    ]

    user_clean = user_answer.lower().strip()
    model_clean = model_answer.lower().strip()

    # Check what user answered
    user_is_true = any(variant in user_clean for variant in true_variants)
    user_is_false = any(variant in user_clean for variant in false_variants)

    # Check correct answer
    model_is_true = any(variant in model_clean for variant in true_variants)
    model_is_false = any(variant in model_clean for variant in false_variants)

    # If both detected in user answer, take first occurrence
    if user_is_true and user_is_false:
        first_true = min(
            (user_clean.find(v) for v in true_variants if v in user_clean), default=999
        )
        first_false = min(
            (user_clean.find(v) for v in false_variants if v in user_clean), default=999
        )
        user_is_true = first_true < first_false
        user_is_false = not user_is_true

    # Compare answers
    if model_is_true and user_is_true:
        return True, {"is_correct": True, "confidence": 100, "reason": "Correct: True"}
    elif model_is_false and user_is_false:
        return True, {"is_correct": True, "confidence": 100, "reason": "Correct: False"}
    elif not model_is_false and user_is_false:
        return False, {
            "is_correct": False,
            "confidence": 100,
            "reason": "Incorrect: answered False (correct: True)",
        }
    elif not model_is_true and user_is_true:
        return False, {
            "is_correct": False,
            "confidence": 100,
            "reason": "Incorrect: answered True (correct: False)",
        }

    # If we can't determine, return False
    return False, {
        "is_correct": False,
        "confidence": 50,
        "reason": "Could not determine boolean value from answer",
    }


def _fallback_evaluation(
    user_answer: str, model_answer: str, question_type: str
) -> Tuple[bool, Dict]:
    """Fallback evaluation when AI fails"""

    user_clean = user_answer.lower().strip()
    model_clean = model_answer.lower().strip()

    # Exact match
    if user_clean == model_clean:
        return True, {
            "is_correct": True,
            "confidence": 100,
            "reason": "Exact match (fallback mode)",
        }

    # Substring match for longer answers
    if len(user_clean) > 10 and (
        user_clean in model_clean or model_clean in user_clean
    ):
        return True, {
            "is_correct": True,
            "confidence": 85,
            "reason": "Substring match (fallback mode)",
        }

    # Word overlap for short answers
    user_words = set(re.findall(r"\w+", user_clean))
    model_words = set(re.findall(r"\w+", model_clean))

    # Remove common stop words
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "but",
    }
    user_words -= stop_words
    model_words -= stop_words

    if len(model_words) > 0:
        overlap = len(user_words & model_words) / len(model_words)

        # For coding, be more strict
        threshold = 0.4 if question_type.lower() == "coding" else 0.6

        if overlap >= threshold:
            return True, {
                "is_correct": True,
                "confidence": int(overlap * 100),
                "reason": f"Word overlap: {overlap:.0%} (fallback mode)",
            }

    # For very short answers, check if user answer is substring
    if len(model_words) <= 3 and len(user_words & model_words) >= 1:
        return True, {
            "is_correct": True,
            "confidence": 70,
            "reason": "Key term match (fallback mode)",
        }

    return False, {
        "is_correct": False,
        "confidence": 60,
        "reason": "No sufficient match (fallback mode)",
    }


# Backward compatible wrapper (returns only boolean like your original)
def evaluate_answer_simple(
    question_text: str, user_answer: str, model_answer: str
) -> bool:
    """
    Simple version that returns only True/False (backward compatible)
    """
    is_correct, _ = evaluate_answer_with_ai(
        question_text, user_answer, model_answer, "short"
    )
    return is_correct


@require_POST
def submit_test(request, registration_id):
    """
    Evaluates test submission, distinguishing between incorrect and unattempted answers.
    """
    registration = get_object_or_404(TestRegistration, pk=registration_id)

    if registration.is_completed:
        return redirect("test_result", registration_id=registration.id)

    user_responses = UserResponse.objects.filter(
        registration=registration
    ).select_related("question")

    total_questions = registration.question_paper.total_questions
    correct_answers_count = 0

    for response in user_responses:
        question = response.question
        user_answer = response.user_answer.strip()
        is_correct = False

        # ✅ Only evaluate if user provided an answer
        if user_answer:
            if question.question_type == "MCQ":
                model_answer = question.answer.strip()
                is_correct = user_answer.lower() == model_answer.lower()
            else:
                # Map internal question type to evaluator type
                qtype = question.question_type.upper()
                if qtype in ("CODE", "CODING"):
                    evaluator_type = "coding"
                elif qtype in ("SA", "SHORT", "SUBJECTIVE"):
                    evaluator_type = "short"
                elif qtype in ("TF", "TRUE_FALSE", "BOOLEAN"):
                    evaluator_type = "true_false"
                else:
                    evaluator_type = "short"

                # evaluate_answer_with_ai returns (is_correct, details)
                is_correct, _ = evaluate_answer_with_ai(
                    question_text=question.text,
                    user_answer=user_answer,
                    model_answer=question.answer.strip(),
                    question_type=evaluator_type,
                )

            if is_correct:
                correct_answers_count += 1

    # Calculate score
    percentage_score = 0
    if total_questions > 0:
        percentage_score = round((correct_answers_count / total_questions) * 100, 2)

    # Save results
    registration.is_completed = True
    registration.end_time = timezone.now()
    registration.score = percentage_score
    registration.save(update_fields=["is_completed", "end_time", "score"])

    return redirect("test_result", registration_id=registration.id)


from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.shortcuts import render

# Assuming User is fetched somewhere, if not, add:
User = get_user_model()

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.shortcuts import render

User = get_user_model()


def password_reset_request(request):
    """
    Custom view jo email ko DB mein check karta hai aur agar milta hai,
    to Django ke default reset process ko aage badhata hai.
    """
    template_name = "registration/password_reset_form.html"

    if request.method == "POST":
        email = request.POST.get("email", "").strip()

        # 1. Database existence check
        try:
            # Check if a user with this email exists (case-insensitive) and is active
            User.objects.get(email__iexact=email, is_active=True)

        except User.DoesNotExist:
            # 2. Agar user nahi mila, to error message set karein.
            # Security ke liye, yeh message thoda vague (vague) hona chahiye,
            # par user requirement ke anusaar hum yahaan specific error de rahe hain.
            messages.error(
                request,
                "The email address you entered is not associated with any active account. Please check it and try again. 🧐",
            )
            # Re-render the form page with the error
            return render(request, template_name, {})

        # 3. Agar user mil gaya, to Django ke default PasswordResetView ko call karein
        # Taki mail send ho sake.
        return auth_views.PasswordResetView.as_view(template_name=template_name)(
            request
        )

    # GET request ke liye (page load hone par)
    return auth_views.PasswordResetView.as_view(template_name=template_name)(request)
