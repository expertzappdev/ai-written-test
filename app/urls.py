# app/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views.user_login, name="login"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.user_logout, name="logout"),
    path("register/", views.user_register, name="register"),
    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html"
        ),
        name="password_reset",
    ),
    path(
        "password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("generate/", views.generate_questions, name="generate_questions"),
    path("home/", views.home, name="home"),
    path("save-paper/", views.save_paper, name="save_paper"),
    path("papers/", views.list_papers, name="list_papers"),
    path("departments/create/", views.department_create_view, name="department_create"),
    path("skills/", views.skill_list_view, name="skill_list"),
    path("skills/create/", views.skill_create_view, name="skill_create"),
    path("skills/update/<int:pk>/", views.skill_update_view, name="skill_update"),
    path("skills/delete/<int:pk>/", views.skill_delete_view, name="skill_delete"),
    path("paper/<int:paper_id>/", views.paper_detail_view, name="paper_detail"),
    path("paper/<int:paper_id>/edit/", views.paper_edit_view, name="paper_edit"),
    path("paper/take/<int:paper_id>/", views.take_paper, name="take_paper"),
    path(
        "api/paper/<int:paper_id>/toggle-public/",
        views.toggle_paper_public_status,
        name="toggle_paper_public_status",
    ),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("users/delete/<int:user_id>/", views.delete_user, name="delete_user"),
    path("profile/<int:pk>/", views.user_profile_view, name="user_profile"),
]
