from django.shortcuts import render, get_object_or_404, redirect


from .models import Homework, Question, Answer
from .forms import AnswerForm


def homework_detail(request, homework_id):
    homework = get_object_or_404(Homework, pk=homework_id)
    questions = Question.objects.filter(homework=homework)
    return render(request, 'homework/homework_detail.html', {'homework': homework, 'questions': questions})


def submit_homework(request, homework_id):
    if request.method == "POST":
        # Process the submitted answers
        # This is a simplification; you'll need to handle each question's answer
        for question in Question.objects.filter(homework_id=homework_id):
            answer_text = request.POST.get(f'answer_{question.id}')
            Answer.objects.create(question=question, student=request.user, answer_text=answer_text)
        return redirect('homework_detail', homework_id=homework_id)
    
    # Show the form for submission
    homework = get_object_or_404(Homework, pk=homework_id)
    return render(request, 'homework/submit_homework.html', {'homework': homework})

