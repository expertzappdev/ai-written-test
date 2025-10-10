# app/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.contrib.auth import get_user_model
from .models import User, UserProfile
from .models import Department, Skill
from .models import Section
from .models import QuestionPaper

User = get_user_model()
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


class LoginForm(AuthenticationForm):
    """
    Custom login form to add specific validation for email and password fields.
    """

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Enter your email address",
                "autofocus": True,
                "autocomplete": "username",
            }
        ),
    )

    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "••••••••",
                "minlength": "8",
                "maxlength": "64",
                "autocomplete": "current-password",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username and not username.strip():
            raise ValidationError(
                "This field cannot be blank or contain only whitespace.",
                code="whitespace_username",
            )
        return username.strip()

    def clean_password(self):
        """
        Adds server-side validation for the password field.
        """
        password = self.cleaned_data.get("password")
        if password and not password.strip():
            raise ValidationError(
                "Password cannot contain only whitespace.", code="whitespace_password"
            )

        password = password.strip()

        if len(password) < 8:
            raise ValidationError(
                "Password must be at least 8 characters long.", code="min_length"
            )
        # ✨ YAHAN BADLAV KIYA GAYA HAI ✨
        if len(password) > 64:
            raise ValidationError(
                "Password is too long. Please use a password with 64 characters or less.",
                code="max_length",
            )

        return password


INPUT_CLASSES = (
    "mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm "
    "placeholder-gray-400 focus:outline-none focus:ring-blue-primary "
    "focus:border-blue-primary sm:text-sm"
)
TEXTAREA_CLASSES = f"{INPUT_CLASSES} resize-y"


# -------------------- USER REGISTRATION FORM --------------------
class UserRegistrationForm(BaseUserCreationForm):
    """
    Handles new user creation with consistent Tailwind styling.
    """

    email = forms.EmailField(
        required=True, help_text="A valid email address is required."
    )
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if field.label:
                placeholder_text = f"Enter your {field.label.lower()}..."
            else:
                placeholder_text = f"Enter {field_name.replace('_', ' ')}..."

            field.widget.attrs.update(
                {"class": INPUT_CLASSES, "placeholder": placeholder_text}
            )

    def clean_email(self):
        """
        Validates that the email is not already registered.
        """
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Email already registered. Please login.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        if commit:
            user.save()
        return user

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


# -------------------- USER PROFILE FORM --------------------
class UserProfileRegistrationForm(forms.ModelForm):
    """
    Handles the user profile fields (phone, address) with same styling.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field.label:
                placeholder_text = f"Enter your {field.label.lower()}..."
            else:
                placeholder_text = f"Enter {field_name.replace('_', ' ')}..."

            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update(
                    {
                        "class": TEXTAREA_CLASSES,
                        "rows": "1",
                        "placeholder": placeholder_text,
                    }
                )
            else:
                field.widget.attrs.update(
                    {"class": INPUT_CLASSES, "placeholder": placeholder_text}
                )

    class Meta:
        model = UserProfile
        fields = ("phone_number", "address")


# class DepartmentForm(forms.ModelForm):
#     # This part remains the same
#     sections = forms.ModelMultipleChoiceField(
#         queryset=Section.objects.all(),
#         widget=forms.CheckboxSelectMultiple,
#         required=True,
#         error_messages={
#             "required": "Please select at least one section for the department."
#         },
#     )

#     class Meta:
#         model = Department
#         fields = ["name", "sections"]

#     # ▼▼▼ ADD THIS VALIDATION METHOD ▼▼▼
#     def clean_name(self):
#         """
#         Custom validation to check for case-insensitive duplicate department names.
#         """
#         # Get the name submitted by the user
#         name = self.cleaned_data.get("name")

#         # Query the database for an existing department with the same name (ignoring case)
#         # We exclude the current department instance itself if we are editing it
#         if (
#             Department.objects.filter(name__iexact=name)
#             .exclude(pk=self.instance.pk)
#             .exists()
#         ):
#             # If a match is found, raise a validation error with your custom message
#             raise forms.ValidationError(
#                 "A department with this name already exists. Please use a different name."
#             )


#         # If the name is unique, return the cleaned name
#         return name
class DepartmentForm(forms.ModelForm):
    sections = forms.ModelMultipleChoiceField(
        queryset=Section.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        error_messages={
            "required": "Please select at least one section for the department."
        },
    )

    class Meta:
        model = Department
        fields = ["name", "sections"]

    def clean_name(self):
        """
        Custom validation to prevent duplicate or similar department names.
        Blocks:
        - Exact duplicates (case-insensitive)
        - Partial matches like 'Market' if 'Marketing' exists, or vice versa
        """
        name = self.cleaned_data.get("name", "").strip()

        # Get all other department names (ignore current one if editing)
        existing_departments = Department.objects.exclude(
            pk=self.instance.pk
        ).values_list("name", flat=True)

        # Check against each department name
        for dept_name in existing_departments:
            dept_name_clean = dept_name.strip().lower()
            name_clean = name.lower()

            # Block if the new name is contained in existing one, or vice versa
            if (
                name_clean == dept_name_clean
                or name_clean in dept_name_clean
                or dept_name_clean in name_clean
            ):
                raise forms.ValidationError(
                    f"A department with a similar name already exists ('{dept_name}'). Please use a different name."
                )

        return name


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = "__all__"


text_input_class = "w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-theme-primary focus:border-theme-primary"


# class QuestionPaperEditForm(forms.ModelForm):
#     class Meta:
#         model = QuestionPaper
#         job_title = forms.CharField(
#             min_length=3,
#             max_length=40,
#             widget=forms.TextInput(attrs={"class": text_input_class}),
#         )
#         fields = [
#             "job_title",
#             "title",
#             "department_name",
#             "duration",
#             "min_exp",
#             "max_exp",
#             "skills_list",
#         ]
#         widgets = {
#             "job_title": forms.TextInput(attrs={"class": text_input_class}),
#             "title": forms.TextInput(attrs={"class": text_input_class}),
#             "department_name": forms.TextInput(attrs={"class": text_input_class}),
#             "duration": forms.NumberInput(attrs={"class": text_input_class}),
#             "min_exp": forms.NumberInput(attrs={"class": text_input_class}),
#             "max_exp": forms.NumberInput(attrs={"class": text_input_class}),
#             "skills_list": forms.TextInput(
#                 attrs={
#                     "class": text_input_class,
#                     "placeholder": "e.g., Python, Django, JavaScript",
#                 }
#             ),
#         }

# app/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.contrib.auth import get_user_model
from .models import User, UserProfile
from .models import Department, Skill
from .models import Section
from .models import QuestionPaper

User = get_user_model()
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


# ... (LoginForm, UserRegistrationForm, etc. remain unchanged) ...


text_input_class = "w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-theme-primary focus:border-theme-primary"


# class QuestionPaperEditForm(forms.ModelForm):
#     # ✨ REQUIREMENT 1: Job Title Validation ✨
#     # We define the field here to add specific length validations.
#     job_title = forms.CharField(
#         min_length=3,
#         max_length=40,
#         widget=forms.TextInput(attrs={"class": text_input_class}),
#     )

#     class Meta:
#         model = QuestionPaper
#         fields = [
#             "job_title",
#             "title",
#             "department_name",
#             "duration",
#             "min_exp",
#             "max_exp",
#             "skills_list",
#         ]
#         widgets = {
#             # 'job_title' is now defined above, so it's removed from here.
#             "job_title": forms.TextInput(attrs={"class": text_input_class}),
#             # "title": forms.TextInput(attrs={"class": text_input_class}),
#             "department_name": forms.TextInput(attrs={"class": text_input_class}),
#             # ✨ REQUIREMENT 2: Min/Max Experience Counter (Backend) ✨
#             # The backend widget remains a NumberInput. The counter UI is a frontend enhancement.
#             # We add a 'min' attribute for basic browser-side validation.
#             "duration": forms.NumberInput(
#                 attrs={"class": text_input_class, "min": "1"}
#             ),
#             "min_exp": forms.NumberInput(
#                 attrs={"class": text_input_class, "id": "min_exp_input", "min": "0"}
#             ),
#             "max_exp": forms.NumberInput(
#                 attrs={"class": text_input_class, "id": "max_exp_input", "min": "0"}
#             ),
#             # ✨ REQUIREMENT 3: Skills Auto-suggestion (Backend) ✨
#             # We add a unique class to this input to target it with JavaScript.
#             "skills_list": forms.TextInput(
#                 attrs={
#                     "class": f"{text_input_class} skill-autocomplete-input",  # Added new class
#                     "placeholder": "e.g., Python, Django, JavaScript",
#                     "autocomplete": "off",  # Important for custom suggestions
#                 }
#             ),
#         }

#     # === START: ADDED VALIDATION FOR JOB TITLE ===
#     def clean_job_title(self):
#         """
#         Adds custom validation for the job_title field.
#         Ensures the job title is a string with a length between 3 and 40 characters.
#         """
#         job_title = self.cleaned_data.get("job_title", "").strip()

#         # Check 1: Minimum length
#         if len(job_title) < 3:
#             raise forms.ValidationError("Job title must be at least 3 characters long.")

#         # Check 2: Maximum length
#         if len(job_title) > 40:
#             raise forms.ValidationError(
#                 "Job title cannot be longer than 40 characters."
#             )

#         # Check 3: Ensure it contains letters (not just numbers or symbols)
#         if not re.search(r"[a-zA-Z]", job_title):
#             raise forms.ValidationError("Job title must contain letters.")

#         return job_title


#     # === END: ADDED VALIDATION ===


class QuestionPaperEditForm(forms.ModelForm):
    # ✨ REQUIREMENT 1: Job Title Validation (UPDATED) ✨
    # The max_length has been changed from 40 to 30.
    job_title = forms.CharField(
        min_length=3,
        max_length=30,  # <-- CHANGED
        widget=forms.TextInput(attrs={"class": text_input_class}),
    )

    class Meta:
        model = QuestionPaper
        fields = [
            "job_title",
            "title",
            "department_name",
            "duration",
            "min_exp",
            "max_exp",
            "skills_list",
        ]
        widgets = {
            # 'job_title' is now defined above, so it's removed from here.
            "job_title": forms.TextInput(attrs={"class": text_input_class}),
            # "title": forms.TextInput(attrs={"class": text_input_class}),
            "department_name": forms.TextInput(attrs={"class": text_input_class}),
            # ✨ REQUIREMENT 2: Min/Max Experience Counter (Backend) ✨
            # The backend widget remains a NumberInput. The counter UI is a frontend enhancement.
            # We add a 'min' attribute for basic browser-side validation.
            "duration": forms.NumberInput(
                attrs={"class": text_input_class, "min": "1"}
            ),
            "min_exp": forms.NumberInput(
                attrs={"class": text_input_class, "id": "min_exp_input", "min": "0"}
            ),
            "max_exp": forms.NumberInput(
                attrs={"class": text_input_class, "id": "max_exp_input", "min": "0"}
            ),
            # ✨ REQUIREMENT 3: Skills Auto-suggestion (Backend) ✨
            # We add a unique class to this input to target it with JavaScript.
            "skills_list": forms.TextInput(
                attrs={
                    "class": f"{text_input_class} skill-autocomplete-input",  # Added new class
                    "placeholder": "e.g., Python, Django, JavaScript",
                    "autocomplete": "off",  # Important for custom suggestions
                }
            ),
        }

    # === START: ADDED VALIDATION FOR JOB TITLE (UPDATED) ===
    def clean_job_title(self):
        """
        Adds custom validation for the job_title field.
        Ensures the job title is a string with a length between 3 and 30 characters.
        """
        job_title = self.cleaned_data.get("job_title", "").strip()

        # Check 1: Minimum length
        if len(job_title) < 3:
            raise forms.ValidationError("Job title must be at least 3 characters long.")

        # Check 2: Maximum length (UPDATED)
        if len(job_title) > 30:  # <-- CHANGED
            raise forms.ValidationError(
                "Job title cannot be longer than 30 characters."  # <-- CHANGED
            )

        # Check 3: Ensure it contains letters (not just numbers or symbols)
        if not re.search(r"[a-zA-Z]", job_title):
            raise forms.ValidationError("Job title must contain letters.")

        return job_title


text_input_class = "w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-theme-primary focus:border-theme-primary"


SKILL_ALIASES = {
    "reactjs": "react",
    "vuejs": "vue",
    "node js": "nodejs",
    "angular js": "angular",
}


from django import forms
from .models import Skill

SKILL_ALIASES = {
    "reactjs": "react",
    "vuejs": "vue",
    "node js": "nodejs",
    "angular js": "angular",
}


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        # ✅ CHANGE: 'is_active' ko yahan add karein
        fields = ["name", "is_active"]

    def clean_name(self):
        """
        Custom validation for the skill name.
        1. Converts the name to lowercase.
        2. Checks for aliases (e.g., reactjs -> react).
        3. Checks for case-insensitive uniqueness.
        """
        name = self.cleaned_data.get("name")
        if name:
            # self.instance ko check karna zaroori hai update ke time existing name ko allow karne ke liye
            if self.instance and self.instance.name.lower() == name.strip().lower():
                return name  # Agar naam change nahi hua hai, to validation skip karein

            cleaned_name = name.strip().lower()

            if cleaned_name in SKILL_ALIASES:
                cleaned_name = SKILL_ALIASES[cleaned_name]

            if Skill.objects.filter(name__iexact=cleaned_name).exists():
                raise forms.ValidationError(
                    "This skill already exists. Please use the existing one."
                )

            return cleaned_name
        return name


text_input_class = "w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-theme-primary focus:border-theme-primary"


from django import forms


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        required=True,
        error_messages={
            "required": "Email address is required.",
            "invalid": "Please enter a valid email address.",
        },
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        blocked_domains = ["test.com", "example.com", "mailinator.com", "fake.com"]
        domain = email.split("@")[-1]
        if domain in blocked_domains:
            raise forms.ValidationError(
                "Email domain not allowed. Please use your real email."
            )
        return email
