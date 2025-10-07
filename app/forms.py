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


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].label = "Email"
        self.fields["username"].widget.attrs.update(
            {
                "class": "w-full px-4 py-2.5 bg-slate-50 border border-slate-300 rounded-lg placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow",
                "placeholder": "Enter your email",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "w-full px-4 py-2.5 bg-slate-50 border border-slate-300 rounded-lg placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow",
                "placeholder": "••••••••",
            }
        )


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


# class UserProfileRegistrationForm(forms.ModelForm):
#     """
#     Handles the user profile fields with the same consistent styling.
#     """

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         for field_name, field in self.fields.items():
#             if field.label:
#                 placeholder_text = f"Enter your {field.label.lower()}..."
#             else:
#                 placeholder_text = f"Enter {field_name.replace('_', ' ')}..."

#             if isinstance(field.widget, forms.Textarea):
#                 field.widget.attrs.update(
#                     {
#                         "class": TEXTAREA_CLASSES,
#                         "rows": "1",
#                         "placeholder": placeholder_text,
#                     }
#                 )
#             else:
#                 field.widget.attrs.update(
#                     {"class": INPUT_CLASSES, "placeholder": placeholder_text}
#                 )

#     class Meta:
#         model = UserProfile
#         fields = ("phone_number", "address")


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "sections"]

    sections = forms.ModelMultipleChoiceField(
        queryset=Section.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = "__all__"


text_input_class = "w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-theme-primary focus:border-theme-primary"


class QuestionPaperEditForm(forms.ModelForm):
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
            "job_title": forms.TextInput(attrs={"class": text_input_class}),
            "title": forms.TextInput(attrs={"class": text_input_class}),
            "department_name": forms.TextInput(attrs={"class": text_input_class}),
            "duration": forms.NumberInput(attrs={"class": text_input_class}),
            "min_exp": forms.NumberInput(attrs={"class": text_input_class}),
            "max_exp": forms.NumberInput(attrs={"class": text_input_class}),
            "skills_list": forms.TextInput(
                attrs={
                    "class": text_input_class,
                    "placeholder": "e.g., Python, Django, JavaScript",
                }
            ),
        }


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name"]
