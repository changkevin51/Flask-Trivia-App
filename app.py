from flask import Flask, render_template, redirect, url_for, session, request, flash
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, RadioField, SubmitField, StringField
from wtforms.validators import DataRequired
import pandas as pd
import secrets
from flask_sqlalchemy import SQLAlchemy
import random

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///leaderboard.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

df = pd.read_csv("questions.csv")
df["options"] = df[["option1", "option2", "option3", "option4"]].values.tolist()

class HomeForm(FlaskForm):
    display_name = StringField('Enter Your Display Name', validators=[DataRequired()])
    categories = SelectMultipleField('Categories', coerce=str)
    difficulties = SelectMultipleField('Difficulties', coerce=str)
    submit = SubmitField('Start Trivia')

class QuestionForm(FlaskForm):
    option = RadioField("Options", choices=[], validators=[DataRequired()])
    submit_answer = SubmitField("Submit Answer")
    skip_question = SubmitField("Skip Question")
    end_quiz = SubmitField("End Trivia")
    eliminate_options = SubmitField("Eliminate Two Wrong Answers")

class LeaderboardEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    attempted = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<LeaderboardEntry {self.player}, Score: {self.score}>"

@app.route("/leaderboard")
def leaderboard():
    leaderboard_entries = LeaderboardEntry.query.order_by(
        LeaderboardEntry.score.desc(), LeaderboardEntry.percentage.desc()
    ).all()
    return render_template("leaderboard.html", leaderboard=leaderboard_entries)

@app.route("/", methods=["GET", "POST"])
def home():
    form = HomeForm()
    form.categories.choices = [(cat, cat) for cat in df["category"].unique()]
    form.difficulties.choices = [(diff, diff) for diff in df["difficulty"].unique()]

    if request.method == "POST":
        selected_categories = request.form.getlist("categories")
        selected_difficulties = request.form.getlist("difficulties")
        display_name = request.form.get("display_name")

        if not display_name:
            flash("Please enter your display name.")
            return render_template("home.html", form=form)

        if not selected_categories or not selected_difficulties:
            flash("Please select at least one category and one difficulty.")
            return render_template("home.html", form=form)

        session["score"] = 0
        session["current_question"] = 0
        session["answers"] = []
        session["skipped_questions"] = 0
        session["selected_categories"] = selected_categories
        session["selected_difficulties"] = selected_difficulties
        session["player_name"] = display_name

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

    if "eliminate_button_visible" not in session:
        session["eliminate_button_visible"] = True

    question_data = filtered_questions.iloc[session["current_question"]].to_dict()
    session["current_question_data"] = question_data
    session["used_eliminate"] = False

    form = QuestionForm()

    if question_data.get("type") == "boolean":
        form.option.choices = [
            (question_data["option1"], question_data["option1"]),
            (question_data["option2"], question_data["option2"]),
        ]
    else:
        form.option.choices = [(opt, opt) for opt in question_data["options"]]

    if len(form.option.choices) <= 2:
        session["eliminate_button_visible"] = False

    show_feedback = False

    if request.method == "POST":
        action = request.form.get("action")

        if action == "submit_answer" and form.validate_on_submit():
            selected_option = form.option.data
            correct_answer = question_data["correct_answer"]
            session["eliminate_button_visible"] = False
            session["answers"].append((question_data["question"], selected_option, correct_answer))

            if selected_option == correct_answer:
                if session["used_eliminate"]:
                    session["score"] += 0.5
                else:
                    session["score"] += 1
            show_feedback = True

        elif action == "eliminate_options" and session["eliminate_button_visible"]:
            current_question_data = session["current_question_data"]
            incorrect_options = [
                opt for opt in current_question_data["options"]
                if opt != current_question_data["correct_answer"] and pd.notna(opt)
            ]
            if len(incorrect_options) > 2:
                options_to_remove = random.sample(incorrect_options, 2)
                current_question_data["options"] = [
                    opt for opt in current_question_data["options"]
                    if opt not in options_to_remove
                ]
            session["current_question_data"] = current_question_data
            session["used_eliminate"] = True
            session.modified = True

        elif action == "skip_question":
            session["skipped_questions"] += 1
            session["current_question"] += 1
            if session["current_question"] >= len(filtered_questions):
                return redirect(url_for("end_game"))
            return redirect(url_for("question"))

        elif action == "end_quiz":
            return redirect(url_for("end_game"))

        elif action == "next_question":
            session["current_question"] += 1
            session["eliminate_button_visible"] = True
            if session["current_question"] >= len(filtered_questions):
                return redirect(url_for("end_game"))
            return redirect(url_for("question"))

    return render_template(
        "question.html",
        question=question_data["question"],
        form=form,
        correct_answer=question_data["correct_answer"] if show_feedback else None,
        show_feedback=show_feedback,
        score=session["score"],
        eliminate_button_visible=session["eliminate_button_visible"]
    )

@app.route("/end")
def end_game():
    score = session.get("score", 0)
    total_questions_attempted = len(session.get("answers", [])) + session.get("skipped_questions", 0)
    skipped_questions = session.get("skipped_questions", 0)
    percentage = (score / (total_questions_attempted - skipped_questions)) * 100 if total_questions_attempted > 0 else 0

    player_name = session.get("player_name", "Anonymous")
    new_entry = LeaderboardEntry(
        player=player_name,
        score=score,
        percentage=round(percentage, 2),
        attempted=total_questions_attempted - skipped_questions
    )
    db.session.add(new_entry)
    db.session.commit()

    return render_template(
        "result.html", score=score, total=total_questions_attempted, skipped=skipped_questions, percentage=percentage
    )

@app.route('/eliminate_options', methods=['GET', 'POST'])
def eliminate_options():
    if not session.get('used_eliminate', False):
        session['used_eliminate'] = True
        session["eliminate_button_visible"] = False
        current_question_data = session['current_question_data']

        incorrect_options = [
            opt for opt in current_question_data['options']
            if opt != current_question_data['correct_answer']
        ]
        options_to_remove = random.sample(incorrect_options, 2)
        current_question_data['options'] = [
            opt for opt in current_question_data['options']
            if opt not in options_to_remove
        ]
        session['current_question_data'] = current_question_data
        session.modified = True

    return redirect(url_for('question'))

if __name__ == "__main__":
    app.run()
