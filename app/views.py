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
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            job_title = data.get("job_title")
            min_exp = data.get("min_exp")
            max_exp = data.get("max_exp")
            skills_raw = data.get("skills")
            sections_data = data.get("sections", {})
            total_questions = sum(sections_data.values())

            seniority = "Junior"
            if int(max_exp) > 5:
                seniority = "Senior"
            elif int(max_exp) > 2:
                seniority = "Mid-Level"

            # --- KEY CHANGES START HERE ---

            prompt = f"""
            Act as a seasoned technical assessment creator and principal engineer. Your primary goal is to build a well-balanced and experience-appropriate technical test. The entire response MUST be a single, valid JSON object without any markdown.

            ## Core Specifications
            1.  **Job Role**: {job_title}
            2.  **Experience Level**: {min_exp} to {max_exp} years ({seniority}-level).
            3.  **Core Skills**: {skills_raw}
            4.  **Paper Sections**: {json.dumps(sections_data)}

            ## Guiding Principles: Think Like an Assessor
            You must follow these hierarchical rules precisely.

            1.  **Overall Difficulty**: The complexity of every single question must align with the **{seniority}** level.

            2.  **Situational Questions**: For non-technical sections like 'Aptitude', provide realistic, job-related scenarios.

            3.  **⭐ Intelligent Generation for Programming/Coding Sections ⭐**: This is your most important directive. For any section with a title containing 'Programming', 'Coding', or 'Algorithm', you must create an **intelligent mix of question types (`MCQ`, `SA`, `CODE`)** that reflects the candidate's seniority. Do NOT just generate one type of question.

                * **If `{seniority}` is Junior (0-2 yrs)**: The focus is on fundamentals. The section mix should be mostly `MCQ` and `SA` questions about syntax, core concepts, and predicting output. You may include **one** simple, introductory `CODE` problem (e.g., fizzbuzz, reverse a string).
                
                * **If `{seniority}` is Mid-Level (3-5 yrs)**: The balance must shift to practical application. The mix should contain fewer basic MCQs. Include `SA` questions about best practices and design choices. The **majority** of the questions should be `CODE` problems of medium complexity (e.g., interacting with data, implementing common algorithms).
                
                * **If `{seniority}` is Senior (6+ yrs)**: The focus is on depth, design, and complex problem-solving. This section must be **dominated by challenging `CODE` problems** (e.g., involving performance optimization, concurrency, or architectural patterns). Any `MCQ` or `SA` questions must be highly advanced, focusing on architectural trade-offs or subtle language features, not basics.

            4.  **Answer Formatting**: The format of the question and answer depends strictly on its `type`.
                * For **`MCQ` and `SA`** questions: The `answer` must be concise (a word, phrase, or single line of code).
                * For **`CODE`** questions: The `text` must be a full problem description (task, input, expected output). The `answer` must be a complete, multi-line code solution, formatted as a single JSON string with `\\n` for newlines.

            ## Output Structure (Strict)
            - Root JSON object: 'title' (string), 'sections' (array).
            - Section object: 'title' (string), 'questions' (array).
            - Question object: 'text', 'answer', 'type'. `MCQ` types must also have an 'options' array.

            Generate the {seniority}-level assessment now, creating the perfect, balanced mix of questions for each section as instructed.
            """

            # --- KEY CHANGES END HERE ---

            genai.configure(api_key=settings.GEMINI_API_KEY)
            # Using a powerful model is key for understanding these nuanced instructions
            model = genai.GenerativeModel("gemini-2.5-pro")
            response = model.generate_content(prompt)

            json_text = response.text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]

            generated_paper = json.loads(json_text)

            return JsonResponse(generated_paper)
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}")
            print(f"Received text from AI: {response.text}")
            return JsonResponse(
                {
                    "error": "Failed to decode the AI's response. The format was invalid."
                },
                status=500,
            )
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
            return JsonResponse(
                {"error": f"An unexpected error occurred: {str(e)}"}, status=500
            )

    departments = Department.objects.all()
    context = {"departments": departments}
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

# ... (rest of your imports)


# @login_required
# def paper_detail_view(request, paper_id):
#     """
#     Displays the details of a single question paper, including all its
#     sections, questions, and filtered participants with their status.
#     Now includes filtering by both test status and shortlist status.
#     """
#     paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

#     # Get filter values from the URL query parameters
#     status_filter = request.GET.get("status", "all")
#     shortlist_filter = request.GET.get(
#         "shortlist_status", "all"
#     )  # <-- NEW: Get shortlist filter

#     skills = [skill.strip() for skill in paper.skills_list.split(",") if skill.strip()]

#     # 1. Fetch all participants related to this paper
#     all_participants = list(
#         TestRegistration.objects.filter(question_paper=paper).order_by("-start_time")
#     )

#     # 2. Determine the 'pass', 'fail', or 'pending' status for each participant in Python
#     for p in all_participants:
#         if p.is_completed:
#             if p.score is not None and paper.cutoff_score is not None:
#                 if p.score >= paper.cutoff_score:
#                     p.status = "pass"
#                 else:
#                     p.status = "fail"
#             else:
#                 # If cutoff isn't set, any completed test is considered 'fail' for status purposes
#                 p.status = "fail"
#         else:
#             p.status = "pending"

#     # 3. Apply the first filter (test status)
#     if status_filter != "all":
#         # Start with a list of participants filtered by pass/fail/pending
#         filtered_participants = [
#             p for p in all_participants if p.status == status_filter
#         ]
#     else:
#         # If the filter is 'all', start with the full list
#         filtered_participants = all_participants

#     # 4. Apply the second filter (shortlist status) on the *already filtered* list
#     if shortlist_filter == "shortlisted":
#         final_participants = [p for p in filtered_participants if p.is_shortlisted]
#     elif shortlist_filter == "not_shortlisted":
#         final_participants = [p for p in filtered_participants if not p.is_shortlisted]
#     else:  # 'all'
#         final_participants = filtered_participants

#     context = {
#         "paper": paper,
#         "skills": skills,
#         "participants": final_participants,  # <-- Pass the final, double-filtered list
#         "title": f"Details for {paper.title}",
#         "selected_status": status_filter,
#         "selected_shortlist_status": shortlist_filter,  # <-- NEW: Pass shortlist status to template
#     }
#     return render(request, "question_generator/paper_detail.html", context)

# app/views.py

# Make sure this import is at the top of your views.py file
from .models import UserResponse


@login_required
def paper_detail_view(request, paper_id):
    """
    Displays the details of a single question paper.
    This version RE-CALCULATES the score for each participant to ensure
    consistency with the test report, even if answers have been edited.
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
            # 1. Fetch all responses for this participant
            user_responses = UserResponse.objects.filter(registration=p)

            # 2. Recalculate the number of correct answers
            correct_answers_count = 0
            for response in user_responses:
                # Ensure we handle cases where a question or its answer might be missing
                if response.question and response.question.answer:
                    if (
                        response.user_answer.strip().lower()
                        == response.question.answer.strip().lower()
                    ):
                        correct_answers_count += 1

            # 3. Calculate the percentage score live
            total_questions = p.question_paper.total_questions
            live_percentage = 0
            if total_questions > 0:
                live_percentage = round((correct_answers_count / total_questions) * 100)

            # 4. Use this live percentage for the status check
            cutoff = p.question_paper.cutoff_score
            if cutoff is not None:
                if live_percentage >= cutoff:
                    p.status = "pass"
                else:
                    p.status = "fail"
            else:
                # If no cutoff is set, any completed test is considered a "pass"
                p.status = "pass"
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


# ... (the rest of your views.py file)

# @login_required
# def paper_detail_view(request, paper_id):
#     """
#     Displays the details of a single question paper, including all its
#     sections, questions, and filtered participants with their status.
#     """
#     paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)
#     status_filter = request.GET.get("status", "all")

#     skills = [skill.strip() for skill in paper.skills_list.split(",") if skill.strip()]

#     # 1. Sabse pehle, paper se jude saare participants ko fetch kar lein.
#     all_participants = list(
#         TestRegistration.objects.filter(question_paper=paper).order_by("-start_time")
#     )

#     # 2. Ab har participant ka status set karein (aapka original logic bilkul sahi hai)
#     for p in all_participants:
#         if p.is_completed:
#             if p.score is not None and paper.cutoff_score is not None:
#                 if p.score >= paper.cutoff_score:
#                     p.status = "pass"
#                 else:
#                     p.status = "fail"
#             else:
#                 # Agar cutoff nahi hai, to completed test 'fail' mana jayega
#                 p.status = "fail"
#         else:
#             # Agar test complete nahi hua to 'pending'
#             p.status = "pending"

#     # 3. Ab jab sabka status set ho chuka hai, to Python mein filter karein
#     if status_filter != "all":
#         # List comprehension se final list banayein jo filter se match kare
#         participants = [p for p in all_participants if p.status == status_filter]
#     else:
#         # Agar filter 'all' hai, to poori list dikhayein
#         participants = all_participants

#     context = {
#         "paper": paper,
#         "skills": skills,
#         "participants": participants,  # Yahaan filtered list bhej rahe hain
#         "title": f"Details for {paper.title}",
#         "selected_status": status_filter,
#     }
#     return render(request, "question_generator/paper_detail.html", context)


# def test_result(request, registration_id):
#     """
#     Calculates and displays the detailed test result, including a clear
#     Pass/Fail status based on the cutoff score.
#     """
#     registration = get_object_or_404(TestRegistration, pk=registration_id)
#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")

#     paper = registration.question_paper
#     total_questions = paper.total_questions
#     cutoff_score = paper.cutoff_score  # Get the cutoff score

#     score = 0
#     results_data = []

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

#     incorrect_answers = total_questions - score
#     percentage = round((score / total_questions) * 100) if total_questions > 0 else 0

#     # --- NEW: Determine the final status ---
#     status = "Fail"
#     if percentage >= cutoff_score:
#         status = "Pass"
#     # --- END NEW ---

#     context = {
#         "registration": registration,
#         "results": results_data,
#         "score": score,
#         "total_questions": total_questions,
#         "incorrect_answers": incorrect_answers,
#         "percentage": percentage,
#         "title": f"Test Report for {registration.email}",
#         "status": status,  # Pass the status to the template
#         "cutoff_score": cutoff_score,  # Pass the cutoff score
#     }

#     return render(request, "partials/users/test_report.html", context)


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


# def test_result(request, registration_id):
#     registration = get_object_or_404(TestRegistration, pk=registration_id)
#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")

#     # Get the related question paper to access its properties
#     paper = registration.question_paper

#     total_questions = paper.total_questions

#     score = 0
#     results_data = []

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

#     incorrect_answers = total_questions - score

#     if total_questions > 0:
#         percentage = round((score / total_questions) * 100)
#     else:
#         percentage = 0

#     # --- NEW LOGIC STARTS HERE ---

#     # Get the cutoff score from the paper
#     cutoff_score = paper.cutoff_score

#     # Determine the status
#     status = "Fail"
#     if percentage >= cutoff_score:
#         status = "Pass"

#     # --- NEW LOGIC ENDS HERE ---

#     context = {
#         "registration": registration,
#         "results": results_data,
#         "score": score,
#         "total_questions": total_questions,
#         "incorrect_answers": incorrect_answers,
#         "percentage": percentage,
#         "title": f"Test Report for {registration.email}",
#         "status": status,
#         "cutoff_score": cutoff_score,
#     }

#     return render(request, "partials/users/test_report.html", context)


# app/views.py
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
                is_correct = evaluate_answer_with_ai(
                    question_text=question.text,
                    user_answer=user_answer,
                    model_answer=question.answer.strip(),
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


# def test_result(request, registration_id):
#     """
#     Calculates and displays the detailed test result.
#     This version uses the SAME evaluation logic as submit_test to ensure
#     the report is always consistent with the score.
#     """
#     registration = get_object_or_404(TestRegistration, pk=registration_id)
#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")

#     paper = registration.question_paper
#     total_questions = paper.total_questions
#     cutoff_score = paper.cutoff_score

#     score = 0
#     results_data = []

#     # ▼▼▼ ISSE ISME BADALNA HAI (CHANGE THIS) ▼▼▼
#     for response in user_responses:
#         question = response.question
#         user_answer = response.user_answer.strip()
#         is_correct = False  # Assume incorrect by default

#         # Rule 1: For MCQs, do a simple, direct text comparison.
#         if question.question_type == "MCQ":
#             model_answer = question.answer.strip()
#             if user_answer.lower() == model_answer.lower():
#                 is_correct = True

#         # Rule 2: For any other type (SA, CODE), use the smart AI to evaluate.
#         else:
#             is_correct = evaluate_answer_with_ai(
#                 question_text=question.text,
#                 user_answer=user_answer,
#                 model_answer=question.answer.strip(),
#             )

#         if is_correct:
#             score += 1

#         results_data.append(
#             {
#                 "question_text": response.question.text,
#                 "user_answer": response.user_answer,
#                 "correct_answer": response.question.answer,
#                 "is_correct": is_correct,  # Now this value is from the correct logic
#             }
#         )
#     # ▲▲▲ YAHAN TAK BADLAV KIYA GAYA HAI (CHANGES END HERE) ▲▲▲

#     incorrect_answers = total_questions - score
#     percentage = round((score / total_questions) * 100) if total_questions > 0 else 0

#     status = "Fail"
#     if percentage >= cutoff_score:
#         status = "Pass"

#     context = {
#         "registration": registration,
#         "results": results_data,
#         "score": score,
#         "total_questions": total_questions,
#         "incorrect_answers": incorrect_answers,
#         "percentage": percentage,
#         "title": f"Test Report for {registration.email}",
#         "status": status,
#         "cutoff_score": cutoff_score,
#     }

#     return render(request, "partials/users/test_report.html", context)


# ... (rest of your views.py)


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


# @require_POST
# def submit_test(request, registration_id):
#     """
#     Test submit hone par yeh view call hoga.
#     Yeh score calculate karke TestRegistration mein save karega.
#     """
#     registration = get_object_or_404(TestRegistration, pk=registration_id)

#     # Pehle se completed test ko dobara submit na hone dein
#     if registration.is_completed:
#         return redirect("test_result", registration_id=registration.id)

#     # Saare user responses fetch karein
#     user_responses = UserResponse.objects.filter(registration=registration)
#     total_questions = registration.question_paper.total_questions

#     correct_answers_count = 0
#     for response in user_responses:
#         # Case-insensitive aur extra space hata kar answer check karein
#         if (
#             response.user_answer.strip().lower()
#             == response.question.answer.strip().lower()
#         ):
#             correct_answers_count += 1

#     # Percentage score calculate karein
#     percentage_score = 0
#     if total_questions > 0:
#         percentage_score = round((correct_answers_count / total_questions) * 100, 2)

#     # Registration object ko update aur save karein
#     registration.is_completed = True
#     registration.end_time = timezone.now()
#     registration.score = percentage_score  # Score save karein
#     registration.save(update_fields=["is_completed", "end_time", "score"])

#     # User ko result page par redirect karein
#     return redirect("test_result", registration_id=registration.id)


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


def evaluate_answer_with_ai(question_text, user_answer, model_answer):
    """
    Uses Gemini AI to evaluate if a user's answer is conceptually correct.
    Returns True if answer is at least 50% correct conceptually.
    """
    if not user_answer or not user_answer.strip():
        return False

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")  # Updated model

        prompt = f"""
        You are an expert technical evaluator. Your job is to check if a user's answer demonstrates understanding of the concept.

        **Question:**
        {question_text}

        **Model Answer (Reference):**
        {model_answer}

        **User's Answer:**
        {user_answer}

        **Evaluation Rules:**
        1. Check if the user's answer conveys the CORE CONCEPT correctly
        2. Accept answers that are at least 50% conceptually correct
        3. Ignore minor grammar mistakes, typos, or extra words
        4. Accept synonyms and alternative explanations if they're correct
        5. Focus on understanding, not exact word matching

        **Examples of what to accept:**
        - If model answer is "Lists are mutable, tuples are immutable"
        - Accept: "You can change lists but not tuples"
        - Accept: "Lists can be modified, tuples cannot be modified"
        - Accept: "Tuples are read-only, lists are not"

        Respond with ONLY a JSON object:
        {{
            "is_correct": true/false,
            "confidence": 0-100,
            "reason": "brief explanation"
        }}
        """

        response = model.generate_content(prompt)
        cleaned_text = response.text.strip()

        # Remove markdown if present
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        result = json.loads(cleaned_text)

        # Log for debugging
        print(f"AI Evaluation - Question: {question_text[:50]}...")
        print(f"User Answer: {user_answer}")
        print(f"AI Result: {result}")

        return result.get("is_correct", False)

    except Exception as e:
        print(f"AI Evaluation Error: {e}")
        # Fallback: do basic string matching
        return user_answer.lower().strip() in model_answer.lower()


# @require_POST
# def submit_test(request, registration_id):
#     """
#     Evaluates test submission with improved AI evaluation for subjective answers.
#     """
#     registration = get_object_or_404(TestRegistration, pk=registration_id)

#     if registration.is_completed:
#         return redirect("test_result", registration_id=registration.id)

#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")

#     total_questions = registration.question_paper.total_questions
#     correct_answers_count = 0

#     # ✅ Detailed evaluation with logging
#     for response in user_responses:
#         question = response.question
#         user_answer = response.user_answer.strip()
#         is_correct = False

#         # MCQ: Direct string comparison
#         if question.question_type == "MCQ":
#             model_answer = question.answer.strip()
#             is_correct = user_answer.lower() == model_answer.lower()
#             print(
#                 f"MCQ Check - Q: {question.text[:30]}... | User: {user_answer} | Model: {model_answer} | Correct: {is_correct}"
#             )

#         # SA/CODE: AI Evaluation
#         else:
#             if user_answer:  # Only evaluate if user provided an answer
#                 is_correct = evaluate_answer_with_ai(
#                     question_text=question.text,
#                     user_answer=user_answer,
#                     model_answer=question.answer.strip(),
#                 )
#             else:
#                 print(f"Skipping empty answer for: {question.text[:30]}...")

#         if is_correct:
#             correct_answers_count += 1

#     # Calculate score
#     percentage_score = 0
#     if total_questions > 0:
#         percentage_score = round((correct_answers_count / total_questions) * 100, 2)

#     # Save results
#     registration.is_completed = True
#     registration.end_time = timezone.now()
#     registration.score = percentage_score
#     registration.save(update_fields=["is_completed", "end_time", "score"])

#     print(
#         f"Final Score: {correct_answers_count}/{total_questions} = {percentage_score}%"
#     )

#     return redirect("test_result", registration_id=registration.id)


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
                is_correct = evaluate_answer_with_ai(
                    question_text=question.text,
                    user_answer=user_answer,
                    model_answer=question.answer.strip(),
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


# @require_POST
# def submit_test(request, registration_id):
#     """
#     Test submit hone par yeh view call hoga.
#     Yeh score calculate karke TestRegistration mein save karega.
#     Objective questions (MCQ) are checked directly.
#     Subjective questions (SA, CODE) are evaluated by AI.
#     """
#     registration = get_object_or_404(TestRegistration, pk=registration_id)

#     if registration.is_completed:
#         return redirect("test_result", registration_id=registration.id)

#     # Use select_related to efficiently fetch the related question
#     user_responses = UserResponse.objects.filter(
#         registration=registration
#     ).select_related("question")
#     total_questions = registration.question_paper.total_questions

#     correct_answers_count = 0
#     for response in user_responses:
#         question = response.question
#         user_answer = response.user_answer.strip()
#         model_answer = question.answer.strip()
#         is_correct = False

#         # ▼▼▼ KEY CHANGE IS HERE ▼▼▼
#         # If the question is a multiple-choice question, check it directly.
#         if question.question_type == "MCQ":
#             if user_answer.lower() == model_answer.lower():
#                 is_correct = True
#         # For any other type (SA, CODE, etc.), use the AI to evaluate.
#         else:
#             is_correct = evaluate_answer_with_ai(
#                 question_text=question.text,
#                 model_answer=model_answer,
#                 user_answer=user_answer,
#             )
#         # ▲▲▲ END OF KEY CHANGE ▲▲▲

#         if is_correct:
#             correct_answers_count += 1

#     # The rest of the function remains the same
#     percentage_score = 0
#     if total_questions > 0:
#         percentage_score = round((correct_answers_count / total_questions) * 100, 2)

#     registration.is_completed = True
#     registration.end_time = timezone.now()
#     registration.score = percentage_score
#     registration.save(update_fields=["is_completed", "end_time", "score"])

#     return redirect("test_result", registration_id=registration.id)
