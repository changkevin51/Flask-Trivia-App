from flask import Flask, render_template, redirect, url_for, session, request, flash
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, RadioField, SubmitField
from wtforms.validators import DataRequired
import pandas as pd
import secrets
import random

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

df = pd.read_csv("questions.csv")
df["options"] = df[["option1", "option2", "option3", "option4"]].values.tolist()

class HomeForm(FlaskForm):
    categories = SelectMultipleField("Select Categories", choices=[], validators=[DataRequired()])
    difficulties = SelectMultipleField("Select Difficulties", choices=[], validators=[DataRequired()])
    submit = SubmitField("Start Trivia")

class QuestionForm(FlaskForm):
    option = RadioField("Options", choices=[], validators=[DataRequired()])
    submit = SubmitField("Submit Answer")
    end_quiz = SubmitField("End Tivia")

@app.route("/", methods=["GET", "POST"])
def home():
    form = HomeForm()
    form.categories.choices = [(cat, cat) for cat in df["category"].unique()]
    form.difficulties.choices = [(diff, diff) for diff in df["difficulty"].unique()]

    if request.method == "POST":
        selected_categories = request.form.getlist("categories")
        selected_difficulties = request.form.getlist("difficulties")

        if not selected_categories or not selected_difficulties:
            flash("Please select at least one category and one difficulty.")
            return render_template("home.html", form=form)

        session["score"] = 0
        session["current_question"] = 0
        session["answers"] = []
        session["skipped_questions"] = 0
        session["selected_categories"] = selected_categories
        session["selected_difficulties"] = selected_difficulties

        return redirect(url_for("question"))

    return render_template("home.html", form=form)

@app.route("/question", methods=["GET", "POST"])
def question():
    filtered_questions = df[
        (df["category"].isin(session["selected_categories"])) &
        (df["difficulty"].isin(session["selected_difficulties"]))
    ]

    if session["current_question"] >= len(filtered_questions):
        return redirect(url_for("end_game"))

    question_data = filtered_questions.iloc[session["current_question"]].to_dict()
    session["current_question_data"] = question_data

    form = QuestionForm()

    if question_data.get("type") == "boolean":
        form.option.choices = [
            (question_data["option1"], question_data["option1"]),
            (question_data["option2"], question_data["option2"]),
        ]
    else:
        form.option.choices = [(opt, opt) for opt in question_data["options"]]

    show_feedback = False

    if request.method == "POST":
        if "end_quiz" in request.form:
            return redirect(url_for("end_game"))

        if "skip_question" in request.form:
            session["skipped_questions"] += 1
            session["current_question"] += 1
            return redirect(url_for("question"))

        if "submit_answer" in request.form:
            selected_option = form.option.data
            correct_answer = question_data["correct_answer"]

            session["answers"].append((question_data["question"], selected_option, correct_answer))
            if selected_option == correct_answer:
                session["score"] += 1

            show_feedback = True

        if "next_question" in request.form:
            session["current_question"] += 1
            return redirect(url_for("question"))

    return render_template(
        "question.html",
        question=question_data["question"],
        form=form,
        correct_answer=session.get("current_question_data", {}).get("correct_answer", None),
        show_feedback=show_feedback,
        score=session["score"]
    )

@app.route("/end")
def end_game():
    score = session.get("score", 0)
    total_questions_attempted = len(session.get("answers", [])) + session.get("skipped_questions", 0)
    skipped_questions = session.get("skipped_questions", 0)
    percentage = (score / (total_questions_attempted - skipped_questions)) * 100 if total_questions_attempted > 0 else 0

    return render_template(
        "result.html", score=score, total=total_questions_attempted, skipped=skipped_questions, percentage=percentage
    )

if __name__ == "__main__":
    app.run(debug=True)