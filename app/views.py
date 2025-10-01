# app/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings  # API Key access karne ke liye
from .forms import LoginForm, UserRegistrationForm, UserProfileRegistrationForm
from google import genai  # Gemini API ke liye
import json  # JSON response parse karne ke liye
from django.db import transaction


# --- Authentication Views ---


from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import LoginForm


def user_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("dashboard")
        else:
            return redirect("home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_staff:
                return redirect("dashboard")
            else:
                return redirect("home")
    else:
        form = LoginForm()

    return render(request, "login.html", {"form": form, "title": "Login"})


def home(request):
    return render(request, "home.html", {"user": request.user})


@login_required
def dashboard(request):
    context = {
        "user": request.user,
        "title": "User Dashboard",
        "content": "Welcome to your secured dashboard!",
    }
    return render(request, "dashboard.html", context)


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

        profile_form = UserProfileRegistrationForm(request.POST)

    else:
        user_form = UserRegistrationForm()
        profile_form = UserProfileRegistrationForm()

    context = {"user_form": user_form, "profile_form": profile_form}
    return render(request, "registration/register.html", context)


# --- Question Generator View ---


@login_required
def generate_questions(request):
    """Handles the form submission, constructs the prompt, and calls the Gemini API."""

    generated_paper = None

    if request.method == "POST":
        try:
            # 1. User Inputs Capture
            job_title = request.POST.get("job_title")
            min_exp = request.POST.get("min_exp")
            max_exp = request.POST.get("max_exp")
            total_questions = request.POST.get("total_questions")
            skills_raw = request.POST.get("skills")

            # Dynamic Sections Parsing (UI fields ke naam ke anusaar)
            sections_data = {}
            sections = ["Aptitude", "Programming", "Technical", "Behavioral"]
            for section in sections:
                count_key = f"section_{section}"
                count = request.POST.get(count_key)
                if count and int(count) > 0:
                    sections_data[section] = int(count)

            # --- 2. Prompt Construction (Gemini ke liye) ---

            # Prompt ko structured JSON output ke liye guide karein
            prompt = f"""
            Generate a technical assessment paper based on the following precise specifications.
            The entire response MUST be a single, valid JSON object that adheres to the structure defined below.
            
            1. Job Role: {job_title}
            2. Experience Level: From {min_exp} to {max_exp} years.
            3. Core Skills to Test: {skills_raw}
            4. Total Questions: {total_questions}
            
            5. Paper Sections and Question Counts: {json.dumps(sections_data)} 
            
            6. Output Structure Constraint:
               - The main JSON object MUST have two keys: 'title' (string) and 'sections' (array).
               - The 'sections' array MUST match the required sections (e.g., Aptitude, Programming) and their question counts.
               - Each question MUST include: 'id' (integer), 'type' (e.g., MCQ, Short Answer, Coding), 'text', 'options' (array of strings, if MCQ), and 'answer' (the correct answer).

            Generate the paper now.
            """

            # --- 3. Gemini API Call ---

            # settings.GEMINI_API_KEY se key access karein
            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            response = client.models.generate_content(
                model="gemini-2.5-pro", contents=prompt
            )

            # JSON clean aur parse karein (LLMs kabhi-kabhi response ko markdown mein wrap kar dete hain)
            json_text = response.text.strip().lstrip("```json").rstrip("```")
            generated_paper = json.loads(json_text)

        except json.JSONDecodeError:
            generated_paper = {
                "error": "Failed to decode response into valid JSON. Check API output."
            }
        except genai.errors.APIError as e:
            generated_paper = {"error": f"Gemini API Error: {str(e)}"}
        except Exception as e:
            generated_paper = {"error": f"An unexpected error occurred: {str(e)}"}

    # 4. Render the Generator UI
    context = {"paper": generated_paper, "is_post": request.method == "POST"}
    return render(request, "question_generator/generator.html", context)
