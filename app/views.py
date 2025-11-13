# app/views.py

import json
from openai import OpenAI  # Import OpenAI instead of google.generativeai
import re
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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import QuestionPaper, PaperSection, Question  # Import your models

from .forms import (
    LoginForm,
    UserRegistrationForm,
    UserProfileRegistrationForm,
    DepartmentForm,
    SkillForm,
)
import csv  
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

            2.  **Question Uniqueness (CRITICAL)**: **ABSOLUTELY NO DUPLICATE QUESTIONS.** Ensure every question generated, across all sections, is unique. If this function is run multiple times, the generated questions must be new and diverse, not a repeat of previously generated content.

            3.  **Situational & Communication Questions**:
                * For non-technical sections like 'Aptitude', provide realistic, job-related scenarios.
                * **For 'Communication' sections, the focus MUST be on evaluating English grammar, syntax, sentence structure, and vocabulary proficiency, NOT general soft skills.** Design questions (MCQ/SA) that test language correctness.

            4.  **⭐ Intelligent Generation for Programming/Coding Sections ⭐**: This is your most important directive. For any section with a title containing 'Programming', 'Coding', or 'Algorithm', you must create an **intelligent mix of question types (`MCQ`, `SA`, `CODE`)** that reflects the candidate's seniority. Do NOT just generate one type of question.

                * **If `{seniority}` is Junior (0-2 yrs)**: The focus is on fundamentals. The **primary quantity and focus MUST be on `CODE` questions**. These `CODE` problems must be simple, foundational problems, equivalent to **LeetCode Easy** level (e.g., array manipulations, string reversals, FizzBuzz, basic data structure implementation). The number of `CODE` questions should be at least **50% of the total** questions in this section, with the remainder being `MCQ` and `SA` on core concepts and predicting output.
                
                * **If `{seniority}` is Mid-Level (3-5 yrs)**: The mix must contain fewer basic MCQs and SAs. The **primary focus and highest quantity of questions MUST be `CODE` problems** of medium complexity (e.g., interacting with data, implementing common algorithms, simple API design). The number of `CODE` questions should **significantly outweigh the sum of `MCQ` and `SA` questions** in this section.
                
                * **If `{seniority}` is Senior (6+ yrs)**: The focus is on depth, design, and complex problem-solving. This section **MUST be overwhelmingly dominated by challenging `CODE` problems**. The number of `CODE` questions must constitute the **vast majority** of the section's total, with any remaining `MCQ` or `SA` questions being highly advanced, focusing on architectural trade-offs or subtle language features, not basics.

            5.  **Answer Formatting**: The format of the question and answer depends strictly on its `type`.
                * For **`MCQ` and `SA`** questions: The `answer` must be concise (a word, phrase, or single line of code).
                * For **`CODE`** questions: The `text` must be a full problem description (task, input, expected output). The `answer` must be a complete, multi-line code solution, formatted as a single JSON string with `\\n` for newlines.

            ## Output Structure (Strict)
            - Root JSON object: 'title' (string), 'sections' (array).
            - Section object: 'title' (string), 'questions' (array).
            - Question object: 'text', 'answer', 'type'. `MCQ` types must also have an 'options' array.

            Generate the {seniority}-level assessment now, creating the perfect, balanced mix of questions for each section as instructed.
            """


            # genai.configure(api_key=settings.GEMINI_API_KEY)
            # model = genai.GenerativeModel("gemini-2.5-pro")
            # response = model.generate_content(prompt)

            # json_text = response.text.strip()
            # --- PASTE THIS NEW BLOCK ---
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates technical assessments in strictly valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )

            json_text = response.choices[0].message.content.strip()
            # ----------------------------
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]

            generated_paper = json.loads(json_text)

            return JsonResponse(generated_paper)
        except json.JSONDecodeError as e:

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


# @login_required
# @require_POST
# @transaction.atomic
# def save_paper(request):
#     """Saves the generated paper and calculates the total question count."""
#     try:
#         data = json.loads(request.body)

#         total_questions_count = 0
#         for section_data in data.get("sections", []):
#             total_questions_count += len(section_data.get("questions", []))

#         paper = QuestionPaper.objects.create(
#             created_by=request.user,
#             title=data.get("title", "Generated Assessment"),
#             job_title=data.get("job_title"),
#             department_name=data.get("department"),
#             min_exp=data.get("min_exp"),
#             max_exp=data.get("max_exp"),
#             is_active=True,
#             duration=data.get("duration"),
#             is_public_active=False,
#             is_private_link_active=False, 
#              # ✨ NAYA FIELD ADD KAREIN
#             status = models.CharField(
#                 max_length=20,
#                 choices=[
#                     ('draft', 'Draft'),
#                     ('active', 'Active'),
#                     ('inactive', 'Inactive'),
#                     ('archived', 'Archived'),
#                 ],
#                 default='draft',  # ✅ DEFAULT VALUE ZAROORI HAI
#                 help_text="Current status of the question paper"
#             ) ,
#             skills_list=(
#                 ", ".join(data.get("skills", []))
#                 if isinstance(data.get("skills"), list)
#                 else data.get("skills")
#             ),
#             total_questions=total_questions_count,
#         )

#         for section_index, section_data in enumerate(data.get("sections", [])):
#             section = PaperSection.objects.create(
#                 question_paper=paper,
#                 title=section_data.get("title"),
#                 order=section_index,
#             )
#             for q_index, question_data in enumerate(section_data.get("questions", [])):

#                 Question.objects.create(
#                     section=section,
#                     text=question_data.get("text"),
#                     answer=question_data.get("answer"),
#                     options=question_data.get("options"),
#                     order=q_index,
#                     question_type=question_data.get("type", "UN"),
#                 )

#         return JsonResponse(
#             {
#                 "success": True,
#                 "message": "Paper saved successfully!",
#                 "redirect_url": "/dashboard/",
#             }
#         )
#     except Exception as e:
#         print(f"Error saving paper: {e}")
#         return JsonResponse({"success": False, "error": str(e)}, status=400)
from django.views.decorators.http import require_POST
from django.db import transaction
from django.http import JsonResponse
import json
from .models import QuestionPaper, PaperSection, Question

# app/views.py

@require_POST
@transaction.atomic
def save_paper(request):
    try:
        data = json.loads(request.body)
        sections_data = data.get("sections", [])
        total_questions_count = 0
        
        # --- DEBUGGING PRINT (Aap ise baad mein hata sakte hain) ---
        print("-------------- DEBUG: DATA RECEIVED ----------- ---")
        print(data)
        
        # Create the main QuestionPaper object
        paper = QuestionPaper.objects.create(
            created_by=request.user,
            title=data.get("title", ""),
            job_title=data.get("job_title", ""),             # <-- FIX: "jobtitle" -> "job_title"
            department_name=data.get("department", ""),
            min_exp=data.get("min_exp", 0),                 # <-- FIX: "minexp" -> "min_exp"
            max_exp=data.get("max_exp", 0),                 # <-- FIX: "maxexp" -> "max_exp"
            duration=data.get("duration", 0),
            skills_list=data.get("skills", ""),             # <-- FIX: skills_list ko data.get se lein
            is_active=True,
            is_public_active=False,
            is_private_link_active=False,
            cutoff_score=data.get("cutoff_score", 20)      # <-- FIX: "cutoffscore" -> "cutoff_score"
        )
        
        # Create sections and questions
        for section_index, section_data in enumerate(sections_data):
            section = PaperSection.objects.create(
                question_paper=paper,
                title=section_data.get("title", f"Section {section_index}"),
                order=section_index,
                weightage=section_data.get("weightage", 0.0),  # Yeh line pehle se sahi thi
            )
            
            questions = section_data.get("questions", [])
            total_questions_count += len(questions)
            
            for q_index, question_data in enumerate(questions):
                Question.objects.create(
                    section=section,
                    text=question_data.get("text", ""),
                    answer=question_data.get("answer", ""),
                    options=question_data.get("options", None),
                    order=q_index,
                    question_type=question_data.get("type", "MCQ")
                )
        
        # Update total_questions count
        paper.total_questions = total_questions_count
        paper.save(update_fields=["total_questions"])
        
        return JsonResponse({
            "success": True,
            "message": "Paper saved successfully!",
            "redirecturl": "/dashboard"
        })
    except Exception as e:
        print(f"Error saving paper: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=400)
@login_required
def list_papers(request):
    papers = QuestionPaper.objects.filter(created_by=request.user).order_by(
        "-created_at"
    )
    return render(request, "question_generator/list_papers.html", {"papers": papers})




def take_paper(request, paper_id):
    """
    Handles the request for a public or invited user to take a question paper.
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id)

    if not paper.is_public_active:
        return render(request, "link_deactivated.html", status=403)

    invited_email = request.GET.get("email")

    redirect_url = reverse("test:user_register_link", kwargs={"link_id": str(paper.id)})

    if invited_email:
        return redirect(f"{redirect_url}?email={invited_email}")

    return redirect(redirect_url)


from django.urls import reverse  
from urllib.parse import urlencode  

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import QuestionPaper, TestRegistration


from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import QuestionPaper, TestRegistration


from .models import UserResponse


@login_required
def paper_detail_view(request, paper_id):
    """
    Displays the details of a single question paper with FIXED MCQ matching.
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)
    status_filter = request.GET.get("status", "all")
    shortlist_filter = request.GET.get("shortlist_status", "all")

    skills = [skill.strip() for skill in paper.skills_list.split(",") if skill.strip()]

    # Note: Template filters (striptags, lower) will handle normalization

    all_participants = list(
        TestRegistration.objects.filter(question_paper=paper).order_by("-start_time")
    )

    # ▼▼▼ THE FINAL, CORRECTED SCORING LOGIC ▼▼▼
    for p in all_participants:
        if p.is_completed:
            user_responses = UserResponse.objects.filter(registration=p)
            correct_answers_count = 0

            for response in user_responses:
                question = response.question
                user_answer = response.user_answer.strip()
                is_correct = False

                if not user_answer:
                    is_correct = False
                elif question and question.answer:
                    if question.question_type == "MCQ":

                        cleaned_answer = re.sub(r"<[^>]+>", "", question.answer).strip()
                        is_correct = user_answer.lower() == cleaned_answer.lower()
                        # cleaned_answer = re.sub(r"<[^>]+>", "", question.answer).strip()
                        # is_correct = user_answer.lower() == cleaned_answer.lower()
                    else:
                        qtype = question.question_type.upper()
                        if qtype in ("CODE", "CODING"):
                            evaluator_type = "coding"
                        elif qtype in ("SA", "SHORT", "SUBJECTIVE"):
                            evaluator_type = "short"
                        elif qtype in ("TF", "TRUE_FALSE", "BOOLEAN"):
                            evaluator_type = "true_false"
                        else:
                            evaluator_type = "short"

                        is_correct, _ = evaluate_answer_with_ai(
                            question_text=question.text,
                            user_answer=user_answer,
                            model_answer=question.answer.strip(),
                            question_type=evaluator_type,
                        )

                if is_correct:
                    correct_answers_count += 1

            total_questions = p.question_paper.total_questions
            live_percentage = 0
            if total_questions > 0:
                live_percentage = round((correct_answers_count / total_questions) * 100)

            p.score = live_percentage
            cutoff = p.question_paper.cutoff_score

            if cutoff is not None:
                if live_percentage >= cutoff:
                    p.status = "pass"
                else:
                    p.status = "fail"
            else:
                p.status = "pass"
        else:
            p.status = "pending"
    # ▲▲▲ END OF CORRECTED LOGIC ▲▲▲

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
    NOW ALSO SAVES MCQ OPTIONS!
    """
    paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

    if request.method == "POST":
        form = QuestionPaperEditForm(request.POST, instance=paper)

        if form.is_valid():
            updated_paper = form.save()

            total_questions_count = 0

            for section in paper.paper_sections.all():
                # ▼▼▼ YEH NAYA LOGIC ADD KAREIN ▼▼▼
                # Section ka weightage save karein
                weightage_key = f"section-weightage-{section.id}"
                if weightage_key in request.POST:
                    try:
                        # Value ko float mein convert karein, default 0.0
                        new_weightage = float(request.POST[weightage_key] or 0.0)
                        section.weightage = new_weightage
                        # Section ko database mein save karein
                        section.save(update_fields=["weightage"]) 
                    except (ValueError, TypeError):
                        # Agar koi galat value (jaise text) daalta hai, toh use ignore karein
                        pass
                # ▲▲▲ NAYA LOGIC KHATAM ▲▲▲
                for question in section.questions.all():
                    question_text_name = f"question-text-{question.id}"
                    question_answer_name = f"question-answer-{question.id}"

                    if question_text_name in request.POST:
                        new_text = request.POST[question_text_name].strip()
                        if new_text:  
                            question.text = new_text

                    if question_answer_name in request.POST:
                        new_answer = request.POST[question_answer_name].strip()
                        if new_answer:  
                            question.answer = new_answer
                        if question.question_type == "MCQ":
                            options = []
                            for opt_num in range(1, 11):  
                                option_key = f"option-{question.id}-{opt_num}"
                                if option_key in request.POST:
                                    option_value = request.POST[option_key].strip()
                                    if option_value:
                                        options.append(option_value)
                            if options:
                                question.options = options

                        question.save()
                   
                    total_questions_count += 1

            updated_paper.total_questions = total_questions_count
            updated_paper.save(update_fields=["total_questions"])

            messages.success(
                request,
                f"✅ Paper '{updated_paper.title}' successfully updated with {total_questions_count} questions!",
            )
            return redirect("paper_detail", paper_id=paper.id)

        else:
            messages.error(
                request,
                "❌ There were errors in your submission. Please check the form.",
            )

    else:
        form = QuestionPaperEditForm(instance=paper)

    context = {"form": form, "paper": paper, "title": f"Edit {paper.title}"}

    return render(request, "question_generator/paper_edit.html", context)


import logging

logger = logging.getLogger(__name__)




#     context = {"form": form}
#     return render(request, "partials/department/department_create.html", context)
# app/views.py

@login_required
def department_create_view(request):
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            try:
                # ✨ CHANGE 1: Pehle Department instance banayein par abhi database main pura commit na karein
                department = form.save(commit=False)
                # Department ko save karein taaki usse ek ID mil jaye
                department.save()

                # ✨ CHANGE 2: Ab explicitly Many-to-Many relations (sections) ko save karein
                form.save_m2m()

                messages.success(request, "Department created successfully!")
                return redirect("dashboard")
            except Exception as e:
                logger.error(f"Error creating department: {e}", exc_info=True)
                messages.error(request, f"Error: {e}")
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
#     """
#     Displays test results with clear indication of unattempted questions.
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
#     unattempted_count = 0  # ✅ NEW: Track unattempted questions

#     for response in user_responses:
#         question = response.question
#         user_answer = response.user_answer.strip()
#         is_correct = False
#         attempt_status = "incorrect"  # ✅ NEW: Default status

#         # ✅ Check if question was attempted
#         if not user_answer:
#             attempt_status = "unattempted"
#             unattempted_count += 1
#         else:
#             # Question attempt kiya gaya hai, ab evaluate karo
#             if question.question_type == "MCQ":
#                 model_answer = question.answer.strip()
#                 is_correct = user_answer.lower() == model_answer.lower()
#             else:
#                 # Map internal question type to evaluator type
#                 qtype = question.question_type.upper()
#                 if qtype in ("CODE", "CODING"):
#                     evaluator_type = "coding"
#                 elif qtype in ("SA", "SHORT", "SUBJECTIVE"):
#                     evaluator_type = "short"
#                 elif qtype in ("TF", "TRUE_FALSE", "BOOLEAN"):
#                     evaluator_type = "true_false"
#                 else:
#                     evaluator_type = "short"

#                 # evaluate_answer_with_ai returns (is_correct, details)
#                 is_correct, _ = evaluate_answer_with_ai(
#                     question_text=question.text,
#                     user_answer=user_answer,
#                     model_answer=question.answer.strip(),
#                     question_type=evaluator_type,
#                 )

#             # Set status based on correctness
#             if is_correct:
#                 score += 1
#                 attempt_status = "correct"
#             else:
#                 attempt_status = "incorrect"

#         results_data.append(
#             {
#                 "question_text": response.question.text,
#                 "user_answer": (
#                     response.user_answer if user_answer else "Not Attempted"
#                 ),  # ✅ NEW
#                 "correct_answer": response.question.answer,
#                 "is_correct": is_correct,
#                 "attempt_status": attempt_status,  # ✅ NEW: Pass status to template
#             }
#         )

#     incorrect_answers = total_questions - score - unattempted_count  # ✅ UPDATED
#     percentage = round((score / total_questions) * 100) if total_questions > 0 else 0

#     status = "Pass" if percentage >= cutoff_score else "Fail"

#     context = {
#         "registration": registration,
#         "results": results_data,
#         "score": score,
#         "total_questions": total_questions,
#         "incorrect_answers": incorrect_answers,
#         "unattempted_count": unattempted_count,  # ✅ NEW
#         "percentage": percentage,
#         "title": f"Test Report for {registration.email}",
#         "status": status,
#         "cutoff_score": cutoff_score,
#     }

#     return render(request, "partials/users/test_report.html", context)
# app/views.py

def testresult(request, registration_id):
    """Displays test results with section-wise weightage breakdown."""
    registration = get_object_or_404(TestRegistration, pk=registration_id)
    user_responses = UserResponse.objects.filter(
        registration=registration
    ).select_related('question')
    
    paper = registration.question_paper
    total_questions = paper.total_questions
    cutoff_score = paper.cutoff_score
    
    # Overall scoring
    score = 0
    results_data = []
    
    # Section-wise scoring
    section_scores = []
    total_weighted_score = 0  # <-- YEH LINE ADD KAREIN
    
    for section in paper.paper_sections.all():
        section_questions = section.questions.all()
        section_total = len(section_questions)
        section_correct = 0
        
        for response in user_responses:
            question = response.question
            if question.section == section:
                user_answer = response.user_answer.strip()
                is_correct = False
                
                if not user_answer:
                    is_correct = False
                elif question.question_type == "MCQ":
                    model_answer = question.answer.strip()
                    is_correct = user_answer.lower() == model_answer.lower()
                else:
                    qtype = question.question_type.upper()
                    if qtype in ["CODE", "CODING"]:
                        evaluator_type = "coding"
                    elif qtype in ["SA", "SHORT", "SUBJECTIVE"]:
                        evaluator_type = "short"
                    elif qtype in ["TF", "TRUEFALSE", "BOOLEAN"]:
                        evaluator_type = "truefalse"
                    else:
                        evaluator_type = "short"
                    
                    is_correct, _ = evaluate_answer_with_ai(
                        question_text=question.text,
                        user_answer=user_answer,
                        model_answer=question.answer.strip(),
                        question_type=evaluator_type,
                    )
                
                if is_correct:
                    section_correct += 1
                    score += 1 # Yeh raw score hai (e.g., 15/20)
        
        # Calculate section percentage and weighted score
        section_percentage = round((section_correct / section_total) * 100, 2) if section_total > 0 else 0
        weighted_score = round((section_percentage * section.weightage) / 100, 2) if section.weightage else 0
        
        total_weighted_score += weighted_score  # <-- YEH LINE ADD KAREIN (Total mein add karein)
        
        section_scores.append({
            'title': section.title,
            'weightage': section.weightage,        # (e.g., 20)
            'correct': section_correct,
            'total': section_total,
            'percentage': section_percentage,      # (e.g., 80.0)
            'weighted_score': weighted_score,      # (e.g., 16.0)
        })
    
    # ... (Build results_data for individual questions... yeh code same rahega) ...
    for response in user_responses:
        question = response.question
        user_answer = response.user_answer.strip()
        is_correct = False
        
        if not user_answer:
            is_correct = False
        elif question.question_type == "MCQ":
            model_answer = question.answer.strip()
            is_correct = user_answer.lower() == model_answer.lower()
        else:
            qtype = question.question_type.upper()
            if qtype in ["CODE", "CODING"]:
                evaluator_type = "coding"
            elif qtype in ["SA", "SHORT", "SUBJECTIVE"]:
                evaluator_type = "short"
            elif qtype in ["TF", "TRUEFALSE", "BOOLEAN"]:
                evaluator_type = "truefalse"
            else:
                evaluator_type = "short"
            
            is_correct, _ = evaluate_answer_with_ai(
                question_text=question.text,
                user_answer=user_answer,
                model_answer=question.answer.strip(),
                question_type=evaluator_type,
            )
        
        results_data.append({
            'question_text': question.text,
            'user_answer': user_answer if user_answer else "(No answer)",
            'correct_answer': question.answer,
            'is_correct': is_correct,
        })
        
    incorrect_answers = total_questions - score
    
    # --- AB HUM 'percentage' KO BHI WEIGHTED SCORE SE REPLACE KAR DENGE ---
    percentage = round(total_weighted_score, 2) # <-- YEH LINE BADLEIN
    status = "Pass" if percentage >= cutoff_score else "Fail"
    
    context = {
        'registration': registration,
        'results': results_data,
        'score': score,
        'total_questions': total_questions,
        'incorrect_answers': incorrect_answers,
        'percentage': percentage, # Yeh ab weighted score hai
        'title': f"Test Report for {registration.email}",
        'status': status,
        'cutoff_score': cutoff_score,
        'section_scores': section_scores,
        'total_weighted_score': total_weighted_score, # <-- YEH LINE ADD KAREIN
    }
    
    return render(request, 'partials/users/test_report.html', context)

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


# @login_required
# @require_POST
# def deactivate_paper(request, paper_id):
#     """
#     Soft deletes a question paper by setting its is_active flag to False.
#     """
#     try:

#         paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

#         paper.is_active = False
#         paper.save()

#         return JsonResponse(
#             {
#                 "status": "success",
#                 "message": f'Paper "{paper.title}" has been deactivated successfully.',
#             }
#         )

#     except QuestionPaper.DoesNotExist:
#         return JsonResponse(
#             {
#                 "status": "error",
#                 "message": "Paper not found or you do not have permission to perform this action.",
#             },
#             status=404,
#         )
#     except Exception as e:
#         return JsonResponse({"status": "error", "message": str(e)}, status=500)
# app/views.py

# ... (baaki saare imports)
from django.utils import timezone  # Yeh add karein
import datetime  # Yeh add karein
# ... (baaki saare imports)


@login_required
@require_POST
def deactivate_paper(request, paper_id):
    """
    Soft deletes a paper.
    NEW: Checks for genuinely active test takers (within their time limit).
    """
    try:
        paper = get_object_or_404(QuestionPaper, pk=paper_id, created_by=request.user)

        # --- YEH HAI BEHTAR CHECK ---
        
        # 1. Paper ka duration (minutes mein) lein
        duration_minutes = paper.duration
        
        active_takers_exist = False  # Pehle se False maan lein

        if duration_minutes and duration_minutes > 0:
            # 2. "Cutoff" time calculate karein.
            # Agar test 60 min ka hai, toh hum sirf unhe dhoondhenge
            # jinhone pichle 60 minute ke andar test start kiya tha.
            # Jo 60 min se pehle start kiye the, unka time waise hi khatam ho chuka hai.
            cutoff_time = timezone.now() - datetime.timedelta(minutes=duration_minutes)

            # 3. Query: Kya koi aisa user hai jo...
            #    - test complete nahi kiya hai (is_completed=False)
            #    - AND test pichle [duration] minutes ke andar start kiya tha? 
            #      (matlab unka time abhi chal raha hai)
            active_takers_exist = TestRegistration.objects.filter(
                question_paper=paper,
                is_completed=False,
                start_time__gt=cutoff_time  # Check: start_time cutoff ke BAAD ka hai
            ).exists()

        else:
            # 4. Agar paper ka duration 0 ya None hai, toh purana (safe) logic use karein
            #    (jo check karta hai ki kya koi bhi incomplete test hai)
            active_takers_exist = TestRegistration.objects.filter(
                question_paper=paper,
                is_completed=False,
                start_time__isnull=False
            ).exists()

        # --- CHECK KHATAM ---

        if active_takers_exist:
            # Agar active takers hain, toh error message ke saath 400 status return karein
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        f'Cannot deactivate paper "{paper.title}". '
                        "One or more users are currently within their active test session."
                    ),
                },
                status=400,
            )

        # Agar koi active taker nahi hai, toh paper ko deactivate karein
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


# def evaluate_answer_with_ai(
#     question_text: str,
#     user_answer: str,
#     model_answer: str,
#     question_type: str = "short",
# ) -> Tuple[bool, Dict[str, Any]]:
#     """
#     Uses Gemini AI to evaluate if a user's answer is conceptually correct.

#     Args:
#         question_text: The question being asked
#         user_answer: User's submitted answer
#         model_answer: Correct/reference answer
#         question_type: Type of question - "mcq", "short", "coding", "true_false"

#     Returns:
#         Tuple of (is_correct: bool, details: dict with confidence and reason)
#     """
#     # Empty answer check
#     if not user_answer or not user_answer.strip():
#         return False, {
#             "is_correct": False,
#             "confidence": 100,
#             "reason": "Answer is empty",
#         }

#     # Normalize inputs
#     user_answer = user_answer.strip()
#     model_answer = model_answer.strip()

#     try:
#         # Quick checks for specific question types before AI call
#         if question_type.lower() == "mcq":
#             return _evaluate_mcq(user_answer, model_answer)

#         elif question_type.lower() in ["true_false", "boolean"]:
#             return _evaluate_boolean(user_answer, model_answer)

#         # AI evaluation for short answer and coding
#         genai.configure(api_key=settings.GEMINI_API_KEY)
#         model = genai.GenerativeModel("gemini-2.0-flash-exp")

#         # Different prompts for different question types
#         if question_type.lower() == "coding":
#             prompt = _get_coding_prompt(question_text, user_answer, model_answer)
#         else:
#             prompt = _get_short_answer_prompt(question_text, user_answer, model_answer)

#         response = model.generate_content(prompt)
#         cleaned_text = response.text.strip()

#         # Remove markdown code blocks if present
#         if cleaned_text.startswith("```json"):
#             cleaned_text = cleaned_text[7:]
#         elif cleaned_text.startswith("```"):
#             cleaned_text = cleaned_text[3:]
#         if cleaned_text.endswith("```"):
#             cleaned_text = cleaned_text[:-3]
#         cleaned_text = cleaned_text.strip()

#         result = json.loads(cleaned_text)

#         is_correct = result.get("is_correct", False)
#         return is_correct, result

#     except json.JSONDecodeError as e:

#         return _fallback_evaluation(user_answer, model_answer, question_type)

#     except Exception as e:
#         print(f"AI Evaluation Error: {e}")
#         return _fallback_evaluation(user_answer, model_answer, question_type)

import json
import re
from typing import Tuple, Dict, Any
from django.conf import settings
from openai import OpenAI  # Import OpenAI instead of google.generativeai

# OpenAI Client initialize karein
client = OpenAI(api_key=settings.OPENAI_API_KEY)

def evaluate_answer_with_ai(
    question_text: str,
    user_answer: str,
    model_answer: str,
    question_type: str = "short",
) -> Tuple[bool, Dict[str, Any]]:
    """
    Uses OpenAI GPT-4o-mini to evaluate if a user's answer is conceptually correct.
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

        # --- AI Evaluation Section Changed Here ---

        # Different prompts for different question types
        if question_type.lower() == "coding":
            prompt = _get_coding_prompt(question_text, user_answer, model_answer)
            system_instruction = "You are an expert programming instructor evaluating code. Output ONLY JSON."
        else:
            prompt = _get_short_answer_prompt(question_text, user_answer, model_answer)
            system_instruction = "You are an expert technical evaluator. Output ONLY JSON."

        # OpenAI API Call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent evaluations
            max_tokens=500,
            response_format={"type": "json_object"}  # Forces valid JSON output
        )

        # Extract content
        cleaned_text = response.choices[0].message.content.strip()
        result = json.loads(cleaned_text)

        is_correct = result.get("is_correct", False)
        return is_correct, result

    except json.JSONDecodeError:
        print("AI Evaluation Error: Invalid JSON received from OpenAI")
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


# def _get_coding_prompt(question_text: str, user_code: str, model_code: str) -> str:
#     """
#     Generate prompt for coding evaluation with cross-language flexibility criteria.
#     (MODIFIED FOR LANGUAGE FLEXIBILITY - FOR DIRECT PASTE)
#     """
#     return f"""You are an expert programming instructor. Evaluate if the user's code correctly solves the problem.

# **Question:**
# {question_text}

# **Reference Solution (Use for context, but do not require exact matching):**
# ```
# {model_code}
# ```

# **User's Code:**
# ```
# {user_code}
# ```

# **Evaluation Criteria:**
# 1. **CRITICAL: The user's code MUST solve the specific problem described in the Question.**

# 2. **⭐ Cross-Language Tolerance (FLEXIBLE LOGIC) ⭐:**
#     * **If the QUESTION text DOES NOT explicitly name a programming language** (e.g., "Write a function...", "Solve this problem..."), **then ACCEPT the solution, even if the language of the User's Code differs from the Reference Solution, provided the core logic is sound.** The goal is to check technical skill, not language specific adherence, unless requested.
#     * If the **QUESTION text EXPLICITLY specifies a language** (e.g., "Write a JavaScript function...", "Implement this in Python"), then **code in a different language should result in is_correct: false**, regardless of the logic.

# 3. The core logic must be sound, even if the implementation style differs.
# 4. Accept different approaches: loops vs. comprehensions, recursion vs. iteration.
# 5. Accept different but correct algorithms.
# 6. Ignore minor syntax variations: spacing, indentation, bracket styles.
# 7. Accept more efficient or optimized solutions.

# **What to REJECT (This must result in is_correct: false):**
# - **Code that solves a COMPLETELY DIFFERENT PROBLEM than the one asked.**
# - Logic errors that produce incorrect output.
# - Missing critical functionality.
# - **Code in a different language when the question explicitly mandated a specific one.**

# **Scoring Guide:**
# - is_correct: true if code would work and solve the problem (50%+ functionality)
# - is_correct: false if code has fundamental logic errors or solves the wrong problem
# - confidence: 90-100% for perfect or near-perfect solutions
# - confidence: 70-89% for working solutions with minor issues

# Respond with ONLY valid JSON (no markdown, no extra text):
# {{
#     "is_correct": true/false,
#     "confidence": 0-100,
#     "reason": "brief explanation"
# }}"""
def _get_coding_prompt(question_text: str, user_code: str, model_code: str) -> str:
    """
    Generate a highly flexible prompt that forces AI to ignore language differences
    and boilerplate code unless specifically required by the question.
    """
    return f"""You are an expert multi-language code evaluator. Your ONLY job is to check if the user's logic solves the problem, regardless of the language used.

**Question:**
{question_text}

**User's Code (EVALUATE THIS LOGIC):**
```
{user_code}

**Question:**
{question_text}

**User's Code (Evaluate THIS based on its own language's syntax/logic):**

**Reference Solution (FOR CONTEXT ONLY - IGNORE LANGUAGE USED HERE):**


**CRITICAL EVALUATION RULES (MUST FOLLOW):**
1. **🚫 IGNORE LANGUAGE RESTRICTIONS (UNLESS EXPLICIT):**
   - If the question does NOT explicitly say "Write in JavaScript" (or another specific language), you **MUST ACCEPT** solutions in **Java, Python, C++, C, SQL, or JavaScript**.
   - The user's language DOES NOT need to match the Reference Solution's language.

2. **🏗️ IGNORE BOILERPLATE & STRUCTURE:**
   - In Java/C++, users often need full classes (`public class Main { ... }`) to run code. **DO NOT mark this wrong** if the question only asked for a "function".
   - Focus ONLY on the core logic inside the function/method that solves the problem.

3. **✅ LOGIC IS KING:**
   - Does the code actually solve the problem?
   - If it runs and produces the correct output (like "madam" -> true), it is **CORRECT**.
   - Ignore minor syntax errors (like missing semicolons) if the logic is sound.

**SCORING:**
- `is_correct: true` -> Logic is correct in ANY standard standard programming language.
- `is_correct: false` -> Logic is wrong, OR question EXPLICITLY forbade this language.

Output strictly valid JSON:
{{
    "is_correct": true/false,
    "confidence": 0-100,
    "reason": "One sentence feedback focusing ONLY on logic."
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

User = get_user_model()

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import reverse  #

User = get_user_model()


def password_reset_request(request):
    """
    Custom view jo email ko DB mein check karta hai aur agar milta hai,
    to Django ke default reset process ko aage badhata hai.
    """
    template_name = "registration/password_reset_form.html"

    if request.method == "POST":
        email = request.POST.get("email", "").strip()

        try:
            User.objects.get(email__iexact=email, is_active=True)

        except User.DoesNotExist:
            messages.error(
                request,
                "The email address you entered is not associated with any active account. Please check it and try again. 🧐",
            )
            return render(request, template_name, {})

      
        return auth_views.PasswordResetView.as_view(template_name=template_name)(
            request
        )

    return auth_views.PasswordResetView.as_view(template_name=template_name)(request)


from django.core.mail import send_mail  
from django.template.loader import render_to_string 
from django.utils.html import strip_tags  
from .forms import (
   SectionForm,
    SkillForm,
    InviteCandidateForm,  
)


from django.urls import reverse
from urllib.parse import urlencode  


@login_required
@require_POST
def invite_candidate(request):
    """
    Handles the AJAX request to invite a candidate via email.
    FIXED: Now adds email parameter to the link.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON data."}, status=400
        )

    form = InviteCandidateForm(data)

    if form.is_valid():
        candidate_email = form.cleaned_data["email"]
        paper_id = form.cleaned_data["paper_id"]

        try:
            paper = QuestionPaper.objects.get(pk=paper_id, created_by=request.user)
        except QuestionPaper.DoesNotExist:
            return JsonResponse(
                {"status": "error", "message": "Paper not found or unauthorized."},
                status=404,
            )

        if not paper.is_public_active:
            paper.is_public_active = True
            paper.save(update_fields=["is_public_active"])
            messages.info(
                request, f"Public link for '{paper.title}' was automatically activated."
            )

        registration_url = reverse(
            "test:user_register_link", kwargs={"link_id": str(paper.id)}
        )

        query_string = urlencode({"email": candidate_email})
        test_link = request.build_absolute_uri(f"{registration_url}?{query_string}")

        context = {
            "paper_title": paper.title,
            "job_title": paper.job_title,
            "recruiter_name": request.user.get_full_name() or request.user.username,
            "test_link": test_link,  
            "duration": paper.duration,
            "total_questions": paper.total_questions,
            "skills_list": paper.skills_list.split(","),
        }

       
        html_message = render_to_string("emails/candidate_invite.html", context)
        plain_message = strip_tags(html_message)

        try:
            send_mail(
                subject=f"Invitation to Take Assessment: {paper.title} for {paper.job_title}",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[candidate_email],
                html_message=html_message,
                fail_silently=False,
            )
            return JsonResponse(
                {
                    "status": "success",
                    "message": f"Invitation sent successfully to {candidate_email}!",
                    "is_public_active": paper.is_public_active,
                },
                status=200,
            )

        except Exception as e:
            logger.error(f"Error sending email to {candidate_email}: {e}")
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Email sending failed. Please check server logs.",
                },
                status=500,
            )
    else:
        return JsonResponse(
            {
                "status": "error",
                "message": "Form validation failed.",
                "errors": form.errors,
            },
            status=400,
        )



@login_required
@require_POST
def create_section_ajax(request):
    """
    AJAX endpoint to create a new section.
    """
    try:
        data = json.loads(request.body)
        form = SectionForm(data)
        
        if form.is_valid():
            section = form.save()
            return JsonResponse({
                "status": "success",
                "section": {
                    "id": section.id,
                    "name": section.name
                }
            }, status=201)
        else:
            return JsonResponse({
                "status": "error",
                "errors": form.errors
            }, status=400)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON"
        }, status=400)

# @login_required
# def search_skills_with_suggestions(request):
#     '''User type करे तो AI suggest करे'''
#     query = request.GET.get('q', '').strip().lower()
    
#     if not query or len(query) < 2:
#         return JsonResponse({'skills': [], 'suggestions': []})
    
#     try:
#         # DB में खोजो
#         db_skills = Skill.objects.filter(
#             name__icontains=query,
#             is_active=True
#         ).values_list('name', flat=True)[:5]
        
#         db_list = list(db_skills)
        
#         if len(db_list) >= 3:
#             return JsonResponse({'skills': db_list, 'suggestions': []})
        
#         genai.configure(api_key=settings.GEMINI_API_KEY)
#         model = genai.GenerativeModel('gemini-2.5-pro')
        
#         prompt = f'Technical recruiting expert: User typed "{query}". Suggest 7-10 related tech skills. Only skill names, one per line.'
        
#         response = model.generate_content(prompt)
#         ai_suggestions = [
#             s.strip() for s in response.text.split('\n')
#             if s.strip() and len(s.strip()) > 2
#         ][:6]
        
#         return JsonResponse({
#             'skills': db_list,
#             'suggestions': ai_suggestions
#         })
    
#     except Exception as e:
#         return JsonResponse({'skills': [], 'suggestions': []}, status=500)


from openai import OpenAI

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib.auth.decorators import login_required
from .models import Skill  
import os

     

import openai
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Skill 
from thefuzz import process, fuzz

@login_required
@require_http_methods(["GET"])
def search_skills_with_suggestions(request):
    query = request.GET.get('q', '').strip().lower()
    ai_provider = request.GET.get('provider', 'chatgpt').lower()
    
    if not query:
        return JsonResponse({'skills': [], 'suggestions': []})
    
    try:
       
        
        all_active_skills = list(Skill.objects.filter(is_active=True).values_list('name', flat=True))
       
        fuzzy_results = process.extract(query, all_active_skills, limit=50, scorer=fuzz.WRatio)
        
        # Sirf wahi rakhein jinka match score > 60 ho (adjust as needed)
        # fuzzy_results format: [('SkillName', score), ...]
        db_list = [res[0] for res in fuzzy_results if res[1] >= 65]

        # --- 2. AI LOGIC ---
        # CHANGE: 'len(query) < 3' ko 'len(query) < 2' kar diya taaki "fi" par bhi AI call ho sake
        # agar DB results kam hain (less than 10 kar diya taaki AI zyada active rahe choti queries par)
        if len(query) < 1 or len(db_list) >= 50:
             return JsonResponse({'skills': db_list, 'suggestions': []})
        
        if ai_provider == 'gemini':
             ai_suggestions = [] # Gemini implement hone par yahan add karein
        else:
            # Agar DB results bahut kam hain, tabhi AI call karein
            ai_suggestions = get_chatgpt_suggestions(query, db_list)
        
        ai_suggestions = ai_suggestions[:15]
        
        return JsonResponse({
            'skills': db_list,
            'suggestions': ai_suggestions,
            'provider': 'chatgpt'
        })
    
    except Exception as e:
        print(f"Search Error: {e}")
        return JsonResponse({'skills': [], 'suggestions': [], 'error': str(e)})

def get_chatgpt_suggestions(query, db_list):
    """Get 15 skill suggestions using OpenAI API"""
    try:
        # Check if key exists
        if not settings.OPENAI_API_KEY: return []

        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        excluded = ', '.join([f'"{s}"' for s in db_list]) if db_list else 'none'
        
        # CHANGE HERE: Prompt mein 15 maange hain
        system_prompt = "You are a technical recruiting expert. Output only a comma-separated list of 15 related short technical skill names. No explanations."
        user_prompt = f'User typed: "{query}". Exclude these DB results: {excluded}. Suggest 15 related technical skills.'

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=200 # Tokens badha diye kyunki 15 skills zyada space lengi
        )
        
        content = response.choices[0].message.content
        if content:
            raw_suggestions = content.replace('\n', ',').split(',')
            ai_suggestions = []
            for s in raw_suggestions:
                clean_s = s.strip().strip('.- •')
                if clean_s and len(clean_s) > 1 and clean_s.lower() not in [x.lower() for x in db_list]:
                    ai_suggestions.append(clean_s)
            return ai_suggestions
            
        return []

    except Exception as e:
        print(f"OpenAI Error: {e}")
        return []
